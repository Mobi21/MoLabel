# MoLabel UI Design Research

Deep research on modern UI design best practices for data labeling/annotation workbenches and developer tools. Conducted 2026-03-25.

---

## 1. Modern Data Labeling Tool UIs

### Label Studio
- **Architecture**: XML-like labeling config defines task layouts; React frontend with mobx-state-tree state management. Supports video, time series, images, text, audio, and chat.
- **2025 additions**: Dark mode, command palette, compact data table views, improved information panels.
- **Strengths**: Highly configurable layouts via XML templates; supports conditional UI logic for complex taxonomies; open-source and extensible; embeddable UI engine.
- **Weaknesses**: XML config is powerful but unfamiliar; enterprise features locked behind paid tier; initial setup complexity for non-technical users.
- **Key UX lesson**: Letting users define their own labeling interface layout (via config) is powerful for diverse annotation tasks.

### Labelbox
- **2025 redesign**: Shifted from a left-panel architecture to a **linear, form-based workflow**. Tasks and content flow in scrolling panes sequentially rather than hiding in collapsed panels.
- **Minimap**: Right-side minimap provides visual alerts for missing inputs across the entire task form, with highlights disappearing once requirements are satisfied.
- **Status indicators**: "Required" and "Finished" pills provide clear completion feedback.
- **Instructions inline**: Project instructions are always visible, positioned adjacent to the tools they relate to.
- **Performance**: Quasi-virtualization techniques for fast rendering during scroll, even with complex ontologies.
- **Built-in code runner**: Detects and executes code blocks during evaluation.
- **Key UX lesson**: Form-based sequential workflows reduce cognitive load compared to multi-panel layouts. Always-visible instructions eliminate context-switching.

### Prodigy (by Explosion)
- **Core philosophy**: "Like Tinder for data" -- one decision at a time. Minimizes cognitive load by presenting focused, binary or simple choices.
- **23 annotation interfaces** for text, images, audio, video, relations, multiple-choice, HTML, and conflict resolution.
- **Active learning in the loop**: The model participates during annotation, only surfacing examples it's uncertain about, achieving 10x+ efficiency gains.
- **Fully scriptable**: Python recipes define the entire workflow -- data stream, annotation interface, callbacks, model updates.
- **Custom interfaces**: HTML/CSS/JavaScript for fully custom UIs while keeping the annotation pipeline.
- **Key UX lesson**: Reducing each annotation decision to its simplest form dramatically increases throughput and annotator satisfaction. Let the model pre-filter.

### Argilla
- **Collaboration-first**: Designed for AI engineers + domain experts building datasets together.
- **RLHF-native**: First-class support for ranking responses, collecting comparison data, and training reward models.
- **Efficiency tools**: Filters, AI feedback suggestions, and semantic search to speed up annotation.
- **Unlimited users**: Designed to distribute workload across hundreds of labelers.
- **Key UX lesson**: Data labeling tools increasingly need to support LLM evaluation workflows (ranking, rating, comparison) alongside traditional annotation.

### Cross-Tool Patterns

| Pattern | Label Studio | Labelbox | Prodigy | Argilla |
|---------|-------------|----------|---------|---------|
| Keyboard shortcuts | Yes | Yes | Yes | Yes |
| Active learning | Plugin | Built-in | Core feature | Via suggestions |
| Multi-modal | Yes | Yes | Yes | Limited |
| Dark mode | 2025 | Yes | N/A (minimal UI) | N/A |
| Command palette | 2025 | No | N/A | No |
| Custom interfaces | XML config | Form-based | HTML/CSS/JS | Python SDK |

### Design Recommendations for MoLabel

1. **One-decision-at-a-time mode** (Prodigy-style) for high-throughput annotation, with a **full editor mode** (Labelbox-style) for complex tasks.
2. **Always-visible instructions** adjacent to annotation controls, not hidden behind tabs.
3. **Sequential form-based workflow** for multi-step evaluation tasks (e.g., RLHF ranking).
4. **Minimap/progress indicator** for long annotation sessions showing completion status.
5. **Configurable labeling interfaces** -- let power users define custom layouts for their specific task type.

---

## 2. Modern Developer/Data Tool Design Trends (2025-2026)

### The "Linear Design" Language

Linear has defined a new standard for developer tool aesthetics:

- **LCH color space** for theme generation (perceptually uniform -- a red and yellow at lightness 50 appear equally light to the human eye). Three core variables (base color, accent color, contrast) generate the entire theme instead of 98+ individual variables.
- **Inter Display** for headings, **Inter** for body text -- a two-tier approach balancing expression with readability.
- **Inverted-L global chrome**: Sidebar + top bar framing the main content viewport.
- **Precise spatial alignment**: Meticulous alignment of labels, icons, and buttons both vertically and horizontally -- "cohesion users feel after minutes rather than notice immediately."
- **Restriction over flexibility**: Thoughtfully curated features rather than endless options.
- **Keyboard-first**: Every interaction triggerable via keyboard shortcut.
- **Dark mode dominant**: Brand color at 1-10% lightness rather than pure black.
- **Complex gradients** for depth without clutter.
- **Reduced color saturation**: Moving toward more neutral, timeless palettes.

### Vercel's Geist Design System

- **Developer-centric**: Explicitly optimized for developer tools and technical interfaces.
- **High-contrast accessible colors** as the default, not an afterthought.
- **Geist Sans + Geist Mono**: Purpose-built typefaces for dev tools.
- **60+ React components** with consistent API patterns.
- **CSS variable-based theming** with system preference detection.
- **Custom icon set** tailored for developer tools.

### Raycast's Design Philosophy

Three principles: **fast, simple, delightful**.
- 99% text-based UI -- proof that text-driven interfaces can be beautiful.
- Native rendering with React for UI declaration.
- Command palette as the primary interaction model.

### Broader 2025-2026 Trends

- **Liquid Glass**: Apple's iOS 26 design language -- translucent, depth-aware surfaces that refract and respond to context. Not skeuomorphic, but not flat either.
- **Micro-interactions**: 50% of designers actively adding micro-interactions and animations. Motion as a UX tool, not decoration.
- **Glassmorphism**: Translucent layers with subtle blur effects creating depth.
- **Purpose-built minimalism**: Minimal doesn't mean featureless -- it means every element earns its place.

### Design Recommendations for MoLabel

1. **LCH-based color system** with 3-variable theme generation (base, accent, contrast) for infinite themability.
2. **Inter/Inter Display** or Geist Sans/Mono typography stack.
3. **Dark mode first** with light mode as equally polished alternative.
4. **Keyboard-first interaction** model with discoverable shortcuts.
5. **Command palette (Cmd+K)** as a core navigation pattern.
6. **Purposeful animations** -- spring physics for transitions, not gratuitous motion.
7. **High-contrast, accessible** color system from day one.

---

## 3. Onboarding and Tutorial Systems

### Notion's 6 Onboarding Lessons

1. **Profile setup with ownership signals**: Name + photo creates psychological ownership. Allow avatar generation as alternative.
2. **Smart workspace detection**: Analyze email domains to identify existing team workspaces and nudge users toward joining.
3. **Use-case segmentation survey**: Structured Q&A identifies needs (individual vs. team, annotation type, data modality). This is the backbone of customization.
4. **Dynamic UI preview**: Interface updates in real-time based on selections. Users see workspace evolving as they make choices.
5. **Workspace naming**: Reinforces ownership and structure. Include inline validation and preview.
6. **Interactive guided tour**: Adaptive walkthroughs highlighting features matching selected use cases. Opt-out flexibility is essential.

### Progressive Disclosure Patterns

- **Empty states as onboarding**: Use blank screens to guide users to their first action rather than showing empty tables.
- **Checklists**: Break complex features into manageable steps, one task per screen. Drives completion and feature discovery.
- **Tooltips**: Contextual information without overwhelming the UI. Trigger for new users, dismiss permanently.
- **Multi-screen workflows**: Spread options across screens with progress indicators rather than cramming onto one page.
- **Hierarchical menus**: Show core features first, progressively expose advanced settings.
- **Resource centers**: Organized knowledge bases by category for self-serve answers.
- **Segment by jobs-to-be-done**: Different user goals warrant different feature prioritization.
- **Branch experiences**: Ask qualifying questions early, route users down personalized paths.

### Best Practices from Nielsen Norman Group

- **Onboarding tutorials** work best when they are: short, interactive, and contextual.
- **Contextual help** (tooltips appearing at the moment of need) outperforms upfront tutorials.
- **Learn-by-doing** is superior to watching/reading -- Notion's Getting Started page teaches by having users use the product.

### Design Recommendations for MoLabel

1. **First-run wizard**: Ask 3-4 questions (role, primary data type, team size, experience level) to customize the initial workspace.
2. **Dynamic preview**: Show the workspace adapting in real-time as users make setup choices.
3. **Checklist-driven onboarding**: "Set up your first project" > "Import sample data" > "Create your first label" > "Try AI-assisted annotation" > "Invite a teammate".
4. **Empty states with purpose**: Every empty state should have an illustration, explanation, and single clear CTA.
5. **Contextual tooltips**: Appear on first encounter with each feature, not as an upfront dump.
6. **Template gallery**: Pre-built project templates for common labeling tasks (NER, sentiment, image classification, RLHF ranking, etc.).
7. **Progressive feature revelation**: Start with simple labeling, progressively introduce AI assistance, workflows, plugins.

---

## 4. Modern React Component Design Patterns

### shadcn/ui Best Practices

- **Tailwind v4 integration**: Full support for `@theme` directive and `@theme inline`. Components updated for Tailwind v4 + React 19.
- **Animation**: `tw-animate-css` replaces deprecated `tailwindcss-animate`.
- **Three component principles**: (1) Encapsulate behavior not appearance (headless logic), (2) Define visual options via class-variance-authority (variants), (3) Token-only styling -- no raw Tailwind literals or hardcoded values.
- **Folder structure**: `/components/ui/` (shadcn primitives), `/components/shared/` (composed components), `/components/forms/` (form-specific).
- **Design tokens with `@theme`**: Single source of truth for colors, spacing, typography, and radii.
- **Theming**: CSS variables with `tailwind.cssVariables: true` in components.json.

### Key shadcn/ui Components for MoLabel

- **Sidebar**: Composable provider-based pattern with three variants (sidebar, floating, inset) and three collapsible modes (offcanvas, icon, none). Built-in Cmd+B toggle, localStorage persistence, mobile sheet overlay.
- **Command (cmdk)**: Built on Paco Coursey's cmdk -- same library powering Linear, Raycast. Fuzzy search, keyboard navigation, groupable actions.
- **Data Table**: Built on TanStack Table. Supports sorting, filtering, pagination, row selection, column visibility, and URL-based state persistence.
- **Resizable**: Built on react-resizable-panels. VS Code-style adjustable panels with dragging, double-click reset, keyboard resizing, snapping, collapsed states, and layout persistence.
- **Sonner (Toast)**: Opinionated toast by Emil Kowalski. Promise integration for automatic loading/success/error states. Pre-styled types (success, error, warning, info, loading).

### Motion (formerly Framer Motion) Best Practices

- **Package renamed**: `framer-motion` is now `motion` on npm; import from `motion/react`.
- **Layout prop**: Enable smooth layout animations with minimal re-renders.
- **AnimatePresence**: Always wrap conditional renders for proper exit animations.
- **Transform properties**: Use `scale` and `translate` for GPU-accelerated performance.
- **Variants system**: Define state groups (hidden, visible, hover) in single config objects.
- **Orchestrated animations**: `useAnimation` hook with staggered sequences (`delay: i * 0.3`).
- **Gesture-based**: Drag constraints, dynamic scaling, responsive motion patterns.
- **Lazy loading**: Only animate components when visible using `useInView`.
- **Spring physics**: Hardware-accelerated, physics-based animations for natural feel.

### TanStack Table Patterns

- **Virtual scrolling**: TanStack Virtual renders only visible rows for large datasets.
- **Combo pattern**: TanStack Table + TanStack Query + TanStack Virtual for data-heavy interfaces.
- **Advanced features**: Dynamic filtering, sorting, column management, drag-and-drop, URL-based state persistence (via `nuqs`).
- **shadcn integration**: Toolbars for filters with `Input`, row actions with `DropdownMenu`, selection with `Checkbox`.

### State Management (Zustand + TanStack Query)

- **Zustand**: Lightweight client state. Slices pattern for domain-driven architecture. Persist middleware for localStorage. DevTools middleware for debugging.
- **TanStack Query**: Server state. Optimistic updates via `onMutate` handler. `useInfiniteQuery` for infinite scroll. Prefetching for instant navigation. Works with Suspense and concurrent rendering.
- **Pattern**: Use Zustand for UI state (sidebar open, selected tool, layout preferences) and TanStack Query for all server data (projects, annotations, models).

### Design Recommendations for MoLabel

1. **shadcn/ui as the component foundation** with Tailwind v4 and CSS variable theming.
2. **Resizable panels** (react-resizable-panels via shadcn) for the workspace layout -- annotation editor, data browser, side panel.
3. **TanStack Table** for all data views with virtual scrolling for large datasets.
4. **Motion (Framer Motion)** for: layout animations on panel resize, staggered list animations, page transitions, micro-interactions on annotation actions.
5. **Sonner** for all notifications with promise-based loading states for async operations (saving annotations, running AI, importing data).
6. **cmdk** for command palette with project-wide search, navigation, and action execution.
7. **Zustand slices** for: UI layout state, annotation tool state, active filters, user preferences.
8. **TanStack Query** for: project data, annotation batches, AI model results, user/team data.

---

## 5. Customizable UI Design

### VS Code Layout Architecture

VS Code provides the gold standard for customizable workspaces:

- **5 primary regions**: Primary Sidebar (left), Secondary Sidebar (right), Editor (center), Panel (bottom), Activity Bar (navigation).
- **Drag-and-drop**: Views and panels can be dragged between any region. Layout persists across sessions.
- **Panel alignment**: Center (editor width), Justify (full width), Left/Right (edge to editor).
- **Editor groups**: Split editors, grid layouts (2x2, 3-column), pinned tabs, locked groups.
- **Floating windows**: Editors detach into independent windows.
- **Zen Mode**: Hides all UI except editor. Centered Layout mode.
- **Profiles**: Save complete configurations (extensions, settings, layouts) and switch with one click.
- **Reset**: View > Reset View Locations to restore defaults.

### Obsidian Customization Model

- **Modular workspace**: Both sidebars expandable/collapsible/splittable. Central editor splits horizontally and vertically.
- **Workspaces Plus**: Save/load named workspace configurations with hotkeys.
- **Minimal theme**: Colors, fonts, and more customizable via companion plugins. Background styles (low contrast, high contrast, true black for OLED).
- **Plugin-driven UI**: Tab Group Arrangement for VS Code-like tab management.
- **CSS snippets**: Users write raw CSS to customize any aspect of the UI.

### Design Recommendations for MoLabel

1. **Three-region layout**: Left sidebar (navigation/project tree), Center (annotation editor), Right panel (properties/AI suggestions). All resizable via react-resizable-panels.
2. **Collapsible panels**: Each region collapsible to icon-only or fully hidden. Cmd+B for sidebar, Cmd+J for bottom panel (VS Code conventions).
3. **Layout persistence**: Save panel sizes and visibility to localStorage. Restore on session load.
4. **Named workspaces**: Let users save layout configurations for different task types ("Annotation Mode", "Review Mode", "Dashboard Mode").
5. **Theme system**: CSS variables with light/dark/system modes. User-selectable accent colors. High-contrast mode for accessibility.
6. **Zen/Focus mode**: Hide all chrome for distraction-free annotation sessions.
7. **Draggable views**: Allow moving panels between regions (properties panel from right to bottom, etc.).

---

## 6. Clean/Minimal Data-Heavy UI Patterns

### Dashboard Layout Principles

- **F and Z-pattern scanning**: Place most critical data top-left. Content flows vertically with priority data first, then overview, then detailed breakdowns.
- **Card-based organization**: Consistent card layout with uniform positioning of titles, labels, legends. Cards don't require visible borders -- consistency matters more.
- **30-40% whitespace**: Boosts comprehension by nearly 20%. Prevents "data eyeball attack."
- **Big bold numbers**: For priority KPI metrics, use large display fonts. Demonstrates confidence in what matters most.
- **Overview first, detail on demand**: Aggregated summaries before drill-downs. Default to useful subsets rather than showing everything.

### Data Table Techniques

- **Sticky headers**: For vertical scrolling. Fixed columns for horizontal navigation.
- **Alignment**: Right-align numbers, left-align text. Monospaced fonts for numbers to maintain vertical digit alignment.
- **Density options**: Condensed (40px rows), Regular (48px), Relaxed (56px). Let users choose.
- **Row height**: Match complexity. Simple lists use compact rows; complex data uses expandable rows.
- **Virtual scrolling**: Render only visible rows (TanStack Virtual).

### Filtering Architecture

- **Full-page filters**: Affect all views globally (date range, project, user).
- **Module-level filters**: Granular control per data view.
- **Progressive filter disclosure**: Frequently-used filters prominent; uncommon filters collapsed.
- **Logical operators**: And/Or, Less than, Greater than, Contains, Starts with.
- **Saved filters**: Let users save filter configurations with names for reuse.
- **URL-based state**: Filters encoded in URL for shareable, bookmarkable views (use `nuqs` library).

### Loading and Empty States

- **Loading**: Never omit loading feedback. Use skeleton loaders that match the shape of incoming content. For waits >10 seconds, show progress indicators with elapsed time.
- **Empty states**: Always include (1) illustration or icon, (2) headline, (3) secondary explanation, (4) CTA button. Never leave users at a dead end.
- **Segmented loading**: Divide screens into independently loading sections. If one API fails, the rest stays functional.
- **Optimistic UI**: For 97-99% success rate actions, display results immediately while processing in background.

### Color Strategy for Data

- **Intensity scales**: Light to dark for magnitude rather than red-yellow-green.
- **Blues + oranges**: Positive/negative trends. Avoids "trading terminal" appearance.
- **Texture patterns**: Hashes, dots, lines alongside color for accessibility.
- **Redundant coding**: Shapes + patterns + color, never color alone.

### Design Recommendations for MoLabel

1. **Project dashboard**: Card-based overview with big bold numbers (annotations completed, AI accuracy, pending reviews). F-pattern layout.
2. **Data browser**: TanStack Table with virtual scrolling, sticky headers, density toggle, column resizing. URL-based filter state.
3. **Skeleton loaders**: Match the shape of data tables, annotation cards, and sidebar content.
4. **Segmented loading**: Dashboard cards load independently. One slow API call doesn't block the entire view.
5. **Saved filter presets**: "Show me: unreviewed annotations with low AI confidence from this week."
6. **Monospaced numbers**: Use Geist Mono or tabular figures for all numeric data in tables and dashboards.

---

## 7. AI-Assisted Tool Interfaces

### Agentic AI UX Patterns (Smashing Magazine framework)

Six lifecycle patterns for AI agent interfaces:

**Pre-Action:**
1. **Intent Preview**: Show what the AI will do in plain language with sequential steps. Offer "Proceed," "Edit Plan," or "Handle it Myself" options. Target: >85% acceptance without edits.
2. **Autonomy Dial**: Let users set comfort level per task type:
   - Observe & Suggest (notification only)
   - Plan & Propose (review required)
   - Act with Confirmation (final go/no-go)
   - Act Autonomously (pre-approved, post-action notification)

**In-Action:**
3. **Explainable Rationale**: "Because you said X, I did Y." Link decisions to user rules/precedent. No jargon.
4. **Confidence Signal**: Percentage scores, color-coded cues (green checkmark = high, yellow question mark = uncertainty). Surface in plans and recommendations.

**Post-Action:**
5. **Action Audit & Undo**: Chronological timeline of all AI actions. Status indicators (successful, in-progress, undone). Time-limited undo windows. Target: <5% reversion rate.
6. **Escalation Pathway**: "I found three options -- which suits you?" or "This seems unusual; would you like to review?" Target: 5-15% healthy escalation frequency.

### Cursor's Diff-Based Review Workflow

- **Inline suggestions**: Cmd+K on selected code shows a diff of proposed changes. Accept or reject per-change.
- **Multi-file aggregated view**: Cursor 2.0 consolidates changes from an agent run into a single review surface.
- **Composer mode (Cmd+I)**: Natural language > plan with diffs across files > individual review before applying.
- **Key insight**: User control through diff-based review is essential. A recent regression that auto-applied changes without showing the diff was immediately flagged as a bug by users.

### GitHub Copilot Patterns

- **Ghost text inline suggestions**: Appear as you type. Tab to accept, Esc to dismiss.
- **Agent mode (2025)**: Analyzes codebases, proposes multi-file changes, runs tests, auto-corrects in a loop.
- **Code review with confidence**: CodeQL-backed review comments with confidence scores.
- **Failure mode**: "Confident wrong answer" -- looks correct but has subtle logical errors. This is why human review UI is critical.

### AI Transparency Patterns

- **Layered transparency by expertise**: Novice (simple pass/fail), Regular (confidence + summary), Expert (full reasoning chain + data sources).
- **Expandable "See More" panels**: Deeper explanations on demand.
- **Clear visual differentiation**: Badges/icons/color distinguish AI-generated from human-verified content.
- **Source attribution**: Show which data/rules informed each AI decision.

### Design Recommendations for MoLabel

1. **AI suggestion cards**: Show each AI-generated annotation with:
   - The annotation itself (highlighted/overlaid on the data)
   - Confidence score (percentage + color indicator)
   - Brief rationale ("Based on pattern X in similar items")
   - Accept / Reject / Edit buttons
   - "Why?" expandable panel for full reasoning

2. **Autonomy dial per project**: Let project owners set AI behavior:
   - "Suggest only" (default) -- AI pre-labels but all require human review
   - "Auto-accept high confidence" -- Auto-accept >95% confidence, queue the rest
   - "Full auto" -- AI handles everything, humans sample-review

3. **Diff view for bulk AI actions**: When AI labels a batch, show a summary diff view:
   - X items auto-labeled, Y flagged for review, Z skipped
   - Drill into individual items from the summary

4. **Action audit log**: Chronological feed of all AI actions in the project, filterable by confidence, status, and type.

5. **Confidence-based triage queue**: Sort review items by confidence -- low confidence first (most likely to be wrong, highest value for human review).

6. **Visual confidence encoding**:
   - Green highlight (>90% confidence)
   - Yellow highlight (60-90%)
   - Red highlight (<60%)
   - Opacity/saturation tied to confidence level

7. **Human override indicators**: After human review, clearly mark items as "Human verified" vs "AI-generated" with distinct visual treatment.

---

## 8. Recommended Technology Stack Summary

Based on all research, the recommended stack for MoLabel's frontend:

### Core
| Layer | Technology | Reason |
|-------|-----------|--------|
| Framework | React 19 + TypeScript strict | Industry standard, team familiarity |
| Styling | Tailwind CSS v4 | Token-based, dark mode built-in |
| Components | shadcn/ui | Composable, themeable, owns the code |
| State (client) | Zustand | Lightweight, slice pattern, middleware |
| State (server) | TanStack Query | Caching, optimistic updates, prefetching |
| Animation | Motion (Framer Motion) | Spring physics, layout animations |
| Tables | TanStack Table + TanStack Virtual | Virtual scroll, filtering, sorting |
| Routing | TanStack Router or React Router | Type-safe, URL state management |

### UI Components
| Feature | Library | Notes |
|---------|---------|-------|
| Command palette | cmdk (via shadcn Command) | Fuzzy search, keyboard nav |
| Toast/notifications | Sonner (via shadcn) | Promise-based, pre-styled types |
| Resizable panels | react-resizable-panels (via shadcn Resizable) | Layout persistence, snap |
| Sidebar | shadcn Sidebar | Provider pattern, collapsible modes |
| Data tables | shadcn DataTable + TanStack Table | Column mgmt, filters, pagination |
| Forms | React Hook Form + Zod | Validation, type safety |
| Icons | Lucide React | Consistent with shadcn ecosystem |
| Drag and drop | dnd-kit | Accessible, performant |
| URL state | nuqs | Shareable filter/view URLs |

### Design System
| Token | Approach |
|-------|----------|
| Colors | LCH-based generation from 3 variables (base, accent, contrast). CSS custom properties. |
| Typography | Geist Sans (UI) + Geist Mono (code/data). Inter as fallback. |
| Spacing | 4px base unit. Tailwind's default scale. |
| Radii | Small (4px), Medium (8px), Large (12px), Full (9999px). |
| Shadows | Minimal. One subtle elevation level for cards/dropdowns. |
| Motion | Spring-based defaults. 200ms for micro-interactions, 300ms for layout changes. |
| Dark mode | CSS `prefers-color-scheme` + manual toggle + localStorage persistence. |

---

## 9. Key Design Principles for MoLabel

1. **Annotation speed is the primary metric.** Every UI decision should be evaluated against "does this help annotators work faster and more accurately?"

2. **One decision at a time** for high-throughput tasks. Full editor for complex tasks. Let users choose.

3. **AI is a co-pilot, not autopilot.** Always show what AI did, why, and how confident it is. Make review effortless, not invisible.

4. **Keyboard-first, mouse-friendly.** Every action has a shortcut. Command palette for discovery. But nothing requires the keyboard.

5. **Progressive disclosure everywhere.** Simple by default, powerful on demand. Beginners see a clean interface; experts unlock advanced controls.

6. **Data density is adjustable.** Compact mode for power users. Relaxed mode for new users. Let the user choose.

7. **Consistent visual language.** Every icon, color, spacing decision follows the design token system. No one-off styles.

8. **Fast, always.** Skeleton loaders, optimistic updates, virtual scrolling, segmented loading. The UI should never feel slow.

9. **Themeable from the ground up.** Dark/light/system mode. Accent color customization. High-contrast accessibility mode.

10. **Workspaces for workflows.** Named layout configurations for different tasks. Switch between "Annotation Mode" and "Review Mode" with one click.

---

## Sources

### Data Labeling Tools
- [Label Studio 2025 Review](https://sider.ai/blog/ai-tools/is-label-studio-the-best-open-source-labeling-tool-a-2025-review)
- [Label Studio Wrapped 2025](https://labelstud.io/blog/label-studio-wrapped-2025/)
- [Labelbox MMC Editor Redesign](https://labelbox.com/blog/ai-evaluation-labelboxs-redesigned-multimodal-chat-editor-04-2025/)
- [Labelbox Editor Capabilities](https://docs.labelbox.com/en/core-concepts/editor-capabilities)
- [Prodigy Annotation Tool](https://prodi.gy/)
- [Prodigy Active Learning](https://explosion.ai/blog/prodigy-annotation-tool-active-learning)
- [Argilla for LLMs](https://argilla.io/blog/argilla-for-llms/)
- [Multimodal Annotation Tools Comparison 2025](https://www.pixeltable.com/blog/multimodal-annotation-tools-comparison-2025)
- [Top Data Labeling Tools 2026](https://www.devopsschool.com/blog/top-10-ai-data-labeling-tools-in-2025-features-pros-cons-comparison/)
- [Best Data Labeling UI Features](https://www.labellerr.com/blog/best-data-labeling-user-interface-tools-features-and-best-practices/)

### Developer Tool Design
- [How We Redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui)
- [Linear Design: The SaaS Design Trend (LogRocket)](https://blog.logrocket.com/ux-design/linear-design/)
- [Vercel Geist Design System](https://vercel.com/geist/introduction)
- [Geist Design System (Figma)](https://www.figma.com/community/file/1330020847221146106/geist-design-system-vercel)
- [Raycast Design Philosophy](https://www.raycast.com/blog/a-fresh-look-and-feel)
- [UI Trends 2026 (UX Studio)](https://www.uxstudioteam.com/ux-blog/ui-trends-2019)
- [12 UI/UX Trends 2026 (index.dev)](https://www.index.dev/blog/ui-ux-design-trends)
- [Web Development Trends 2026 (Figma)](https://www.figma.com/resource-library/web-development-trends/)

### Onboarding & Tutorials
- [Notion's Personalized Onboarding (Candu)](https://www.candu.ai/blog/how-notion-crafts-a-personalized-onboarding-experience-6-lessons-to-guide-new-users)
- [Notion's Lightweight Onboarding (Appcues)](https://goodux.appcues.com/blog/notions-lightweight-onboarding)
- [Progressive Disclosure Examples (Userpilot)](https://userpilot.com/blog/progressive-disclosure-examples/)
- [Onboarding Tutorials vs Contextual Help (NNGroup)](https://www.nngroup.com/articles/onboarding-tutorials/)
- [Onboarding Best Practices 2025 (Guidejar)](https://www.guidejar.com/blog/7-user-onboarding-best-practices-that-actually-work-in-2025)
- [Progressive Disclosure & Memory (Pendo)](https://www.pendo.io/pendo-blog/onboarding-progressive-disclosure/)

### React Component Patterns
- [shadcn/ui Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4)
- [shadcn/ui Theming](https://ui.shadcn.com/docs/theming)
- [shadcn/ui Sidebar](https://ui.shadcn.com/docs/components/radix/sidebar)
- [shadcn/ui Data Table](https://ui.shadcn.com/docs/components/radix/data-table)
- [shadcn/ui Resizable](https://ui.shadcn.com/docs/components/radix/resizable)
- [Scalable Design System with shadcn/ui (Medium)](https://shadisbaih.medium.com/building-a-scalable-design-system-with-shadcn-ui-tailwind-css-and-design-tokens-031474b03690)
- [Motion (Framer Motion)](https://motion.dev/)
- [Advanced Motion Techniques 2025](https://www.luxisdesign.io/blog/mastering-framer-motion-advanced-animation-techniques-for-2025)
- [TanStack Table](https://tanstack.com/table/latest)
- [Virtualized Table with TanStack](https://dev.to/ainayeem/building-an-efficient-virtualized-table-with-tanstack-virtual-and-react-query-with-shadcn-2hhl)

### Customizable UI
- [VS Code Custom Layout](https://code.visualstudio.com/docs/configure/custom-layout)
- [VS Code UX Guidelines](https://code.visualstudio.com/api/ux-guidelines/overview)
- [Obsidian Minimal Theme](https://github.com/kepano/obsidian-minimal)
- [react-resizable-panels](https://github.com/bvaughn/react-resizable-panels)

### Data-Heavy UI
- [Dashboard Design UX Patterns (Pencil & Paper)](https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-dashboards)
- [Designing UI for Heavy Data (AlterSquare)](https://www.altersquare.io/designing-ui-applications-heavy-data-workflows/)
- [Dashboard Design Principles 2026 (DesignRush)](https://www.designrush.com/agency/ui-ux-design/dashboard/trends/dashboard-design-principles)
- [Dashboard Design Principles (UXPin)](https://www.uxpin.com/studio/blog/dashboard-design-principles/)
- [Data Table Best Practices (JustInMind)](https://www.justinmind.com/ui-design/data-table)
- [Empty State UX (Eleken)](https://www.eleken.co/blog-posts/empty-state-ux)

### AI Interface Design
- [Designing for Agentic AI (Smashing Magazine)](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)
- [7 UX Patterns for AI Agents (Exalt Studio)](https://exalt-studio.com/blog/designing-for-ai-agents-7-ux-patterns-that-drive-engagement)
- [Confidence-Based Feedback UI (Medium)](https://medium.com/design-bootcamp/designing-a-confidence-based-feedback-ui-f5eba0420c8c)
- [UX of AI](https://uxofai.com/)
- [Cursor AI Guide 2025](https://skywork.ai/blog/cursor-ai-comprehensive-guide-2025-everything-you-need-to-know/)
- [Cursor vs GitHub Copilot 2026](https://www.truefoundry.com/blog/cursor-vs-github-copilot)
- [CopilotKit (Agent UI Framework)](https://github.com/CopilotKit/CopilotKit)

### State Management & Data Fetching
- [Zustand](https://github.com/pmndrs/zustand)
- [Modern React State Management 2025](https://dev.to/joodi/modern-react-state-management-in-2025-a-practical-guide-2j8f)
- [TanStack Query Optimistic Updates](https://tanstack.com/query/v5/docs/framework/react/examples/optimistic-updates-ui)
- [React Query 2025 Deep Dive](https://dev.to/jdavissoftware/mastering-react-query-in-2025-a-deep-dive-into-data-fetching-for-modern-apps-22jf)

### Notifications & UI Feedback
- [Sonner Toast Library](https://github.com/emilkowalski/sonner)
- [React Toast Libraries Compared 2025 (LogRocket)](https://blog.logrocket.com/react-toast-libraries-compared-2025/)
- [cmdk Command Palette](https://github.com/pacocoursey/cmdk)
- [Sidebar Design Examples 2026 (Navbar Gallery)](https://www.navbar.gallery/blog/best-side-bar-navigation-menu-design-examples)
- [Dark Mode Best Practices 2025](https://medium.com/@jackbrownkarmaa/dark-mode-in-web-design-best-practices-in-2025-445d8d6463a3)
