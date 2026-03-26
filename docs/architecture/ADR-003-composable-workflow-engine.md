# ADR-003: Composable Workflow Engine

**Date:** 2026-03-23
**Status:** Accepted
**Supersedes:** Original PRD fixed 12-step lifecycle (Ingest, Normalize, Schema, Pre-Label Import, Agent Labeling, Review, Adjudication, Quality Check, Export, Snapshot, Iterate, Monitor)

## Context

The original PRD defined a fixed 12-step lifecycle that every labeling project would follow in sequence. While this provides a clear mental model, it fails in practice because labeling projects are fundamentally diverse:

- **Quick agentic labeling:** An experienced user wants to run an agent on a clean dataset, spot-check a sample, and export. They don't need calibration, adjudication, or multi-round review. The fixed lifecycle forces them through irrelevant steps.
- **High-stakes annotation:** A medical NLP team needs multiple rounds of human review, inter-annotator agreement analysis, adjudication of disagreements, and only then agent-assisted labeling of the remaining items. The fixed lifecycle puts agent labeling before human review.
- **Benchmark creation:** A researcher wants to establish ground-truth labels through expert consensus, then evaluate multiple models against that benchmark. The fixed lifecycle doesn't support this workflow at all.
- **Iterative refinement:** A team wants to run an agent, review the worst-performing items, refine the prompt, re-run, and loop until quality targets are met. The fixed lifecycle treats iteration as an afterthought.
- **Agent comparison:** A user wants to run three different models on the same data and compare their outputs before choosing one. The fixed lifecycle supports only one agent run.

A fixed lifecycle cannot accommodate this variety without becoming a leaky abstraction full of skip flags and conditional branches bolted on after the fact.

## Decision

Replace the fixed lifecycle with a **fully composable workflow engine** where users build workflows from discrete step types.

### Workflow Definition

Workflows are defined as **YAML files** stored in the project directory (`workbench/workflows/`). YAML was chosen over a database representation because:

- Workflows are version-controllable alongside the project data.
- Users can copy, diff, and share workflow definitions as plain files.
- YAML is human-readable for debugging and auditing.
- The GUI workflow builder (React Flow, per ADR-001) generates and reads YAML, so users never have to write YAML by hand unless they want to.

Example workflow structure:

```yaml
name: "Human-in-the-Loop Review"
version: 1
description: "Agent labels with human review and refinement loop"
steps:
  - id: ingest
    type: data_ingest
    config:
      source: "data/raw/*.jsonl"

  - id: normalize
    type: data_normalize
    config:
      schema_ref: "schemas/sentiment.yaml"

  - id: agent_label
    type: agent_run
    config:
      prompt_ref: "prompts/sentiment-v1.yaml"
      model: "claude-sonnet-4-20250514"

  - id: review
    type: human_review
    config:
      sample_strategy: "low_confidence"
      sample_size: 100
      breakpoint: true

  - id: quality
    type: quality_check
    config:
      min_agreement: 0.85
      min_coverage: 0.95

  - id: refinement_loop
    type: loop
    config:
      steps: [agent_label, review, quality]
      termination:
        type: metric
        metric: "quality.agreement"
        threshold: 0.90
        max_iterations: 5

  - id: export
    type: export
    config:
      format: "jsonl"
      destination: "exports/"
```

### Step Type Catalog

Steps are organized into 6 categories with ~20 step types:

**Data**
| Step Type | Purpose |
|-----------|---------|
| `data_ingest` | Load data from files, HuggingFace, or import formats |
| `data_normalize` | Map source fields to task schema |
| `data_filter` | Filter records by field values, metadata, or quality signals |
| `data_sample` | Draw stratified, random, or confidence-based samples |
| `data_deduplicate` | Remove or flag duplicate/near-duplicate records |

**Agent**
| Step Type | Purpose |
|-----------|---------|
| `agent_run` | Run an LLM agent on records using a prompt template |
| `agent_compare` | Run multiple agents/models and collect outputs side-by-side |

**Human**
| Step Type | Purpose |
|-----------|---------|
| `human_review` | Human reviews agent outputs, accepts/corrects/rejects |
| `human_triage` | Quick pass/fail sorting of records for downstream routing |
| `human_calibration` | Annotator alignment session on a shared sample before full review |
| `human_adjudication` | Resolve disagreements between reviewers or between human and agent |

**Quality**
| Step Type | Purpose |
|-----------|---------|
| `quality_check` | Evaluate labels against quality metrics (agreement, coverage, confidence) |
| `agreement_analysis` | Compute inter-annotator or human-agent agreement statistics |
| `drift_detection` | Detect distribution shifts between data subsets or over time |

**Output**
| Step Type | Purpose |
|-----------|---------|
| `export` | Export labeled data in configured format |
| `snapshot` | Capture full project state at a point in time |
| `release_validation` | Run final checks before marking a dataset as release-ready |

**Control**
| Step Type | Purpose |
|-----------|---------|
| `loop` | Repeat a sequence of steps until a termination condition is met |
| `conditional` | Branch execution based on metric values or data properties |
| `parallel` | Run multiple steps concurrently (e.g., multiple agent runs) |
| `gate` | Pause execution and require explicit user approval to continue |

### Loop Termination Strategies

Loops are a first-class concept with four termination strategies:

- **Count-based:** Run exactly N iterations. Simple and predictable.
- **Metric-based:** Run until a quality metric (agreement, accuracy, coverage) crosses a threshold. The most common strategy for iterative refinement.
- **Coverage-based:** Run until a target percentage of records have been reviewed/labeled. Useful for human review loops.
- **Manual:** Run until the user explicitly stops the loop. Useful for exploratory workflows.

All loop types have a `max_iterations` safety limit to prevent runaway execution.

### Execution Model

Workflows execute as a **hybrid automatic/manual** system:

- By default, steps execute automatically in sequence.
- Any step can have `breakpoint: true` in its config, which pauses execution before that step and requires user confirmation to proceed.
- Human steps (`human_review`, `human_triage`, `human_calibration`, `human_adjudication`) always pause for user interaction by their nature.
- Gate steps (`gate`) are explicit pause points.
- Users can pause, resume, or cancel a running workflow at any time from the mission control dashboard.
- Step execution state is persisted, so workflows survive application restarts.

### Built-in Templates

Six templates provide starting points that cover the most common workflows:

1. **Quick Agentic Label:** Ingest, agent run, spot-check sample, export. Minimal human involvement.
2. **Human-in-the-Loop Review:** Ingest, agent run, human review, quality check, refinement loop, export.
3. **Full Quality Pipeline:** Ingest, calibration, agent run, human review, agreement analysis, adjudication, quality check, export, release validation.
4. **Benchmark Authority:** Ingest, multi-round expert review, adjudication, agreement analysis, snapshot as ground truth.
5. **Agent Comparison:** Ingest, parallel agent runs (multiple models), side-by-side human review, comparison analytics, select best, export.
6. **Iterative Refinement:** Ingest, agent run, low-confidence review, prompt refinement, loop until quality target, export.

The original PRD's fixed 12-step lifecycle maps approximately to the "Full Quality Pipeline" template. Users who want that linear experience can start from that template.

## Alternatives Considered

- **Fixed lifecycle with skip flags (enhanced PRD approach):** Add `skip: true` to steps in the existing 12-step lifecycle. Rejected because it doesn't support reordering, looping, branching, or parallel execution. Skipping steps still implies they exist, creating a confusing mental model.

- **Prefect/Airflow-style DAG engine:** Use an existing workflow orchestration framework. Rejected because these are designed for data engineering pipelines (batch ETL, scheduled jobs), not interactive human-in-the-loop workflows. They lack concepts like breakpoints, human review steps, and real-time intervention. They also add heavyweight dependencies.

- **Code-first workflow definition (Python DSL):** Define workflows as Python code using decorators or a builder API. Rejected because it excludes non-developer users from workflow creation and makes the GUI builder harder to implement (generating Python code from a visual editor is more complex than generating YAML).

- **Visual-only workflow definition (no YAML):** Store workflows only as GUI state in the database. Rejected because it prevents version control, command-line manipulation, and sharing workflows as files. YAML is the source of truth; the GUI is a view over it.

## Consequences

1. **Core architectural component:** The workflow engine (`molabel-core`) becomes the central abstraction of the system. Most features are implemented as step types that plug into the engine.

2. **Parameterized testing:** The workflow engine needs thorough testing with diverse workflow configurations. Approximately 15 workflow fixture YAMLs should cover: linear workflows, loops with each termination strategy, conditionals, parallel steps, nested loops, error handling, breakpoint behavior, and each built-in template.

3. **Step type extensibility:** New step types can be added by plugins (per the plugin architecture). Each step type is a Python class implementing a defined interface with `validate()`, `execute()`, and `render_config_schema()` methods.

4. **Migration from fixed lifecycle:** Existing users (if any, during early development) would need their projects migrated from the fixed lifecycle to an equivalent workflow YAML. Since MoLabel is pre-release, this is not a practical concern.

5. **Workflow versioning:** Workflows are versioned in their YAML (`version: N`). When a user edits a workflow that has already been executed, the engine creates a new version rather than mutating the existing one, preserving audit history.

6. **Complexity budget:** A composable workflow engine is more complex to implement and test than a fixed lifecycle. This is accepted as necessary complexity: the fixed lifecycle was simpler to build but would have been a constant source of user friction and feature requests.
