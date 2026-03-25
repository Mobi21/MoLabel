# molabel-depolarize — Agent Guidance

## Responsibility

DePolarize reference implementation for MoLabel. Proves the generic core can support a real project with turn-level text review, context-window review, trajectory records, manifest governance, and release gating.

## Namespace

Uses `molabel_depolarize` (separate namespace, not under the shared `molabel` namespace). This package has its own `__init__.py` at the root.

## Rules

- Depends on molabel-core and molabel-plugins
- Must not contain logic that belongs in the generic core
- Domain-specific schemas, path inference, governance semantics, and export formats live here
- The core must be able to start without this package installed
