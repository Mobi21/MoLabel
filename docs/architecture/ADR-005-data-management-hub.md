# ADR-005: Data Management Hub

**Date:** 2026-03-23
**Status:** Accepted
**Supersedes:** Original PRD basic data explorer and dataset operations

## Context

The original PRD described a "Data Explorer" as a table view with filtering and sorting, and "Dataset Operations" as a collection of import/export utilities. While functional, this underestimates the role of data management in a labeling workbench.

Real-world labeling projects have complex data management needs that go beyond browsing rows in a table:

- **Pre-label visibility:** Teams often have existing labels from previous tools (Label Studio, Prodigy, Argilla), model predictions, or external annotators. These need to be imported, mapped to the current schema, and displayed alongside new agent and human labels -- not silently overwritten or ignored.
- **Record-level context:** When reviewing a label, the reviewer needs to see everything about that record: the source data, all agent outputs from all runs, all human reviews, the adjudication decision, quality signals, and how it arrived at its current state. A flat table cannot provide this.
- **Cross-dataset analysis:** Projects often involve multiple datasets (training, validation, test splits; multiple domains; different time periods). Users need to compare label distributions, detect drift, and ensure consistency across datasets.
- **Point-in-time recovery:** Labeling is an iterative process. Users need to capture snapshots of the full project state at meaningful points (before a major agent re-run, before export, after a review round) and compare or restore them.
- **Data source diversity:** Real data comes from many sources. A labeling tool that only reads CSV files forces users to do data preparation outside the tool, breaking the workflow.

## Decision

Elevate data management from a basic explorer to a **full data management hub** with three interconnected surfaces, plus snapshot and pre-label subsystems.

### Surface 1: Dataset Catalog

The catalog is the entry point for data management. It provides a project-wide view of all datasets:

| Column | Description |
|--------|-------------|
| Name | Dataset identifier |
| Source | Where the data came from (local file, HuggingFace, import) |
| Records | Total record count |
| Labeled | Count and percentage of records with at least one label |
| Health | Summary quality indicator (green/yellow/red) based on coverage, agreement, and freshness |
| Last Updated | When the dataset was last modified (data change, new labels, or new agent run) |
| Actions | Direct links to explorer, review queue, export, analytics |

The catalog supports:
- **Grouping** by source, status, or custom tags
- **Search** across dataset names and metadata
- **Bulk operations** (export multiple datasets, apply filters across datasets, merge datasets)
- **Dataset creation** from file upload, HuggingFace search, or import from other tools

### Surface 2: Record Inspector (360-View)

For any single record, the inspector provides a complete view of its lifecycle:

**Source Data Panel:**
- Original source fields as ingested
- Normalized fields mapped to the task schema
- Source metadata (file, line number, import timestamp)

**Labels Panel:**
- All pre-labels (imported labels from external sources) with source attribution and trust level
- All agent outputs from every agent run, with prompt version, model, confidence score, and timestamp
- All human review events with reviewer ID, decision (accept/correct/reject), corrected values, and notes
- Adjudication decision (if applicable) with rationale

**Quality Panel:**
- Per-field agreement across all label sources
- Confidence score breakdown (self-reported, self-consistency, logprobs)
- Drift flags (if this record's labels are outliers relative to similar records)
- Export eligibility (whether this record meets export quality thresholds)

**Lineage Panel:**
- Complete chronological history of everything that has happened to this record
- Which workflow steps have processed it and when
- Which prompt versions were used for agent labeling
- Which review rounds included it

The inspector is accessible from the data explorer (click any row), the review queue (see full context while reviewing), and the quality dashboard (drill into flagged records).

### Surface 3: Dataset Analytics

Dataset-level analytics provide insight into label quality and distribution:

**Label Distribution:**
- Bar/pie charts showing label value distribution per field
- Comparison across datasets (e.g., training vs. validation distribution)
- Comparison across label sources (agent vs. human vs. pre-label distribution)

**Quality Metrics:**
- Inter-annotator agreement (Cohen's kappa, Krippendorff's alpha) where multiple human annotators exist
- Human-agent agreement rates by field and label value
- Coverage: percentage of records labeled, reviewed, adjudicated, export-ready
- Quality trend over time (by workflow iteration)

**Drift Detection:**
- Label distribution comparison between data subsets (temporal, source-based, or custom splits)
- Statistical tests for distribution shift (chi-squared, KL divergence)
- Visual drift alerts when distributions diverge beyond a configurable threshold

**Pre-Label Analysis:**
- Agreement between pre-labels and new labels (agent or human)
- Pre-label accuracy (when human-reviewed labels are available as ground truth)
- Mapping coverage: what percentage of pre-label fields mapped to the current schema

### Pre-Labels

Pre-labels are existing labels imported from external sources. They are treated as a specific type of review event rather than a separate data structure:

```yaml
type: review_event
source: import
source_system: "label-studio"
source_file: "label-studio-export-2026-03-15.json"
trust_level: expert      # one of: ground_truth, expert, external, untrusted
labels:
  sentiment: positive
  confidence: 0.92
unmapped_fields:
  annotator_id: "user-47"
  annotation_time_ms: 3400
```

**Trust levels** determine how pre-labels interact with the rest of the system:

| Trust Level | Description | Behavior |
|-------------|-------------|----------|
| `ground_truth` | Known-correct labels (gold standard) | Used as reference for agent accuracy measurement. Not queued for re-review. |
| `expert` | High-quality labels from domain experts | Weighted heavily in agreement calculations. Optional re-review. |
| `external` | Labels from external annotators or models | Treated as a data point but not authoritative. Queued for review by default. |
| `untrusted` | Noisy labels (crowd-sourced, legacy, unknown quality) | Displayed for reference only. Not used in quality calculations unless explicitly opted in. |

**Label mapping** handles schema mismatches between imported labels and the current task schema:

- A visual mapping editor lets users map source fields to task schema fields.
- For categorical fields, a value mapping table maps source label values to task label values (e.g., "pos" maps to "positive").
- Unmapped source fields are preserved as reference-only fields, visible in the Record Inspector but not used in quality calculations or export.
- The mapping is stored as a reusable mapping configuration, so importing from the same source again uses the same mapping.

### Snapshots

Snapshots capture the complete state of a project at a point in time:

**What a snapshot includes:**
- All record labels (agent outputs, human reviews, adjudication decisions)
- All quality metrics at the time of snapshot
- Dataset membership (which records are in which datasets)
- Workflow state (which steps have run, their configurations)
- Prompt versions in use
- Project configuration

**Storage model:** Snapshots are stored as lightweight delta references rather than full copies. The first snapshot is a full capture; subsequent snapshots store only the changes since the last snapshot. This keeps storage manageable even for large projects with frequent snapshots.

**Snapshot operations:**
- **Create:** User-triggered from the UI or from a workflow step (`snapshot`).
- **Browse:** List all snapshots with timestamp, description, and summary stats (record count, label count, quality metrics).
- **Compare (diff):** Select two snapshots and see what changed: new records, changed labels, quality metric changes, dataset membership changes.
- **Restore:** Roll back to a previous snapshot. This creates a new snapshot of the current state first (so restoration is non-destructive), then applies the historical state.

### Data Sources

MoLabel supports the following data sources:

**Local files:**
- CSV (with configurable delimiter, quoting, encoding)
- JSONL (one JSON object per line)
- Parquet (columnar format, efficient for large datasets)
- JSON (array of objects)
- YAML (array of objects)
- Markdown (structured documents with frontmatter)

**HuggingFace datasets:**
- Browse and search HuggingFace Hub datasets
- Stream large datasets without downloading the full file
- Support for dataset splits (train, validation, test)
- Authentication via HuggingFace token for private datasets

**Import from labeling tools:**
- Label Studio JSON export format
- Argilla export format
- Prodigy JSONL export format
- Generic annotation format (configurable field mapping)

**Future (via plugins):** Cloud storage (S3, GCS, Azure Blob), databases (PostgreSQL, BigQuery), APIs, and additional labeling tool formats. The data source interface is designed for extensibility from the start.

## Alternatives Considered

- **Basic data table (original PRD):** A flat table with sorting and filtering. Rejected because it cannot provide record-level context, cross-dataset analysis, or snapshot capabilities. Users would need external tools for data analysis, breaking the integrated workflow.

- **Embedded Jupyter notebooks:** Provide data analysis via embedded notebooks. Rejected because it fragments the UX (switching between a labeling interface and a notebook), requires users to write Python for basic analysis, and doesn't integrate with the workflow engine.

- **External database (PostgreSQL):** Store all data in an external PostgreSQL database for richer querying. Rejected because it violates the local-first principle (users would need to install and manage PostgreSQL) and adds deployment complexity. SQLite with well-designed indexes can handle the query patterns MoLabel needs at the data volumes typical of labeling projects (thousands to low millions of records).

- **Git-based versioning instead of snapshots:** Use git to version the project data. Rejected because git is not efficient for large binary data or databases, and it would require users to understand git for what should be a simple "save checkpoint" operation. Snapshots are a simpler, purpose-built abstraction.

- **No pre-label import (clean start only):** Require users to start labeling from scratch. Rejected because most real projects have existing labels from previous efforts, and ignoring them wastes significant prior work. Pre-labels are one of MoLabel's key differentiators over simpler tools.

## Consequences

1. **Significant product surface:** Data management becomes one of the three main areas of the application (alongside workflow management and review/labeling). It requires substantial frontend development across three surfaces plus the snapshot and pre-label subsystems.

2. **Label mapping is ETL-like:** The pre-label mapping editor is essentially a lightweight ETL (extract-transform-load) tool for label data. This is a moderately complex feature that needs careful UX design to be usable by non-technical users.

3. **Snapshot storage management:** Deltas keep individual snapshots small, but over time, many snapshots accumulate. The system needs a snapshot management UI where users can delete old snapshots and see storage usage. A snapshot retention policy (keep last N, keep tagged snapshots) may be needed.

4. **Trust-level system:** Pre-labels with trust levels introduce a concept that permeates the quality system. Agreement calculations, review queue prioritization, and export filtering all need to be trust-level-aware. This adds complexity to the quality engine.

5. **Data source extensibility:** The data source interface must be clean enough that plugins can add new sources without modifying core code. This means defining a clear abstract interface for data ingestion with methods like `discover()`, `preview()`, `ingest()`, and `schema()`.

6. **Performance at scale:** The record inspector and dataset analytics both require efficient querying across multiple data types (records, labels, reviews, quality metrics). The SQLite schema design must account for these access patterns with appropriate indexes and possibly materialized views for analytics.

7. **HuggingFace dependency:** The HuggingFace datasets library is a significant dependency. It should be an optional dependency (installed when the user wants HuggingFace support) rather than a core requirement, to keep the base install lightweight.
