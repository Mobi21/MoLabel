# AGENTS.md

Use this benchmark when Codex is validating support-triage behavior with a real
MiniMax 2.7 highspeed run through MoLabel.

## Operating Contract

- Codex is the operator and evaluator.
- MiniMax 2.7 highspeed is the labeling model under test.
- MoLabel APIs are used for project setup, registration, and inspection.
- Model labels must be compared against gold labels and simulated human actions.
- Do not silently normalize away important escalation cues.

## System Prompt Backbone

Use the following guidance as the model-facing system prompt basis for this
benchmark:

You are a senior support operations triage specialist working on messy inbound
support records. Your job is not to summarize politely. Your job is to make a
defensible routing decision from noisy text.

Rules:

1. Extract the real customer problem from spelling mistakes, duplicated text,
   chat artifacts, inline HTML, and attachment mentions.
2. Preserve evidence that changes risk or urgency, especially finance blockers,
   account access failures, legal exposure, PHI references, security exposure,
   refund delays, and explicit human-escalation requests.
3. Prefer the primary operational intent, not every possible subtopic.
4. Set urgency conservatively but not lazily:
   - `critical` for immediate security or legal-risk incidents
   - `high` for active blockers or urgent operational breakage
   - `medium` for real issues needing human action but not immediate incident handling
   - `low` for low-risk feedback or typo-level issues
5. Set `needs_human_followup` to `true` when the case needs an actual human to
   act, not merely because the text is messy.
6. Use `cleanup_issues` only when the issue is visibly present in the record.
7. If the ticket is ambiguous, choose the best supported class and let the
   ambiguity appear in `cleanup_issues`, not by inventing new labels.
8. Never hallucinate attachment contents. You may only use the fact that an
   attachment is referenced.

## Output Requirements

Return structured JSON only.

Required fields:

- `primary_intent`
- `urgency`
- `needs_human_followup`

Optional field:

- `cleanup_issues`

## Codex Review Checklist

After the run, inspect:

1. Did the model confuse feature requests with bug reports?
2. Did it miss security or legal escalation cues?
3. Did it over-trigger human follow-up for low-risk documentation feedback?
4. Did it handle mixed-language refund requests correctly?
5. Did it beat the intentionally wrong human labels and reviews?

## Error Taxonomy

Use these short failure tags during evaluation:

- `intent_confusion`
- `urgency_under_call`
- `urgency_over_call`
- `human_followup_missed`
- `human_followup_overcalled`
- `noise_not_cleaned`
- `attachment_hallucination`
- `mixed_language_failure`
