# MoLabel CLI

Agent-first CLI and bundled skill package for MoLabel.

The intended operating model is:

- agents use `molabel` as the primary public interface,
- the backend stays behind that CLI,
- the GUI is the inspection and manual-review surface.

## Command Groups

- `session`: reviewer identity and session control
- `workspace`: workspace detection and bootstrap
- `provider`: provider discovery, health, and model listing
- `model-profile`: model profile CRUD and connectivity checks
- `benchmark`: authority-pack inspection, validation, scoring, and reporting
- `dataset`: dataset and record inspection/import
- `task-schema`: task schema creation and inspection
- `prompt`: prompt creation and inspection
- `workflow`: workflow creation, execution, and execution control
- `queue`: review queue inspection and claiming
- `review`: submit, draft, reveal, release, and correction flows
- `adjudication`: disagreement detection and resolution
- `agent-run`: agent-run lifecycle and comparison
- `quality`: quality dashboard, agreement, drift
- `export`: export creation and validation
- `release`: release creation and approval
- `artifact`: canonical file read/diff/write
- `skill`: install bundled MoLabel skills

## Development

```bash
npm install
npm run build
npm test
```
