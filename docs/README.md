# MoLabel Documentation

This directory now has two kinds of docs:

- current-state guides for how the system works today,
- and deeper design records, PRDs, and research notes that explain why it was
  built this way or where it is still heading.

## Start Here

- [How MoLabel Works Today](guides/how-molabel-works-today.md)
  End-to-end system overview: repo layout, runtime surfaces, storage ownership,
  workflow execution, review, adjudication, quality, export, and release.

- [Grounded Benchmark Framework](guides/grounded-benchmark-framework.md)
  Current executable benchmark guide: stages, scoring, diagnostics, evidence
  bundle layout, log audit semantics, and how to verify metrics from raw logs.

- [Grounded Benchmark Catalog](guides/grounded-benchmark-catalog.md)
  Benchmark-by-benchmark reference: what each grounded fixture measures, which
  artifacts it scores, which metric is primary, and which task semantics must
  not be flattened away.

## Canonical References

- [Product Requirements](prd/agentic-data-operations-workbench-prd.md)
  Product scope and intended operating model.

- [Data Model](architecture/data-model.md)
  Canonical ownership of files, SQLite state, and derived data.

- [Workflow Execution](architecture/workflow-execution.md)
  Runtime behavior of YAML-defined workflows and step semantics.

- [API Specification](architecture/api-specification.md)
  Backend REST surface and data contracts.

- [Session And Identity](architecture/session-and-identity.md)
  Review queue ownership, identity, draft state, and audit semantics.

- [CLI README](../cli/README.md)
  Command families for the public CLI surface.

## Status Map

Use this status model when reading the rest of `docs/`:

- `docs/guides/` is intended to describe current behavior.
- `docs/architecture/` is authoritative for technical boundaries and deep
  domain behavior when it says so explicitly.
- `docs/prd/` describes product direction and constraints.
- `docs/research/` contains benchmark and design research. Many of those files
  are still useful, but some are deliberately marked proposed, draft, or
  transitional.

## Known Transitional Areas

- The product is CLI-primary in direction, but the most explicit Python console
  script exposed from the workspace today is `molabel-dev`.
- The frontend exists in-tree, but it is not ready for public use yet.
- The grounded benchmark is authority-pack-first in scoring semantics, but the
  current CLINC fixture still carries transitional `workbench/` scaffolding as
  executable reference material.
