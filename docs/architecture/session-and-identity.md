# Session and Identity Design

Date: 2026-03-23
Status: Draft
Related: PRD Section 18.8

> **Note:** All enum values and field definitions in this document must match the canonical data model (`data-model.md`). If there is a discrepancy, `data-model.md` is authoritative.

## Overview

MoLabel is a local-network tool without enterprise authentication. Multiple reviewers can work concurrently through the same review queues from different browser sessions. This document specifies how reviewer identity, session management, queue claiming, and multi-session coordination work.

The design optimizes for low-friction setup (a reviewer can start working in under 30 seconds on first visit) while preserving enough identity tracking for audit trails and queue management.

## Reviewer Profiles

### Data Model

```sql
CREATE TABLE reviewer_profiles (
    id TEXT PRIMARY KEY,                  -- UUID v4, server-generated
    display_name TEXT NOT NULL,           -- user-chosen, not unique (two "Alex" reviewers are fine)
    avatar_color TEXT,                    -- hex color, auto-assigned from a palette, editable (optional)
    is_operator INTEGER NOT NULL DEFAULT 0, -- operator flag (not enforced initially — the flag exists for future access control)
    is_active INTEGER NOT NULL DEFAULT 1,-- whether this profile is currently active
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_active_at TEXT,                  -- updated on each session activity (optional)
    preferences TEXT                      -- JSON: UI preferences (optional)
);

CREATE INDEX idx_reviewer_last_active ON reviewer_profiles(last_active_at);
```

### Profile Properties

- **id**: UUID v4, generated server-side on profile creation. This is the stable identifier used in all review events, agent runs, audit entries, and queue claims. It never changes.
- **display_name**: Free-text, chosen by the reviewer. Does not need to be unique — reviewers are identified by UUID internally and by display name + avatar color in the UI. Maximum 64 characters. Cannot be empty.
- **avatar_color**: Hex color string (e.g., `"#4A90D9"`). Optional. Auto-assigned from a 12-color palette on creation, cycling through colors to avoid adjacent duplicates. Editable by the reviewer.
- **is_operator**: Boolean flag (default false). Operators can execute workflows, approve gates, manage datasets, and perform admin operations. This flag is advisory — it is NOT enforced as access control. Any reviewer can perform any action. The flag exists so that future versions can enforce it without a data model migration.
- **is_active**: Boolean flag (default true). When false, the profile is hidden from the profile selector dropdown but remains queryable for audit purposes.
- **created_at**: ISO 8601 timestamp, set once on creation.
- **last_active_at**: ISO 8601 timestamp (optional), updated whenever the reviewer's session makes any API call. Used by mission control to show "active" vs "idle" reviewers.
- **preferences**: JSON (optional). UI preferences such as theme, keyboard shortcuts, and layout.

### Profile Lifecycle

- Profiles are created via the "Who are you?" screen (see Session Management below).
- Profiles cannot be deleted. This preserves audit trail integrity — review events reference the reviewer `id` as a foreign key. A deleted profile would create dangling references.
- Profiles can be edited: display name and avatar color can be changed at any time. Changes are reflected in future UI displays but do NOT retroactively change the display name on historical review events. Historical events store the reviewer `id` only; the display name is joined at query time.
- If a reviewer leaves the team, their profile remains in the database. Setting `is_active` to false hides them from the profile selector dropdown, but they remain queryable for audit purposes.

### Profile Creation API

```
POST /api/v1/reviewer-profiles
Body: { "display_name": "Alex" }
Response: { "id": "...", "display_name": "Alex", "avatar_color": "#4A90D9", "is_operator": false, "is_active": true, "created_at": "..." }
```

The server assigns the `id` and `avatar_color`. The client cannot specify these.

## Session Management

### First Visit Flow

1. User opens the app in a browser (e.g., `http://localhost:8000`).
2. The app checks for a session cookie. No cookie exists.
3. The app shows the "Who are you?" screen: a list of existing reviewer profiles (if any) and a "Create new profile" button.
4. If the user selects an existing profile, a session is created for that profile.
5. If the user creates a new profile, they enter a display name, the profile is created server-side, and a session is created.
6. The app redirects to the home screen.

### Session Cookie

- Cookie name: `molabel_session`
- Value: a signed token containing the reviewer `id` and `issued_at`. Signed with an application secret (auto-generated on first app launch, stored in `workbench/.molabel/app_secret`). The signature prevents cookie tampering (a reviewer cannot change their `id` by editing the cookie value).
- Flags: `HttpOnly` (not accessible to JavaScript), `SameSite=Strict` (not sent on cross-site requests), `Path=/`.
- `Secure` flag: NOT set (the app runs over plain HTTP on localhost). If HTTPS is configured, the flag should be set.
- Expiry: none (session cookie — persists until browser closes or user switches profiles). This is intentional: reviewers working on a local network should not be interrupted by session timeouts.

### Session Validation

On every API request:

1. Read the `molabel_session` cookie.
2. Verify the signature.
3. Extract the reviewer `id`.
4. Confirm the `id` exists in `reviewer_profiles`.
5. Update `last_active_at` for the profile (debounced to once per 60 seconds to avoid write amplification).
6. Attach the reviewer `id` to the request context for use by handlers.

If no valid session cookie is present, the server returns HTTP 401. The frontend redirects to the profile selection screen.

### Profile Switching

- A "Switch profile" button is always visible in the app header, showing the current display name and avatar color.
- Clicking it returns to the "Who are you?" screen.
- Switching profiles replaces the session cookie with a new one for the selected profile.
- Any in-progress work (unsaved draft reviews) is auto-saved to the database under the original profile before switching.
- Active queue claims held by the old profile are NOT automatically released on switch. They expire naturally via the claim timeout (see Queue Claim Model). This prevents accidental data loss if a reviewer switches profiles by mistake and switches back.

## Queue Claim Model

### Problem

Multiple reviewers pulling items from the same review queue must not receive the same item. The claim model ensures atomic, conflict-free item assignment.

### Claim Mechanics

When a reviewer requests the next item from a queue:

1. **Atomic claim**: The server executes a single SQL transaction:
   ```sql
   UPDATE review_tasks
   SET claimed_by = :reviewer_id,
       claimed_at = datetime('now'),
       status = 'claimed'
   WHERE id = (
       SELECT id
       FROM review_tasks
       WHERE queue_id = :queue_id
         AND status = 'available'
         AND claimed_by IS NULL
       ORDER BY priority DESC, created_at ASC
       LIMIT 1
   )
   RETURNING *;
   ```
   The `UPDATE ... WHERE ... (SELECT ... LIMIT 1)` pattern is atomic in SQLite — no two concurrent requests can claim the same row.

2. **Claim response**: The server returns the claimed review task with full record data, task schema, and any agent outputs (subject to blind review rules).

3. **No bulk claims**: A reviewer claims one item at a time. When they submit a review and request the next item, a new claim is made. This keeps queue distribution fair and responsive to changing reviewer pace.

### Claim Timeout

- Default timeout: 30 minutes (configurable per project in `workbench.project.yaml` under `review_settings.claim_timeout_minutes`).
- A background task runs every 60 seconds, checking for expired claims:
  ```sql
  UPDATE review_tasks
  SET claimed_by = NULL,
      claimed_at = NULL,
      status = 'available',
      claim_expired_count = claim_expired_count + 1
  WHERE claimed_by IS NOT NULL
    AND claimed_at < datetime('now', '-' || :timeout_minutes || ' minutes')
    AND status = 'claimed';
  ```
- When a claim expires, the item returns to the available pool and can be claimed by any reviewer (including the original one).
- The `claim_expired_count` field tracks how many times an item's claim has expired, for operational monitoring.

### Claim Expiry Notification

When a reviewer's claim expires:

1. The next time that reviewer makes any API call, the server checks if they had a recently expired claim.
2. If so, the API response includes a notification header: `X-MoLabel-Notification: claim_expired`.
3. The frontend displays a toast: "Your claim on [record summary] expired because your session was inactive for [N] minutes. The item has been returned to the queue."
4. If the reviewer was mid-review (had unsaved work), their draft is preserved in the `draft_labels` field on the `review_tasks` row. If they claim the same item again, the draft is restored.

### Claim Lifecycle

```
available → claimed → submitted
                   → available (claim expired; claim_expired_count incremented)
                   → skipped (→ available)
```

- **available**: item is in the queue, unclaimed, ready to be assigned. Items also return to this status when a claim expires.
- **claimed**: item is assigned to a reviewer. The reviewer has `claim_timeout` minutes to submit.
- **submitted**: the reviewer submitted a review event. The item leaves the queue.
- **skipped**: the reviewer explicitly skipped the item (e.g., clicked "Skip" without submitting). The item returns to `available`.

### Review Task Table Schema

```sql
CREATE TABLE review_tasks (
    id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    record_id TEXT NOT NULL REFERENCES records(id),
    task_schema_id TEXT NOT NULL REFERENCES task_schemas(id),
    dataset_id TEXT NOT NULL REFERENCES datasets(id),
    status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','claimed','submitted','skipped')),
    priority INTEGER NOT NULL DEFAULT 0,
    priority_reason TEXT,
    claimed_by TEXT REFERENCES reviewer_profiles(id),
    claimed_at TIMESTAMP,
    claim_expired_count INTEGER NOT NULL DEFAULT 0,
    is_overlap BOOLEAN NOT NULL DEFAULT FALSE,
    is_calibration BOOLEAN NOT NULL DEFAULT FALSE,
    draft_labels JSON,
    ai_revealed BOOLEAN NOT NULL DEFAULT FALSE,
    ai_revealed_at TIMESTAMP,
    submitted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_review_tasks_queue_status
    ON review_tasks(queue_id, status, priority DESC, created_at ASC);
CREATE INDEX idx_review_tasks_claimed_by
    ON review_tasks(claimed_by) WHERE claimed_by IS NOT NULL;
```

### Draft Preservation

Review drafts are stored as the `draft_labels` JSON field on the `review_tasks` table (see `data-model.md`). When a claim expires, `draft_labels` is preserved so the next reviewer can see the previous reviewer's partial work.

When a reviewer claims an item and `draft_labels` is non-null, the draft is loaded into the review form. Drafts are updated on every auto-save (debounced to every 10 seconds during active editing). `draft_labels` is cleared when a review is submitted.

## Security Considerations

### Threat Model

MoLabel assumes a trusted local network. The threat model is:

- **In scope**: accidental data loss, accidental identity confusion, concurrent access conflicts.
- **Out of scope**: malicious users, network eavesdropping, credential theft, privilege escalation.

### Known Limitations

1. **No authentication**: any user on the network can access the app by navigating to its URL. There is no login screen, no password, no API key.
2. **Self-selected identity**: reviewers choose their own display name. Nothing prevents a user from creating a profile with someone else's name. The UUID-based `id` prevents actual impersonation of review history, but the display name is misleading.
3. **No role-based access control**: the `is_operator` flag is advisory. Any reviewer can execute workflows, delete datasets, modify exports.
4. **No transport encryption**: the app runs over plain HTTP. Review data, session cookies, and API responses are transmitted in cleartext on the local network.
5. **No audit trail for identity changes**: if a reviewer changes their display name, the change is not recorded in the audit log (the old name is simply overwritten). The `id` remains stable, so audit queries by ID are unaffected, but queries by name may miss historical context.

### Mitigations

1. **Network binding**: the app binds to `0.0.0.0` by default (accessible from any machine on the local network) but can be configured to bind to `127.0.0.1` (localhost only) via `MOLABEL_HOST=127.0.0.1` environment variable. Localhost binding prevents all network access and is appropriate for single-user setups.

2. **Profile permanence**: reviewer profiles cannot be deleted. This ensures that the audit trail always has a valid reference for every review event, agent run, and adjudication decision. Profiles can be deactivated by setting `is_active` to false.

3. **Operator flag**: the `is_operator` flag exists in the data model. While not enforced initially, it allows future versions to add enforcement without a migration. The flag is visible in the UI — reviewers can see who is marked as an operator.

4. **Signed session cookies**: the session cookie is signed with an application secret. While this does not prevent a network attacker from stealing the cookie (no TLS), it prevents casual cookie tampering. A reviewer cannot promote themselves to operator by editing the cookie.

5. **Append-only review events**: review events cannot be modified or deleted through the API. Even if a malicious user gains access, they cannot erase or rewrite review history. They can only add new events.

### Future Authentication Path

The data model is designed to support future authentication without breaking changes:

- `id` is already a UUID, suitable as an external identity mapping target.
- The `reviewer_profiles` table can be extended with `auth_provider`, `external_id`, and `password_hash` columns.
- The session cookie mechanism can be replaced with JWT tokens from an auth provider.
- The `is_operator` flag can be enforced as a real RBAC role.
- A `reviewer_profile_changes` audit table can be added to track identity changes.

None of these changes require modifying the `review_events`, `agent_runs`, or `adjudications` tables — they all reference the reviewer `id` which remains stable.

## Multi-Session Behavior

### Concurrent Reviewers

MoLabel is designed for 2-10 concurrent reviewers on a local network. The design has been validated for this range. Scaling beyond 10 concurrent writers may require connection pooling or a move away from SQLite.

Concurrent reviewer behavior:

- Each reviewer has their own browser session and profile.
- Each reviewer sees their own queue position: how many items they have reviewed, how many remain, their average time per item.
- Reviewers do not see each other's in-progress work. They see only their own current item and their own progress.
- Mission control (accessible to operators) shows all active reviewer sessions: display name, avatar color, last active time, current queue, items completed in this session, average pace.

### Same-Profile Multi-Session

If two browser sessions use the same reviewer profile (same `id`):

1. Both sessions have valid session cookies and can make API calls.
2. If session A claims an item and session B claims the next item, both proceed independently.
3. If session A claims an item and session B also requests an item from the same queue, session B gets a different item (the claim is atomic).
4. If session A has a claimed item and session B submits a review for a different item, both succeed.
5. **Conflict case**: if session A has a claimed item and session B attempts to claim the same item (this can only happen if session A's claim expired and session B races for it), the atomic claim prevents double-assignment.
6. **Draft conflict**: if both sessions edit drafts for the same review task, last-write-wins applies. The `draft_labels` JSON field on the `review_tasks` row is updated on each auto-save. The later save overwrites the earlier one.
7. This scenario is logged as an audit warning: `{"type": "concurrent_same_profile", "id": "...", "session_count": 2}`. The warning is visible in mission control.

### Session Visibility in Mission Control

Mission control tracks active sessions via the `last_active_at` field on reviewer profiles:

- **Active**: `last_active_at` within the last 5 minutes.
- **Idle**: `last_active_at` between 5 and 30 minutes ago.
- **Offline**: `last_active_at` more than 30 minutes ago, or never set.

The mission control display includes:

| Reviewer | Status | Queue | Completed | Pace | Current Item |
|----------|--------|-------|-----------|------|-------------|
| Alex (blue) | Active | sentiment-v1 | 47 | 1.2/min | record-0492 |
| Jordan (green) | Idle | sentiment-v1 | 31 | 0.8/min | — (claim expired) |
| Sam (orange) | Active | sentiment-v1 | 52 | 1.5/min | record-0501 |

### SSE Event Streams

Real-time updates for multi-session coordination use Server-Sent Events:

- **Queue events** (`/api/v1/events/queue/{queue_id}`): emitted when items are claimed, submitted, skipped, or expired. Reviewers subscribed to a queue see updated counts and queue position. Notifications (e.g., claim expiry, queue completion) are delivered through this stream.
- **Workflow events** (`/api/v1/events/workflow/{execution_id}`): emitted for workflow state changes and step completions. Operators see real-time dashboard updates.
- **Provider events** (`/api/v1/events/providers`): emitted for provider status changes (availability, errors, model updates).

SSE connections are authenticated via the session cookie. A connection for a reviewer who is not logged in is rejected with HTTP 401.

## Queue Assignment Ordering

Items in a review queue are assigned based on priority and creation time:

1. **Priority** (descending): higher priority items are assigned first. Priority is set by the step that created the queue:
   - Active learning: low-confidence items get higher priority.
   - Calibration: calibration items get maximum priority.
   - Default: all items have priority 0 (FIFO by creation time).

2. **Creation time** (ascending): among items with the same priority, the oldest item is assigned first.

3. **Sticky assignment** (optional): if `config.sticky_assignment: true` on the review step, once a reviewer has been assigned items from a particular data subset (e.g., a specific source file or cluster), subsequent assignments prefer items from the same subset. This improves reviewer context and consistency. The stickiness is a soft preference — if no items from the preferred subset are available, any available item is assigned.

## Overlap Review

For overlap review (multiple reviewers review the same item):

1. The review step config specifies `config.overlap_count: N` (e.g., 2 for double review).
2. The queue contains N copies of each item (each with a unique `id` but the same `record_id`).
3. The claim mechanism ensures that the same reviewer does not claim two copies of the same record. The claim query adds: `AND record_id NOT IN (SELECT record_id FROM review_tasks WHERE queue_id = :queue_id AND claimed_by = :reviewer_id AND status IN ('claimed', 'submitted', 'skipped'))`.
4. Each reviewer independently reviews the item and submits their own review event.
5. When all N review tasks for a record are submitted, the record's overlap review is complete.
6. Disagreements between reviewers on the same record are detected by the `agreement_analysis` or `quality_check` steps and routed to adjudication if configured.
