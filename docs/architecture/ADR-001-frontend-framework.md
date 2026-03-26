# ADR-001: Frontend Framework

**Date:** 2026-03-23
**Status:** Accepted
**Supersedes:** Original PRD specification of HTMX + Jinja2 server-rendered UI

## Context

The original PRD specified HTMX with Jinja2 templates as the frontend technology, chosen for simplicity and to keep the stack Python-centric. As the product design matured, the required UI surfaces became clear:

- **Workflow builder:** A visual drag-and-drop canvas where users compose labeling workflows from step nodes, connect them with edges, configure branching and loops, and see execution state overlaid on the graph. This is a rich canvas interaction pattern.
- **Data explorer:** An interactive table with column resizing, sorting, filtering, inline editing, row selection, bulk actions, column-level type rendering (text, images, labels, confidence scores), and virtual scrolling for datasets with hundreds of thousands of records.
- **Mission control dashboard:** Real-time progress tracking across active workflow runs, with live-updating charts, status indicators, cost accumulators, and the ability to pause/resume/intervene in running workflows.
- **Side-by-side model comparison:** Synchronized scrolling views comparing outputs from multiple agent runs, with diff highlighting and per-field agreement indicators.
- **Agent performance charts:** Time-series accuracy trends, confidence calibration curves, error pattern breakdowns, and cost-per-label tracking with interactive drill-down.
- **Record inspector (360-view):** A dense, multi-panel view showing source data, all agent outputs, all human reviews, quality signals, and full lineage for a single record.

HTMX excels at progressively enhancing server-rendered HTML with targeted updates, but it is not designed for these interaction patterns. Building a drag-and-drop graph editor, virtualized data tables, or real-time synchronized comparison views in HTMX would require fighting the framework at every step, resulting in fragile custom JavaScript that negates the simplicity benefits.

## Decision

Replace HTMX + Jinja2 with a modern React-based frontend stack:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| UI framework | **React 19** | Component model, concurrent rendering |
| Language | **TypeScript** | Type safety across the frontend |
| Build tool | **Vite** | Fast dev server with HMR, optimized production builds |
| Workflow builder | **React Flow** | Node-based graph editor for workflow composition |
| Component library | **shadcn/ui** | Accessible, composable primitives (not a black-box library; components are copied into the project and owned) |
| Data explorer | **TanStack Table** | Headless table with virtual scrolling, sorting, filtering, column resizing |
| Charts | **Recharts** | Composable chart components for performance analytics |
| State management | **Zustand** | Lightweight global state for workflow editor state, UI preferences, active run tracking |
| API layer | **TanStack Query** | Server state management with caching, background refetch, optimistic updates |
| Styling | **Tailwind CSS** | Utility-first CSS, consistent with shadcn/ui |

The frontend communicates with the Python/FastAPI backend exclusively via a REST API. An OpenAPI schema is generated from the FastAPI backend, and TypeScript client types are auto-generated from that schema using a codegen tool (e.g., `openapi-typescript`). This ensures type safety across the full stack without manual type synchronization.

### Plugin UI Model

The original PRD envisioned plugins defining their UI via Jinja2 templates. Under the new model:

- **Default rendering:** Plugins declare their configuration and output schemas as JSON Schema. The frontend renders these automatically using a schema-driven form/display component.
- **Custom rendering (optional):** Plugins may ship an optional React component bundle for richer UI. The frontend loads these dynamically. Plugins that don't provide a custom component get the JSON Schema default, which is functional and consistent.

This means most plugin authors never need to write React code, while power users can provide fully custom UIs.

## Alternatives Considered

- **HTMX + Jinja2 (original PRD):** Rejected because the required UI complexity far exceeds what HTMX can deliver without extensive custom JavaScript. The simplicity advantage disappears when you need canvas interactions, virtualized tables, and real-time dashboards.
- **Svelte / SvelteKit:** Considered for its smaller bundle size and simpler reactivity model. Rejected because the ecosystem of specialized components (React Flow, TanStack Table, shadcn/ui) is significantly more mature in React. Building a workflow graph editor from scratch in Svelte would delay delivery substantially.
- **Vue 3 + Vuetify:** Considered as a middle ground. Rejected for the same ecosystem gap: no equivalent to React Flow's maturity for node-based graph editing, and fewer high-quality headless UI primitives.
- **Gradio / Streamlit:** Considered briefly as Python-native UI options. Rejected because they are designed for ML demos, not production applications with complex navigation, state management, and custom interaction patterns.

## Consequences

1. **Separate build target:** The frontend is a standalone project at the repo-root `frontend/` directory with its own `package.json`, build scripts, and dev server. Production builds output static assets that the FastAPI backend serves.

2. **API-first architecture:** All backend functionality must be exposed through well-defined REST endpoints with OpenAPI documentation. This is a positive constraint that improves backend design and enables future API consumers (CLI tools, third-party integrations).

3. **TypeScript codegen pipeline:** A build step generates TypeScript types from the FastAPI OpenAPI schema. This must run whenever the API changes and should be integrated into the dev workflow.

4. **JavaScript/Node.js in the toolchain:** Developers need Node.js installed alongside Python. The `uv` workspace manages Python; a separate `package.json` manages frontend dependencies.

5. **Plugin UI model shift:** Plugin authors who want custom UI must provide React components. The JSON Schema default rendering ensures this is optional, not required.

6. **Team skills:** Contributors working on the frontend need React/TypeScript experience. Backend contributors can work entirely in Python without touching the frontend.
