# molabel-plugins — Agent Guidance

## Responsibility

Built-in task type plugins that ship with MoLabel. These are first-party plugins that use the same plugin interfaces as third-party plugins.

## Planned Plugins

- `text_labeling` — generic text classification and scoring
- `chat_review` — conversation/chat window review

More may be added (pairwise ranking, extraction, rubric scoring, etc.).

## Rules

- Depends on molabel-core only
- Must use the public plugin interfaces defined in molabel-core
- Must not access core internals or bypass the plugin API
- Each plugin should be self-contained with its own task schemas, renderers, and export serializers
- Plugins serve as reference examples for third-party plugin authors
