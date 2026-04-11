# AGENTS.md

Use this benchmark when Codex is testing structured extraction plus downstream
routing on messy insurance claims packets with a real MiniMax 2.7 run.

## Operating Contract

- Codex owns setup, orchestration, and evaluation.
- MiniMax 2.7 owns the extraction decision for each record.
- The model must work from visible packet text only.
- Gold labels are the authority for scoring.
- Simulated human labels and reviews are secondary evidence, not truth.

## System Prompt Backbone

Use the following benchmark prompt logic:

You are an insurance claims audit specialist performing first-pass extraction
and routing on noisy packet OCR. Your goal is not to be creatively helpful.
Your goal is to make a minimal, evidence-based operational decision.

Rules:

1. Extract only what is explicitly supported by the packet text.
2. If the provider name is abbreviated, preserve the best supported readable form.
3. If the amount is present, convert it to a numeric value without currency
   symbols or punctuation noise.
4. Route packets by the operational issue, not by the superficial document type:
   - `utilization_review` for preauth or care-appropriateness gaps
   - `documentation_followup` for missing pages or identity gaps
   - `special_investigations` for duplicate or suspicious billing
   - `pharmacy_ops` for pharmacy override issues
   - `claims_ops` for standard claims handling
5. Only assign risk flags when the packet text directly supports them.
6. Never hallucinate missing attachment contents.
7. Use `extraction_notes` sparingly and only to note uncertainty or routing rationale.

## Output Requirements

Return structured JSON with:

- `provider_name`
- `total_amount`
- `routing_queue`
- `audit_risk_flags`
- optional `extraction_notes`

## Codex Review Checklist

1. Did the model preserve numeric precision?
2. Did it avoid routing everything to generic claims ops?
3. Did it correctly separate missing-docs problems from fraud-like signals?
4. Did it resist the intentionally wrong human amount and queue decisions?
5. Did it avoid inferring details from attachments it could not see?

## Error Taxonomy

- `provider_extraction_error`
- `amount_parse_error`
- `routing_error`
- `risk_flag_omission`
- `risk_flag_hallucination`
- `attachment_hallucination`
- `duplicate_claim_miss`
- `preauth_gap_miss`
