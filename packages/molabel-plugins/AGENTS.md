# molabel-plugins — Agent Guidance

## Responsibility

Built-in plugins that ship with MoLabel. These are first-party plugins that use the same plugin interfaces as third-party plugins.

## Plugins

Each one registers through the `molabel.plugins` entry-point group in `pyproject.toml`:

- `loaders/` — CSV, JSON, JSONL, Parquet, YAML, Markdown, and Hugging Face data loaders
- `exporters/` — JSONL, CSV, Parquet, and Hugging Face exporters

## Rules

- Depends on molabel-core only
- Must use the public plugin interfaces defined in molabel-core
- Must not access core internals or bypass the plugin API
- Each plugin should be self-contained
- Plugins serve as reference examples for third-party plugin authors
