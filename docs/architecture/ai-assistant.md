# AI Assistant Architecture

Date: 2026-03-23
Status: Draft
Related: PRD Sections 15.10-15.10.1, UX Strategy Sections 9, 11

## Overview

The supportive AI assistant is a workflow-aware guide that helps users understand their current context, explains blockers, recommends next actions, and answers questions grounded in project state. It is NOT a generic chatbot — it is deeply integrated with the workflow engine, queue system, and project data.

The assistant occupies a specific role in MoLabel's three-actor model:

- **AI guide** — the assistant (narrator, supervisor, explainer)
- **AI workers** — external agents (labeling, normalization, deduplication)
- **Human authority** — the user (decisions, adjudication, release)

The assistant never replaces human judgment silently, never auto-hides process complexity, and never obscures what files and outputs actually changed.

## Architecture

### Provider Integration

- Uses the user's own configured model profiles (same providers used for agent runs)
- User selects which model profile powers the assistant in Settings
- If the configured provider is unavailable, the assistant shows "Assistant unavailable — provider offline" rather than failing silently
- Can be disabled entirely in project settings
- No bundled model — the assistant is only available when the user has at least one working model provider configured

### Context Assembly Pipeline

The assistant context is assembled server-side before each query. A dedicated context builder pulls from SQLite operational state and cached metrics to construct a focused context window.

```python
class AssistantContextBuilder:
    """Assemble focused context for the assistant.

    Pulls from SQLite state, cached metrics, and current UI context
    to build a token-budgeted context window for the user's chosen model.
    """

    def build_context(
        self,
        query: str,
        screen: str,
        record_id: str | None,
    ) -> AssistantContext:
        ...
```

Context sources are assembled in priority order, each with a token budget:

| Priority | Source | Budget | Description |
|----------|--------|--------|-------------|
| 1 | System prompt with mode instructions | ~500 tokens | Always included. Sets behavioral rules and current mode. |
| 2 | Current screen and workflow state | ~200 tokens | Current screen name, active workflow step, execution status. |
| 3 | Queue statistics | ~200 tokens | Pending/completed/blocked counts, reviewer's position in queue. |
| 4 | Active blockers | ~300 tokens | What is blocking workflow progress, validation failures, missing inputs. |
| 5 | Recent agent runs | ~500 tokens | Last 3-5 runs with status, accuracy summary, model used. |
| 6 | Validation gate statuses | ~200 tokens | Which gates pass/fail, what is required for next stage. |
| 7 | Record context | ~500 tokens | If user is asking about a specific record: its data, labels, agent outputs, review history. |
| 8 | Project summary | ~200 tokens | Dataset sizes, task schemas, overall progress percentages. |

**Total budget: ~2600 tokens of context**, leaving room for the user's query and model response within a **4000-token input budget**. This budget is designed to keep per-query costs under $0.01 for most providers.

If total context exceeds the budget, lower-priority sources are truncated or omitted. The system never silently drops the system prompt or workflow state (priorities 1-2).

### Mode Detection

The assistant operates in five modes. Mode is auto-detected from the user's query and current screen context:

| Mode | Trigger Examples | Current Screen Hints | Behavior |
|------|-----------------|---------------------|----------|
| Guide | "What should I do?", "What's next?", "Help" | Home, dashboard, workflow overview | Recommends next action based on workflow state and blockers |
| Explain | "What does X mean?", "Why is this...", "Explain" | Any screen | Explains labels, metrics, workflow steps, or system concepts |
| Operator | "Run...", "Export...", "Start...", "Create queue" | Workflow, agent, export screens | Helps prepare actions (does NOT auto-execute) |
| Agent Monitor | "How is the agent doing?", "What happened?" | Agent run, mission control screens | Explains agent behavior, performance, errors, outputs |
| Troubleshoot | "Why did this fail?", "What's wrong?", "Fix" | Error states, failed validation screens | Diagnoses failed jobs, validation failures, missing plugins |

Mode detection uses keyword matching plus current screen context. If ambiguous, the system defaults to **Guide mode**, which is the safest and most generally useful mode.

### System Prompt Structure

```
You are MoLabel's workflow assistant. You help users understand their
data labeling project and take the right next action.

Current mode: {detected_mode}
Current screen: {screen_name}
Project: {workspace_name}

RULES:
- Always ground your answers in the provided context
- Never fabricate data, metrics, or statuses
- When recommending actions, explain WHY
- Never auto-execute actions — only prepare and suggest
- If you don't have enough context to answer, say so
- Never replace human judgment silently
- Never obscure what files and outputs actually changed

CONTEXT:
{assembled_context}
```

The system prompt is constant across all modes except for the `{detected_mode}` field, which adjusts the model's focus. Mode-specific behavioral instructions are appended to the RULES section when a mode other than Guide is detected.

### Conversation History

- The assistant maintains conversation history within a session (up to last 5 exchanges)
- History is stored in browser memory (not persisted to database)
- Each new screen navigation resets the conversation context but preserves history within the session
- History is included in the context window and counts against the token budget
- When history would exceed its token allocation, oldest exchanges are dropped first

### Error Handling

| Condition | User-Facing Behavior |
|-----------|---------------------|
| Provider timeout | "Response timed out — try again or switch to a different model" |
| Provider rate limit | "Rate limited — wait a moment and try again" |
| Provider offline / unreachable | "Assistant unavailable — provider offline" |
| Context assembly failure | Show raw context summary without AI interpretation |
| Invalid / unparseable response | "I couldn't generate a helpful response for that question" |
| No model profile configured | "No model profile selected — configure one in Settings to use the assistant" |

All errors are non-blocking. The assistant panel shows the error state but the rest of the application continues to function normally.

### Cost Control

- Each assistant query uses the user's configured provider and counts against their API costs
- The context budget (4000 tokens input) is designed to keep per-query costs under $0.01 for most providers
- Usage is tracked in the cost tracking system alongside agent run costs
- The assistant panel shows estimated cost per query
- No background queries — the assistant only calls the provider when the user explicitly asks a question

### API Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/assistant/query` | POST | Sends user question with screen context, receives streaming response |
| `/api/v1/assistant/context` | GET | Returns current assembled context summary (for debugging/transparency) |

The assistant response is streamed via SSE within the POST response body (not a separate SSE endpoint). This keeps the API surface simple and avoids managing separate streaming connections.

Request payload for `/api/v1/assistant/query`:

```json
{
  "query": "Why is this export blocked?",
  "screen": "exports.detail",
  "record_id": null,
  "session_history": [
    {"role": "user", "content": "What should I do next?"},
    {"role": "assistant", "content": "..."}
  ]
}
```

## UI Integration

The assistant lives in the right-side inspector panel (not a floating chat bubble):

- **Collapsed by default** — does not consume screen space until needed
- **Expands** when user clicks the assistant icon or presses `Cmd+/`
- **Suggested questions** shown based on current screen context (e.g., "What's blocking this export?" on the export screen)
- **Response area** supports markdown rendering for structured answers
- **"Show context" toggle** for transparency — shows what data the assistant can see, so users understand grounding
- **Cost indicator** shows estimated cost of the last query

The assistant does not:

- Float over content as a chat bubble
- Auto-open or interrupt the user
- Show notifications or badges demanding attention
- Persist conversation across app restarts

## Relationship to External Agents

The assistant and external agents (labeling agents, normalization agents, etc.) are separate concerns:

- The assistant **explains** what agents did, how they performed, and what to do about failures
- The assistant **does not** directly invoke agents or execute agent runs
- The assistant **can help prepare** agent run configurations (Operator mode) but the user must confirm execution
- Agent status and results flow into the assistant's context assembly pipeline as read-only data

This separation ensures the assistant remains a narrator and supervisor, not an uncontrolled actor in the system.
