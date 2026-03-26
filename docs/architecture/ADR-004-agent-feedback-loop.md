# ADR-004: Agent Feedback Loop

**Date:** 2026-03-23
**Status:** Accepted
**Supersedes:** Original PRD one-shot agent labeling model

## Context

The original PRD treated LLM agents as stateless workers: configure a prompt, run the agent on the dataset, review the outputs, done. If quality was insufficient, the user would manually tweak the prompt and re-run. There was no systematic mechanism for agents to improve from human corrections.

This is a significant missed opportunity. In a labeling workbench, human reviewers generate a rich stream of correction signals every time they accept, modify, or reject an agent's output. These corrections encode exactly what the agent is getting wrong and how to fix it. A modern labeling tool should close this loop.

Three complementary strategies are needed:

1. **Prompt refinement:** Use accumulated corrections to systematically improve the agent's prompt, rather than relying on ad-hoc manual tweaking.
2. **Active learning:** Prioritize human review effort on the items where it will have the most impact, rather than reviewing random or sequential samples.
3. **Performance analytics:** Give users visibility into how the agent is performing, where it's failing, and whether it's improving over time.

## Decision

Implement a **hybrid agent feedback loop** combining prompt refinement, active learning, and performance analytics as first-class features of the labeling workflow.

### Prompt Refinement

Human corrections accumulate in the project's correction store (`workbench/prompts/corrections/`). Each correction records the original agent output, the human's corrected output, and optional annotator notes explaining the correction.

When the correction count reaches a configurable batch threshold (default: 25 corrections per batch), the system performs a **correction analysis**:

1. **Pattern extraction:** Group corrections by error type (wrong label, missing field, hallucinated value, format error, boundary error, etc.) and by data characteristics (record length, domain, complexity).
2. **Refinement generation:** Based on the patterns, generate candidate prompt refinements:
   - **Few-shot examples:** Select the most representative correction pairs as new few-shot examples for the prompt.
   - **Instruction patches:** Generate natural-language instruction additions that address systematic errors (e.g., "When the text contains sarcasm, pay attention to the overall sentiment rather than individual positive words").
   - **Rubric clarifications:** Identify ambiguous areas in the labeling rubric where the agent consistently disagrees with humans, and propose rubric clarifications.
3. **User review:** Refinements are presented to the user for review. The user can accept, modify, or reject each refinement. Nothing is applied automatically. The user maintains full control over what the agent is told.
4. **Application:** Accepted refinements are incorporated into a new prompt version (see prompt management below). The next agent run uses the refined prompt.

The batch threshold is configurable per project because correction density varies. A project with 10 labels might need 50 corrections per batch to see clear patterns, while a binary classification task might show patterns after 10.

### Active Learning

Not all records benefit equally from human review. Active learning prioritizes human effort on records where review will be most informative.

**Multi-signal confidence scoring** combines three signals when available:

| Signal | Source | Description |
|--------|--------|-------------|
| Self-reported confidence | Agent prompt | The agent is asked to rate its own confidence (1-5 or 0.0-1.0) as part of its structured output |
| Self-consistency | Multiple runs | The same record is labeled N times (default: 3) with temperature > 0. Consistency across runs indicates confidence |
| Logprobs | Provider API | When the provider exposes token-level log probabilities (OpenAI, some Ollama models), these provide a direct confidence signal |

These signals are combined into a composite confidence score with configurable weights. By default, self-consistency is weighted highest because it is the most reliable and universally available signal.

**Prioritization strategies** use the confidence scores to select records for human review:

- **Low-confidence first:** Review the least confident records. Maximizes correction signal per review.
- **Uncertainty sampling:** Review records near the decision boundary. Most useful for classification tasks.
- **Stratified sampling:** Ensure review coverage across confidence bands, labels, and data segments. Prevents blind spots.
- **Disagreement-first:** When multiple agent runs exist (from `agent_compare`), prioritize records where agents disagree.

### Performance Analytics

Every agent run produces detailed performance data that feeds into analytics dashboards:

**Per-field accuracy** (when human labels are available):
- Exact match accuracy, partial match (for text fields), label-level precision/recall/F1
- Broken down by label value, record complexity, data segment

**Trends over time:**
- Accuracy by prompt version, showing whether refinements are improving performance
- Agreement rate between agent and human, tracked across workflow iterations
- Throughput: records labeled per minute, with cost breakdown

**Error analysis:**
- Most common error patterns (which labels are confused with which)
- Systematic biases (does the agent over-predict certain labels?)
- Data characteristics correlated with errors (record length, domain, language)

**Confidence calibration:**
- Calibration curve: does the agent's stated confidence match its actual accuracy?
- Over/under-confidence detection with recommendations

**Cost tracking:**
- Cost per label (total API cost / labels produced)
- Cost per correct label (factoring in error rate)
- Cost comparison across models and prompt versions

### Prompt Management

Prompts are elevated to **first-class versioned project artifacts**, stored as YAML files in `workbench/prompts/`:

```
workbench/prompts/
  sentiment-v1.yaml         # base template
  sentiment-v2.yaml         # after first refinement batch
  sentiment-v3.yaml         # after second refinement batch
  corrections/
    batch-001.yaml          # first 25 corrections
    batch-002.yaml          # next 25 corrections
```

**Key properties of prompt management:**

- **Immutable once used:** Once a prompt version is used in an agent run, it is frozen. Edits create a new version. This ensures full reproducibility: any agent output can be traced back to the exact prompt that produced it.
- **Composable structure:** A prompt is composed of layers:
  - **Base template:** The core instructions and output schema definition.
  - **Task rubric:** Labeling guidelines, definitions, edge cases.
  - **Few-shot examples:** Correction-derived examples showing input/output pairs.
  - **Instruction patches:** Targeted instructions addressing specific error patterns.
- **Automatic versioning:** When the user accepts prompt refinements, the system creates a new version with a clear diff from the previous version. The user can see exactly what changed.
- **Correction batches:** Stored as structured YAML with the original output, corrected output, error category, and optional notes. These are the raw material for prompt refinement.

### Structured Output

Reliable structured output from LLMs is critical for a labeling tool. The system uses a **provider-native first, fallback second** approach:

1. **Provider-native structured output** (preferred): Use the provider's built-in structured output mechanism when available:
   - OpenAI: `response_format` with JSON schema
   - Anthropic: `tool_use` with schema definition
   - Ollama: `format: json` with schema
   - Other providers: check for structured output support at runtime

2. **Fallback: prompt-based JSON:** When the provider doesn't support structured output, the schema is included in the prompt with explicit JSON formatting instructions.

3. **Validation:** All outputs are validated against the task's JSON schema regardless of how they were obtained.

4. **Auto-retry:** On validation failure, the system retries up to 3 times with the validation error included in the retry prompt. If all retries fail, the record is flagged as `agent_error` for human review.

## Alternatives Considered

- **No feedback loop (original PRD):** Treat agents as one-shot workers. Rejected because it wastes the correction signals generated by human review and leaves users to manually iterate on prompts by trial and error.

- **Automatic prompt application (no user review):** Apply refinements automatically without user approval. Rejected because prompt changes can have unexpected effects. Users must maintain control over what their agent is told, especially in high-stakes labeling scenarios.

- **Fine-tuning instead of prompt refinement:** Use corrections to fine-tune the model. Rejected because fine-tuning requires provider-specific APIs, significant data volumes, and compute costs. Prompt refinement is immediate, transparent, and works with any model. Fine-tuning support can be added as a future enhancement for users with large correction libraries.

- **Full RLHF pipeline:** Build a reinforcement learning from human feedback loop. Rejected as wildly overscoped for a labeling tool. RLHF modifies model weights; MoLabel should improve prompts, not models.

- **Correction-based few-shot only (no pattern analysis):** Simply append correction examples to the prompt without analyzing patterns. Rejected because prompts have limited context windows. Intelligent selection of representative examples and extraction of general rules is more token-efficient and more effective than dumping all corrections into the prompt.

## Consequences

1. **Prompts as project artifacts:** Prompts are no longer disposable configuration; they are versioned, auditable artifacts central to the project. The UI needs a dedicated prompt management surface.

2. **Correction library as a new data type:** Corrections accumulate as a structured dataset. They need storage, browsing, searching, and export capabilities. They are valuable training data in their own right.

3. **Agent performance data volume:** Every agent run produces detailed per-record performance data. This needs efficient storage (likely in the project's SQLite database) and indexed querying for analytics dashboards.

4. **Confidence scoring cost:** Self-consistency scoring requires multiple agent runs per record (default 3x). This multiplies API costs. Users must be able to configure this: disable self-consistency, reduce runs to 2, or use it only for a sample. The system should present the cost tradeoff clearly.

5. **Prompt refinement quality depends on correction quality:** If human reviewers make inconsistent or incorrect corrections, the refinement system will produce poor suggestions. The calibration step type (from ADR-003) helps mitigate this by aligning reviewers before full review.

6. **Analytics dashboard scope:** The performance analytics described here are a significant frontend feature. They require the charting capabilities outlined in ADR-001 (Recharts) and will be a major surface in the application.
