# MoLabel Full Upgrade Final Checklist

Date: 2026-05-16
Status: implementation-complete with one external live-provider evidence blocker

This checklist is the working definition of the finished MoLabel full-system upgrade. Items are checked only when the connected code path and verification evidence exist.

## Core Operating Model

- [x] CLI-first agent operation through public `molabel` commands.
- [x] MiniMax default model identity set to `MiniMax-M2.7-highspeed`.
- [x] Backend API remains the contract behind the CLI.
- [x] Canonical workspace artifacts live under stable `workbench/` paths.
- [x] Release proof manifests persist under the workspace release namespace.
- [x] Audit events persist for release and artifact proposal decisions.
- [x] Agent-run failure envelopes classify auth failures, timeouts, malformed output, empty output, validation failures, partial failures, and retry exhaustion.

## Artifact Safety And Traceability

- [x] Agents create durable artifact proposals instead of silently writing canonical files.
- [x] Artifact proposal accept/reject decisions persist.
- [x] Proposal create/accept/reject events appear in the audit ledger.
- [x] Direct artifact writes require `expected_hash` when overwriting an existing canonical file.
- [x] Proposal acceptance rejects stale files when the canonical artifact changed after proposal creation.
- [x] Artifact trace includes source hash, proposed hash, current hash, target path, run id, actor, decision state, audit event pointers, and release/proof linkage when available.
- [x] Workspace diff/apply/reject handles proposed, rejected, accepted, conflicted, and stale proposals predictably through CLI/API contracts.
- [x] No-silent-overwrite tests cover canonical artifact namespaces.

## Workflow, Review, And Research Support

- [x] Workflow review-gate integration failures are resolved in the checked integration suite.
- [x] Parser coverage failure is resolved in the checked non-live e2e suite.
- [x] Psychology survey/codebook workflow template exists.
- [x] Codebook CLI validation command exists.
- [x] Psychology/research benchmark pack exists and is verified.
- [x] Psychology/research workflow has a file-backed end-to-end fixture contract.
- [x] Review/adjudication release gates are tested against computed validation gates and unresolved failure cases.
- [x] Task schemas now support option-level rubric descriptions so crowded label spaces can be made agent-friendly instead of relying on raw label strings.

## Provider And Runtime Reliability

- [x] Provider health reports resolved base URL, auth ref, model id, reachable, authenticated, and model-valid fields without exposing secrets.
- [x] MiniMax live smoke path is verified.
- [x] Live grounded model benchmark path is verified for classification, rationale/moderation, and evidence verification.
- [x] Guided MiniMax CLI-operator path is verified on clinc150.
- [x] Guided MiniMax CLI-operator path is verified across evidence/rationale families beyond clinc150.
- [x] BANKING77 near-neighbor label gap is fixed with reusable option rubrics and re-verified live at 16/16 exact matches.
- [x] Raw freeform MiniMax shell operation is explicitly excluded from the finished operating contract; the certified operating path is the guided public-CLI operator.
- [x] Live benchmark runner supports sequential cooldowns and classifies provider usage-limit failures as rate-limit pressure instead of ambiguous infrastructure failures.

## Benchmark And Release Certification

- [x] Grounded benchmark catalog covers 18 fixture families.
- [x] Benchmark pack verifier command exists with strict mode.
- [x] Release certification command exists.
- [x] Release approval blocks failed computed validation gates.
- [x] Release detail can reconstruct validation/proof state from proof manifests.
- [x] Every grounded benchmark unit family passes in the checked final sweep.
- [x] Benchmark fixture verifier covers the added psychology/research pack.
- [x] Final live grounded model sweep covers six required MiniMax benchmark families: clinc150, HateXplain, FEVEROUS, BANKING77, GoEmotions, and SciFact.
- [x] Final live guided operator sweep completed all six families after harness repair, with five acceptable and BANKING77 identified as a real quality gap.
- [x] BANKING77 was repaired through visible option rubrics and passed targeted live operator rerun with `1.0000` label/checklist/overall scores.
- [ ] Final all-in-one post-repair live operator aggregate is blocked by current MiniMax provider quota: `429 usage limit exceeded (2056)` after cooldown. This is an external evidence blocker, not an unchecked implementation item.

## GUI Control Room Parity

- [x] GUI build and tests pass in the checked suite.
- [x] GUI exposes or links to artifact trace, semantic diff review, audit timeline, provider health, and release certification status through the Operations page.
- [x] GUI/API parity is represented in the checked frontend tests plus backend API/CLI contracts for review, adjudication, semantic diff review, artifact trace, provider health, and release certification.

## Final Verification Gates

- [x] Python unit suite passes.
- [x] Python integration suite passes.
- [x] Non-live e2e suite passes.
- [x] CLI lint/build/tests pass.
- [x] Frontend lint/build/tests pass.
- [x] Ruff passes.
- [x] Grounded benchmark unit sweep passes after final code changes.
- [x] Live MiniMax targeted BANKING77 operator rerun passes after option-rubric repair.
- [x] Provider quota failure from the final cooled full aggregate is recorded under `reports/full-upgrade-final-2026-05-16-final-cooldown/`.
- [ ] Rerun the final all-in-one live operator aggregate when MiniMax quota recovers.
