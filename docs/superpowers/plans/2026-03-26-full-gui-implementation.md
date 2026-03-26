# MoLabel Full GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete MoLabel GUI — all 14 screens with beautiful, production-grade UI using shadcn/ui, React Router, Zustand, and TanStack Query.

**Architecture:** Single-page app with sidebar navigation, route-based pages, Zustand for UI state, TanStack Query for server state, shadcn/ui components with Tailwind CSS. Mock data layer for development until backend is connected.

**Tech Stack:** React 19, TypeScript strict, Vite, Tailwind CSS v4, shadcn/ui, React Router v7, Zustand, TanStack Query v5, React Flow, TanStack Table, Recharts, Lucide icons

---

## Phase 1: Foundation

### Task 1: Install shadcn/ui and Core Dependencies

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/components.json`
- Modify: `frontend/src/app.css`

- [ ] **Step 1:** Install shadcn/ui dependencies and core packages
```bash
cd frontend
npm install react-router-dom@7 @tanstack/react-query@5 zustand lucide-react class-variance-authority clsx tailwind-merge
npm install -D @types/react-router-dom
```

- [ ] **Step 2:** Create `src/lib/utils.ts` with cn helper
```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 3:** Initialize shadcn/ui config and install core components:
button, input, label, card, badge, separator, tooltip, dropdown-menu, dialog, sheet, scroll-area, tabs, table, select, textarea, switch, avatar, skeleton, sonner (toast), command, popover, sidebar

- [ ] **Step 4:** Set up CSS variables for theming in app.css — dark/light mode with professional muted palette

- [ ] **Step 5:** Verify build succeeds: `npm run build`

### Task 2: Set Up React Router with All Routes

**Files:**
- Create: `frontend/src/router.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/pages/` — placeholder for each of 14 pages

- [ ] **Step 1:** Create router config with all 14 routes
- [ ] **Step 2:** Create placeholder page components for all routes
- [ ] **Step 3:** Wire router into App.tsx
- [ ] **Step 4:** Verify navigation works in browser

### Task 3: Set Up Zustand Stores

**Files:**
- Create: `frontend/src/stores/workspace-store.ts`
- Create: `frontend/src/stores/ui-store.ts`
- Create: `frontend/src/stores/auth-store.ts`

- [ ] **Step 1:** Create workspace store (active workspace, loading state)
- [ ] **Step 2:** Create UI store (sidebar collapsed, theme, active page)
- [ ] **Step 3:** Create auth store (current reviewer, session)

### Task 4: Set Up TanStack Query

**Files:**
- Create: `frontend/src/lib/query-client.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1:** Create query client with defaults
- [ ] **Step 2:** Wrap app in QueryClientProvider

### Task 5: Create Mock Data Layer

**Files:**
- Create: `frontend/src/mocks/` — mock data for all entities

- [ ] **Step 1:** Create mock data matching backend Pydantic models for: workspaces, datasets, records, workflows, task schemas, agent runs, reviews, quality metrics, exports, releases, plugins, reviewers
- [ ] **Step 2:** Create mock API hooks that return this data

---

## Phase 2: Core Layout & Navigation

### Task 6: App Shell — Sidebar + Main Content

**Files:**
- Create: `frontend/src/components/layout/app-sidebar.tsx`
- Create: `frontend/src/components/layout/app-layout.tsx`
- Create: `frontend/src/components/layout/top-bar.tsx`
- Create: `frontend/src/components/layout/nav-item.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1:** Build collapsible sidebar with shadcn Sidebar component — icons + labels for all 14 nav items grouped into sections:
  - Overview: Home, Mission Control
  - Data: Data, Tasks, Workflow
  - AI: Agents
  - Human: Review, Adjudication
  - Quality: Quality, Curation
  - Output: Exports & Releases
  - System: Plugins, Settings

- [ ] **Step 2:** Build top bar with: workspace name, breadcrumbs, reviewer avatar, theme toggle

- [ ] **Step 3:** Wire layout into router — sidebar persists, main content area swaps per route

- [ ] **Step 4:** Add smooth transitions between routes

- [ ] **Step 5:** Verify in browser — sidebar collapses, navigation works, responsive

---

## Phase 3: Screens (each verified in browser before moving on)

### Task 7: Home Dashboard

**Files:**
- Create: `frontend/src/pages/home/index.tsx`
- Create: `frontend/src/pages/home/stat-card.tsx`
- Create: `frontend/src/pages/home/activity-feed.tsx`
- Create: `frontend/src/pages/home/quick-actions.tsx`

Features: Project identity, stat cards (records/labeled/reviewed/export-ready), active workflow stage indicator, blockers list, pending queues preview, recent activity feed, primary CTA button.

### Task 8: Settings Page

**Files:**
- Create: `frontend/src/pages/settings/index.tsx`
- Create: `frontend/src/pages/settings/provider-config.tsx`
- Create: `frontend/src/pages/settings/reviewer-management.tsx`
- Create: `frontend/src/pages/settings/preferences.tsx`

Features: Tabbed layout — Providers (API key config for OpenAI/Anthropic/Ollama/OpenRouter), Reviewers (list/create/edit), Preferences (theme, defaults), Audit Log viewer.

### Task 9: Data — Dataset Catalog

**Files:**
- Create: `frontend/src/pages/data/index.tsx`
- Create: `frontend/src/pages/data/dataset-catalog.tsx`
- Create: `frontend/src/pages/data/dataset-card.tsx`
- Create: `frontend/src/pages/data/import-dialog.tsx`

Features: Dataset list with search/filter, health indicators, record counts, import dialog (file upload, HuggingFace search), bulk operations.

### Task 10: Data — Record Inspector

**Files:**
- Create: `frontend/src/pages/data/record-inspector.tsx`
- Create: `frontend/src/pages/data/panels/source-panel.tsx`
- Create: `frontend/src/pages/data/panels/labels-panel.tsx`
- Create: `frontend/src/pages/data/panels/quality-panel.tsx`
- Create: `frontend/src/pages/data/panels/lineage-panel.tsx`

Features: 360-degree record view with 4 panels — source data, labels (agent + human), quality signals, lineage/history.

### Task 11: Data — Analytics

**Files:**
- Create: `frontend/src/pages/data/analytics.tsx`
- Create: `frontend/src/components/charts/label-distribution.tsx`
- Create: `frontend/src/components/charts/quality-metrics.tsx`
- Create: `frontend/src/components/charts/drift-chart.tsx`

Features: Label distribution charts, quality metrics (kappa, agreement), drift detection visualization, pre-label analysis.

### Task 12: Tasks — Schema & Rubric Editor

**Files:**
- Create: `frontend/src/pages/tasks/index.tsx`
- Create: `frontend/src/pages/tasks/schema-editor.tsx`
- Create: `frontend/src/pages/tasks/rubric-editor.tsx`
- Create: `frontend/src/pages/tasks/review-flow-config.tsx`

Features: Task schema builder (add/edit/remove label fields), rubric editor (definitions, examples, edge cases), review flow configuration, overlap/adjudication rules.

### Task 13: Workflow — Visual Builder

**Files:**
- Create: `frontend/src/pages/workflow/index.tsx`
- Create: `frontend/src/pages/workflow/canvas.tsx`
- Create: `frontend/src/pages/workflow/nodes/` — custom node types
- Create: `frontend/src/pages/workflow/toolbar.tsx`
- Create: `frontend/src/pages/workflow/step-config-panel.tsx`

Features: React Flow canvas with custom node types (data, agent, human, quality, output, control), drag-and-drop, edge creation, execution state overlay, step config panel, template selector.

### Task 14: Agents — Run Interface & Comparison

**Files:**
- Create: `frontend/src/pages/agents/index.tsx`
- Create: `frontend/src/pages/agents/model-profiles.tsx`
- Create: `frontend/src/pages/agents/run-interface.tsx`
- Create: `frontend/src/pages/agents/comparison-view.tsx`
- Create: `frontend/src/pages/agents/performance-dashboard.tsx`

Features: Model profile management, agent run launcher, side-by-side comparison with diff highlighting, performance dashboard (accuracy, cost, calibration curves).

### Task 15: Review — Queue Interface

**Files:**
- Create: `frontend/src/pages/review/index.tsx`
- Create: `frontend/src/pages/review/review-queue.tsx`
- Create: `frontend/src/pages/review/review-item.tsx`
- Create: `frontend/src/pages/review/blind-mode.tsx`

Features: Queue with prioritization, one-at-a-time review, accept/correct/reject, blind mode toggle, reveal AI button, draft saving, skip with reason.

### Task 16: Adjudication

**Files:**
- Create: `frontend/src/pages/adjudication/index.tsx`
- Create: `frontend/src/pages/adjudication/disagreement-list.tsx`
- Create: `frontend/src/pages/adjudication/resolution-editor.tsx`

Features: Disagreement queue, side-by-side conflicting labels, resolution options (adopt, merge, re-review, escalate), agreement patterns.

### Task 17: Quality Dashboard

**Files:**
- Create: `frontend/src/pages/quality/index.tsx`
- Create: `frontend/src/pages/quality/health-summary.tsx`
- Create: `frontend/src/pages/quality/agreement-view.tsx`
- Create: `frontend/src/pages/quality/drift-view.tsx`
- Create: `frontend/src/pages/quality/confidence-view.tsx`

Features: Overall health indicator, agreement metrics, drift detection with statistical tests, calibration curves, cost analysis, drill-down to failing records.

### Task 18: Curation

**Files:**
- Create: `frontend/src/pages/curation/index.tsx`
- Create: `frontend/src/pages/curation/subset-builder.tsx`
- Create: `frontend/src/pages/curation/challenge-set.tsx`

Features: Data subsetting tools, challenge set creation, quality filters, field mapping, export preparation checklist.

### Task 19: Exports & Releases

**Files:**
- Create: `frontend/src/pages/exports/index.tsx`
- Create: `frontend/src/pages/exports/export-wizard.tsx`
- Create: `frontend/src/pages/exports/release-manager.tsx`

Features: Export creation wizard (format, filters, preview), validation summary, download/push-to-HF. Release creation, validation checks, approval workflow, history.

### Task 20: Plugins

**Files:**
- Create: `frontend/src/pages/plugins/index.tsx`
- Create: `frontend/src/pages/plugins/plugin-card.tsx`

Features: Plugin list with enable/disable toggles, health indicators, config panels, documentation links.

### Task 21: Mission Control

**Files:**
- Create: `frontend/src/pages/mission-control/index.tsx`
- Create: `frontend/src/pages/mission-control/live-dashboard.tsx`
- Create: `frontend/src/pages/mission-control/agent-tracker.tsx`

Features: Real-time dashboard — active agents, queued work, failed steps, human decisions needed, release blockers. Live progress tracking, pause/resume controls.

### Task 22: AI Assistant Panel

**Files:**
- Create: `frontend/src/components/assistant/assistant-panel.tsx`
- Create: `frontend/src/components/assistant/assistant-input.tsx`
- Modify: `frontend/src/components/layout/app-layout.tsx`

Features: Right-side collapsible panel, context-aware prompts, modes (guide, explain, operator, monitor, troubleshoot). Available on every screen.
