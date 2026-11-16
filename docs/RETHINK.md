# Rethinking MoLabel for 2026

Status: proposal for review. Sections marked **DRAFT** contain positioning wording that Mobi approves before it reaches the README or any public page.

## What MoLabel is for

**DRAFT.** MoLabel is an open labeling and adjudication tool that agents and people drive together. Its output is a living, versioned gold set: the eval or training data a team trusts, kept in git, growing as new failures arrive.

The center of labeling work has moved. Models pre-label and judge at scale. People review the hard cases. The result is a reference set used to measure the model, not a one-off CSV ([Eger et al.](https://arxiv.org/html/2411.04637v3), [Microsoft Research](https://www.microsoft.com/en-us/research/publication/keeping-humans-in-the-loop-human-centered-automated-annotation-with-generative-ai/)). Eval and observability tools such as [Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues) and [Braintrust](https://www.braintrust.dev/blog/human-review-golden-datasets) now own much of the "human review for agents" loop. Classic labeling tools never covered it well. MoLabel's opening is the open, self-hosted version of that loop, which an agent can drive end to end and which works with no LLM key.

## Who uses it

- **An agent** (Claude Code, Codex, a CI job) runs the CLI or, later, an MCP server. It imports data, sets up schemas, runs pre-labels and judges, routes work into queues, computes agreement, and promotes reviewed items into the gold set. It needs JSON on every command, real exit codes, and stable IDs.
- **A reviewer** (a domain expert, often not an engineer) works one queue item at a time from the keyboard. They score, correct, and move on.
- **An adjudicator or lead** resolves disagreements, watches agreement and judge calibration, and decides what becomes gold.

## Core loops

**Human loop.** Open a queue, then score, correct, and move to the next item. Four queue kinds borrow the Langfuse and Braintrust shape. Triage marks items ignore, review, or duplicate. Review fills in `expected`, rubric scores and notes. Calibrate gives overlapping items to several people so agreement can be measured. Adjudicate resolves the disagreements. Reviewed items are then promoted into the gold set.

**Agent loop.** Import, then run cheap deterministic checks (JSON schema, exact match), and only then spend tokens on a pre-label or judge. Route uncertain, rare or high-risk items to people. Read agreement and judge-vs-human reports. Promote, export, and commit the gold set.

**Flywheel.** New failures from production traces or workflow runs are appended to the gold set, deduplicated, and versioned. A frozen gold set goes stale ([Hamza Tahir](https://x.com/htahir111/status/2082141596779237693), [@VeraxVault](https://x.com/VeraxVault/status/2118885909387206791)).

## Principles the product enforces

1. **Human review works with no LLM key.** Label Studio, Argilla and doccano all allow this. Today MoLabel's documented flow cannot reach review without a key, which is a bug. An offline provider and a human-first route fix it.
2. **Guard against suggestion bias.** Showing LLM suggestions did not make annotators faster, but it shifted the labels and inflated later model-vs-gold scores ([Pangakis and Wolters, ACL 2025 Findings](https://aclanthology.org/2025.findings-acl.1323.pdf)). MoLabel already has blind review and an explicit AI reveal (`apply_blind_review_policy`, `reveal_ai` in the queue API). The plan adds blind first-pass labels as a queue setting and audit samples drawn from *accepted* pre-labels, not only corrections.
3. **Calibrate the judge before trusting it.** Use the same rubric for people and the judge, written as atomic yes/no criteria rather than one holistic 1 to 5 score ([BINEVAL via @omarsar0](https://x.com/omarsar0/status/2070942495832470001), [PAJAMA](https://x.com/zihengh1/status/2072726001742713310)). Calibrate in order: people, rubric, a small labeled set, disagreements, then the judge ([Donghao Yang](https://x.com/KuaiQ34888/status/2074462785157882344), [DataTalksClub](https://x.com/DataTalksClub/status/1996127265844068458)). Report judge-vs-human kappa, F1 and a confusion matrix, because the choice of judge alone can swing a score from 10% to 43.5% ([@battista212](https://x.com/battista212/status/2034579193682411884)). See also [Dietz et al.](https://www.cs.unh.edu/~dietz/papers/dietz2025principles.pdf) and [Kangwook Lee](https://x.com/Kangwook_Lee/status/2008721275787604037).
4. **Agreement metrics ship in the open product.** Cohen's kappa, Fleiss' kappa and Krippendorff's alpha stay free, in the public repo. Label Studio Community has none of its "Quality Workflows" features. Agreement metrics are limited in Starter Cloud and full only in Enterprise ([Label Studio editions](https://labelstud.io/guide/label_studio_compare)). That makes free agreement metrics a real differentiator, so they must be correct. One correctness fix comes first, in its own PR before the GUI. `agreement_metrics.py` computes `krippendorff_alpha` from the Fleiss expected-agreement term, without the coincidence matrix and n/(n-1) correction that alpha requires. PR P5b replaces it with a real alpha and tests every metric against published reference values.
5. **Gold sets are files in git.** The released gold set is JSONL (Parquet for large sets) with a schema, an append log for new failures, and dedupe on a content hash. Working review state stays in SQLite. That draws the "file-canonical" line honestly. Config and gold sets are files. The review in progress is a database. (Decided by Mobi, Nov 15.)

## Comparison

| | Label Studio | Argilla | doccano | MoLabel target |
|---|---|---|---|---|
| Review without an LLM key | yes | yes | yes | yes (offline provider) |
| Agent-drivable surface | SDK, REST | Python SDK | REST | JSON CLI, REST, MCP (planned) |
| Agreement and IAA | paid tiers only (limited in Starter Cloud, full in Enterprise) | not checked | none in the docs | Cohen, Fleiss, Krippendorff, free |
| Model suggestions | ML backend pre-annotation | suggestions vs answers | none | pre-labels, judges, offline provider |
| Data types | broad multi-modal | text, LLM feedback | text | text and structured records first |

Sources: [Label Studio](https://github.com/HumanSignal/label-studio), [Argilla](https://github.com/argilla-io/argilla), [doccano](https://github.com/doccano/doccano), as summarized in the Nov 15, 2026 research note. The agreement row was checked on Nov 16, 2026 against the [Label Studio editions page](https://labelstud.io/guide/label_studio_compare) and the [doccano docs](https://doccano.github.io/doccano/), which do not mention agreement metrics. The Argilla cell was not checked. Judge calibration, blind first-pass labels and versioned gold sets are MoLabel targets. This doc does not claim the others lack them. MoLabel should not chase Label Studio's media breadth. [DataLabel](https://github.com/liuxiaotong/data-label) is the closest open example of CLI, MCP, IAA and adjudication together, and is worth reading end to end. [Potato](https://github.com/davidjurgens/potato) has strong calibration-room and agent-trace patterns, but it is GPL-3.0. MoLabel is Apache-2.0, so Potato is a pattern reference only and none of its code is copied.

## Keep, cut, add

**Keep.** The CLI with its bundled agent skills. The FastAPI service. Workflows, blind review and AI reveal, adjudication, corrections, agreement metrics, grounded benchmarks, releases and audit.

**Cut.** The assistant route and panel, which the PRD already removed from the product. The `molabel-depolarize` package, which is one docstring line. The `src-tauri` stub. The SSE stubs, which send one "connected" event and then only keepalives. Ten mock frontend pages and their unused dependencies. The internal agent prompts in `docs/implementation/`.

**Add.** An offline provider. A real queue GUI. Gold-set versioning with append and dedupe. Judge calibration on atomic rubrics, with cheap checks before any token is spent. Blind-label and accepted-pre-label audit queues. An MCP server ([fastapi-mcp](https://github.com/tadata-org/fastapi_mcp)), planned after the API contract is solid. Later, a "likely label errors first" queue order via [Cleanlab](https://github.com/cleanlab/cleanlab), once model probabilities exist.

## Target architecture

```
 agents ──► molabel CLI (TS, JSON out) ──┐
 agents ──► MCP server (planned) ────────┤
 people ──► review GUI (React queue) ────┼──► FastAPI service ──► molabel-core
                                         │       │                 │
                                         │    SQLite (working      ├─ providers (incl. offline)
                                         │    state, Alembic)      ├─ quality (Polars metrics)
                                         │                          └─ export (JSONL / Parquet)
                                         └── workspace files: schemas, prompts, workflows, gold sets (git)
```

One service layer serves every client. The CLI, GUI and MCP server all call the same REST API, so a behavior fix lands once. Tables are created by Alembic only, never by `CREATE TABLE` inside a route. The server writes only inside a validated workspace root, never into the folder it was launched from.

## GUI scope

The GUI is a keyboard-first review and adjudication queue, not a multi-page platform. It ships these screens, all wired to the real API:

1. **Queue list.** The queues in a workspace, with their kind (triage, review, calibrate, adjudicate) and progress.
2. **Item review.** One record, the rubric (pass/fail, categorical, notes), and an optional corrected `expected`. Keys follow [Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues): 1 to 9 for categories, Ctrl/Cmd+Enter to complete and advance, and J/K for next and previous. AI suggestions stay hidden until revealed when the queue is blind.
3. **Adjudication.** Disagreements side by side, with a pick-or-write resolution.
4. **Calibration and gold.** Agreement and judge-vs-human numbers for a queue, and a "promote to gold" action.

Anything else, such as dataset browsing or workflow building, stays in the CLI until a reviewer needs it. The browser loads one item at a time with a small prefetch window, never the whole dataset.

## Performance stance

There will be no rewrite in another language. MoLabel's bottlenecks today are correctness and product shape, and a rewrite would fix neither. The plan profiles four real paths (ingest, queries, benchmark and agreement computation, export) and reports the numbers. Polars or DuckDB from Python goes in where the profile shows a gain of at least 3x ([Plotly comparison](https://plotly.com/blog/duckdb-vs-polars-vs-pandas/)). Polars fits agreement and benchmark transforms in the API process. DuckDB fits large JSONL or Parquet gold sets queried in place. A Rust module via PyO3 and [pyo3-arrow](https://docs.rs/pyo3-arrow/latest/pyo3_arrow/) is considered only for a proven hot loop with at least a 3x measured gain, and it keeps a pure-Python fallback.

## PR plan

Each PR is small, stacked, and records its test, lint and typecheck numbers.

| # | PR | Scope |
|---|---|---|
| P0 | #2 green CI | Skip the 33 fixture-data tests (issue #3), add a CLI CI job |
| P1 | Agent contract | Exit 0 for `--help` and `--version`, non-zero on a failed `workflow run`, a clean token, `queue list`, one review decision name, templates bound to the created dataset and schema, `--json` everywhere |
| P2 | State and safety | No database in the launch folder, an honest file-canonical boundary, validated `workspace_root`, Alembic-only tables |
| P3a | starlette upgrade | Python security bump on its own |
| P3b | npm majors | vitest@5, @hey-api/openapi-ts |
| P4 | Cut dead weight | Assistant, depolarize, `src-tauri`, SSE stubs, unused frontend files and deps, internal prompts, accurate AGENTS.md and CLAUDE.md. Format the existing CLI files with prettier, then add `prettier --check` to the CLI CI job |
| P5 | Offline provider | Deterministic heuristic pre-labels, so the full flow runs with no key. Done means a no-key end-to-end smoke test in CI: import, offline pre-label, review, export |
| P5b | Agreement metrics correctness | Real Krippendorff's alpha (coincidence matrix, n/(n-1) correction). Cohen, Fleiss and alpha tested against published reference values |
| P6 | Review GUI | The four screens above, on the real API, with the mock pages deleted |
| P7 | Performance | Profile, report, and adopt Polars or DuckDB only where the gain is at least 3x |
| P8 | Gold sets | Promote to gold, git-versioned JSONL, append failures, dedupe |
| P9 | Bias and judge calibration | Blind first-pass labels, accepted-pre-label audits, atomic rubrics, cheap checks before the judge, judge-vs-human report |
| P10 | MCP server | fastapi-mcp over the same API (planned) |

P8 to P10 come from the research and follow the locked order. Mobi approved them on Nov 15. P5b moved out of P7 on Nov 16 after review, because free and correct agreement metrics are a headline claim.

The newcomer loop has one definition of done, the P5 smoke test. It runs in CI with no API key: import, offline pre-label, review, export.

Other decisions from Nov 15: the review decision vocabulary is `accept`, `edit` and `reject`. Whether an AI suggestion was shown is a separate field (`ai_revealed`, plus a diff against the pre-label), and `accept_ai` stays an alias for one release.
