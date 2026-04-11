# Grounded Benchmark Catalog

This guide is the benchmark-by-benchmark reference for the grounded benchmark
track in MoLabel.

Use it together with:

- `docs/guides/grounded-benchmark-framework.md` for harness execution,
  stage-aware scoring, evidence bundles, and operator audit behavior,
- `docs/guides/grounded-benchmark-authoring-checklist.md` for fixture authoring
  rules,
- and `fixtures/benchmarks-grounded/<benchmark-id>/authority/*` for the exact
  contract of an individual fixture.

## 1. How To Read The Catalog

Every grounded benchmark has the same top-level evaluation model:

- `paper_direct` means the fixture preserves the paper task contract as closely
  as the committed slice allows.
- `molabel_operated` means the same task is represented through MoLabel’s
  normalized artifact contract.
- `paper_model`, `molabel_model`, `workflow_autorun`, `workflow_reviewed`, and
  `operator_reviewed` stay distinct so the reports can show where quality was
  lost, preserved, or recovered.

The benchmark-specific sections below focus on:

- what the original task is,
- what artifact shape MoLabel evaluates,
- what the primary score rewards,
- and which semantics must not be flattened or silently normalized away.

## 2. Benchmark Families

The implemented grounded fixtures cover eight reusable benchmark families.

| Family | Core artifact | Main scorer pressure |
|---|---|---|
| Single-label classification | one label, sometimes with abstention or OOS routing | label accuracy, macro-F1, exact match |
| Multi-label classification | set-valued label outputs | set precision/recall/F1, Jaccard, exact match |
| Moderation with rationales | label plus targets plus token rationale mask | label quality plus rationale preservation |
| Evidence-backed verification | verdict/decision plus grouped evidence | verdict accuracy plus evidence completeness and joint correctness |
| QA with evidence | answer bundle with support facts or anchors | answer quality, support quality, joint answer-plus-support |
| Retrieval / ranking | ranked document ids with qrels | depth-sensitive ranking metrics |
| Span extraction | stable span offsets | overlap F1 and exact span match |
| Grounded generation | generated claims tied to anchors | source coverage and unsupported-content penalties |

## 3. Implemented Benchmarks At A Glance

| Benchmark | Family | Primary metric | Key semantic pressure |
|---|---|---|---|
| `clinc150` | single-label classification | `intent_accuracy` | intent plus explicit out-of-scope detection |
| `banking77` | single-label classification | `intent_accuracy` | fine-grained intent confusion under a closed label set |
| `goemotions` | multi-label classification | `emotion_set_f1` | valid label sets, not one-label collapse |
| `hatexplain` | moderation with rationales | `stance_macro_f1` | label, target communities, and token rationale mask |
| `feverous` | evidence-backed verification | `feverous_score` | verdict plus at least one complete gold evidence set |
| `scifact` | evidence-backed verification | `scifact_joint_score` | scientific claim verdict plus sentence evidence |
| `evidence-inference` | evidence-backed verification | `joint_effect_evidence` | intervention-effect decision plus grouped rationale evidence |
| `tabfact` | evidence-backed verification | `decision_accuracy` | table-grounded verdict with evidence cells |
| `hotpotqa` | QA with evidence | `joint_answer_support` | answer text plus supporting facts |
| `qasper` | QA with evidence | `joint_answer_support` | scientific QA plus evidence and unanswerable cases |
| `docvqa` | QA with evidence | `anls` | OCR-noisy answer matching plus support anchors |
| `beir` | retrieval / ranking | `ndcg_at_5` | ranking quality with qrels and depth-sensitive metrics |
| `msmarco` | retrieval / ranking | `mrr_at_5` | early precision in ranked passage retrieval |
| `cuad` | span extraction | `span_overlap_f1` | legal clause span boundaries and offsets |
| `multispanqa` | span extraction | `span_overlap_f1` | discontiguous multi-span extraction |
| `toxic-spans` | span extraction | `span_overlap_f1` | character-grounded toxic fragment detection |
| `totto` | grounded generation | `grounded_generation_score` | highlighted-cell-faithful sentence generation |
| `webnlg` | grounded generation | `grounded_generation_score` | triple-faithful data-to-text generation |

## 4. Benchmark Reference

### 4.1 `clinc150`

Single-intent classification with explicit out-of-scope handling.

- Paper task:
  - classify a user utterance into one intent or flag it as out of scope.
- MoLabel artifact contract:
  - `intent_label`
  - `is_out_of_scope`
- Primary metrics:
  - `intent_accuracy`
  - `oos_recall`
  - `intent_exact_match`
- What makes it meaningful:
  - the benchmark tests whether MoLabel preserves the distinction between the
    task label and the routing-style OOS decision instead of hiding OOS inside
    a label normalization shortcut.
- Do not flatten:
  - explicit OOS semantics,
  - paper-direct versus normalized MoLabel label names.

### 4.2 `banking77`

Fine-grained banking intent classification over a closed label set.

- Paper task:
  - assign one of the BANKING77 intents to each customer-service utterance.
- MoLabel artifact contract:
  - `intent_label`
- Primary metrics:
  - `intent_accuracy`
  - `intent_macro_f1`
  - `intent_exact_match`
- What makes it meaningful:
  - the committed slice is confusion-heavy, so regressions usually mean label
    normalization drift, invalid-vocabulary behavior, or degraded intent
    discrimination rather than generic model noise.
- Do not flatten:
  - the closed-set vocabulary,
  - invalid-label handling as a fake abstention path.

### 4.3 `goemotions`

Multi-label emotion classification with set-valued outputs.

- Paper task:
  - predict zero or more emotions from the GoEmotions label space.
- MoLabel artifact contract:
  - `emotion_labels`
- Primary metrics:
  - `emotion_set_f1`
  - `emotion_jaccard`
  - `emotion_set_precision`
  - `emotion_set_recall`
  - `emotion_exact_match`
- What makes it meaningful:
  - this benchmark proves that MoLabel can preserve a real multi-label task
    instead of collapsing it into one dominant label.
- Do not flatten:
  - valid empty-set versus parser failure,
  - duplicate-label rejection,
  - the distinction between paper-faithful multi-label semantics and a simpler
    single-label operational shortcut.
- Current reporting note:
  - the fixture reports set-valued metrics honestly; it does not overclaim
    paper-exact macro-F1 unless that scorer is actually present.

### 4.4 `hatexplain`

Hate-speech classification with target communities and token-level rationales.

- Paper task:
  - predict hate/offensive/normal style stance, affected communities, and the
    text evidence that justifies the decision.
- MoLabel artifact contract:
  - `stance_label`
  - `target_communities`
  - `rationale_token_mask`
- Primary metrics:
  - `stance_macro_f1`
  - `target_jaccard`
  - `rationale_token_f1`
  - `operational_exact_match`
- What makes it meaningful:
  - it tests whether MoLabel can carry both moderation labels and faithful
    rationale structure rather than reducing the task to a one-field classifier.
- Do not flatten:
  - token masks into prose summaries,
  - community targets into one free-text explanation field,
  - annotator disagreement into fake certainty.

### 4.5 `feverous`

Wikipedia claim verification with sentence and table-cell evidence.

- Paper task:
  - predict `SUPPORTS`, `REFUTES`, or `NOT ENOUGH INFO` and cite the evidence
    needed to justify the verdict.
- MoLabel artifact contract:
  - `verdict`
  - `evidence_sets`
  - `evidence_atoms`
- Primary metrics:
  - `feverous_score`
  - `verdict_accuracy`
  - `evidence_precision`
  - `evidence_recall`
  - `evidence_f1`
- What makes it meaningful:
  - paper-direct success requires the verdict plus at least one complete gold
    evidence set, so a correct label with incomplete support is still a real
    regression.
- Do not flatten:
  - grouped evidence into an unordered bag,
  - table-cell anchors into sentence-only evidence,
  - `NOT ENOUGH INFO` into a normal negative class.

### 4.6 `scifact`

Scientific claim verification against abstract evidence.

- Paper task:
  - predict `SUPPORT`, `CONTRADICT`, or `NOT_ENOUGH_INFO` and identify the
    abstract sentences that justify that outcome.
- MoLabel artifact contract:
  - `paper_label`
  - `verdict`
  - `paper_evidence_sets`
  - `evidence_atoms`
- Primary metrics:
  - `scifact_joint_score`
  - `verdict_accuracy`
  - `evidence_precision`
  - `evidence_recall`
  - `evidence_f1`
- What makes it meaningful:
  - it reuses FEVER-style evidence semantics in a scientific setting and
    exposes whether verdict quality and evidence quality move together.
- Do not flatten:
  - complete evidence sets into any-hit sentence overlap,
  - scientific contradiction into generic binary verification.

### 4.7 `evidence-inference`

Intervention-effect inference with grouped rationale evidence.

- Paper task:
  - infer whether an intervention significantly increases, decreases, or does
    not significantly change an outcome, and cite the evidence group that
    supports the decision.
- MoLabel artifact contract:
  - `paper_label`
  - `decision`
  - `evidence_bundle`
- Primary metrics:
  - `joint_effect_evidence`
  - `decision_accuracy`
  - `evidence_group_f1`
  - `evidence_group_exact_match`
- What makes it meaningful:
  - the benchmark only stays honest if the decision and evidence groups are
    scored jointly; decision-only scoring would overstate quality.
- Do not flatten:
  - grouped evidence into flat spans,
  - intervention direction into generic entailment labels.

### 4.8 `tabfact`

Table-grounded fact verification.

- Paper task:
  - judge whether a statement is entailed by a table and identify the relevant
    evidence cells.
- MoLabel artifact contract:
  - `decision`
  - `evidence_bundle`
- Primary metrics:
  - `decision_accuracy`
  - `joint_verdict_evidence`
  - `evidence_group_f1`
- What makes it meaningful:
  - this is the cleanest table-grounding verification slice, so it exposes
    whether MoLabel preserves cell-level evidence instead of sentence-only
    approximations.
- Do not flatten:
  - table cells into plain text passages,
  - evidence groups into unordered singletons when the table structure matters.

### 4.9 `hotpotqa`

Multi-hop QA with supporting facts.

- Paper task:
  - produce an answer and the supporting facts required for that answer.
- MoLabel artifact contract:
  - `qa_bundle`
  - answer text plus supporting-fact identifiers
- Primary metrics:
  - `joint_answer_support`
  - `answer_exact_match`
  - `answer_token_f1`
  - `supporting_fact_exact_match`
  - `supporting_fact_f1`
- What makes it meaningful:
  - the benchmark shows whether MoLabel can preserve multi-hop support
    structure instead of reporting answer text alone.
- Do not flatten:
  - answer-only success into full-task success,
  - supporting facts into free-form explanations.

### 4.10 `qasper`

Scientific question answering with evidence and explicit unanswerable cases.

- Paper task:
  - answer questions about scientific papers, provide evidence, and represent
    when a question is unanswerable from the source.
- MoLabel artifact contract:
  - `qa_bundle`
- Primary metrics:
  - `joint_answer_support`
  - `answer_exact_match`
  - `answer_token_f1`
  - `supporting_fact_f1`
- What makes it meaningful:
  - it tests scientific reading plus null handling, not just short-answer QA.
- Do not flatten:
  - unanswerable cases into low-confidence guesses,
  - paper evidence into generic sentence overlap.

### 4.11 `docvqa`

Document question answering on scanned pages.

- Paper task:
  - answer questions over OCR-heavy document pages.
- MoLabel artifact contract:
  - `qa_bundle`
  - answer plus support anchors
- Primary metrics:
  - `anls`
  - `joint_answer_support`
  - `supporting_fact_f1`
- What makes it meaningful:
  - it adds OCR noise and document anchoring pressure that text-only QA
    benchmarks do not have.
- Do not flatten:
  - anchor structure into plain extracted text,
  - ANLS into exact-match-only evaluation.

### 4.12 `beir`

General retrieval benchmark scored on ranked outputs.

- Paper task:
  - rank candidate documents for a query using qrels-backed relevance labels.
- MoLabel artifact contract:
  - `ranking`
- Primary metrics:
  - `ndcg_at_5`
  - `map`
  - `mrr`
  - `recall_at_5`
  - `precision_at_5`
- What makes it meaningful:
  - the benchmark exercises ranking depth, duplicate handling, and qrels-driven
    relevance rather than one-best retrieval.
- Do not flatten:
  - ranking into binary retrieved/not-retrieved,
  - fixed-depth behavior into arbitrary-length result lists.

### 4.13 `msmarco`

Passage ranking with emphasis on early precision.

- Paper task:
  - rank passages so the first relevant result appears as early as possible.
- MoLabel artifact contract:
  - `ranking`
- Primary metrics:
  - `mrr_at_5`
  - `recall_at_5`
  - `precision_at_5`
  - `map`
- What makes it meaningful:
  - it puts more pressure on top-of-list quality than broader ranking metrics
    do, which makes small ranking regressions easier to detect.
- Do not flatten:
  - reciprocal-rank semantics into unordered relevance.

### 4.14 `cuad`

Legal clause extraction with source-grounded spans.

- Paper task:
  - extract the contract span that answers a legal clause question.
- MoLabel artifact contract:
  - `spans`
- Primary metrics:
  - `span_overlap_f1`
  - `span_exact_match`
- What makes it meaningful:
  - legal extraction errors are often near-miss boundary errors, so overlap and
    exact span metrics both matter.
- Do not flatten:
  - offsets into answer text only,
  - multiple valid clauses into one normalized string.

### 4.15 `multispanqa`

Discontiguous answer extraction.

- Paper task:
  - extract all answer spans, including discontiguous ones.
- MoLabel artifact contract:
  - `spans`
- Primary metrics:
  - `span_overlap_f1`
  - `span_exact_match`
- What makes it meaningful:
  - the benchmark catches systems that only return one contiguous answer region
    when the task needs several.
- Do not flatten:
  - discontiguous spans into one merged snippet,
  - offset-bearing spans into plain text answers.

### 4.16 `toxic-spans`

Character-grounded toxic fragment detection.

- Paper task:
  - mark the toxic character spans inside a comment.
- MoLabel artifact contract:
  - `spans`
- Primary metrics:
  - `span_overlap_f1`
  - `span_exact_match`
- What makes it meaningful:
  - this fixture is sensitive to character offsets, not just token overlap or
    sentence-level toxicity classification.
- Do not flatten:
  - character spans into token labels without explicit conversion,
  - toxic-comment detection into toxic-span detection.

### 4.17 `totto`

Table-to-text generation with explicit highlighted cells.

- Paper task:
  - generate a sentence faithful to highlighted table cells.
- MoLabel artifact contract:
  - `generation`
- Primary metrics:
  - `grounded_generation_score`
  - `source_coverage`
  - `unsupported_content_rate`
- What makes it meaningful:
  - the task is grounded generation, not pure fluency; unsupported claims are a
    first-class regression.
- Do not flatten:
  - highlighted cells into generic table context,
  - grounded generation into text similarity alone.

### 4.18 `webnlg`

Triple-grounded data-to-text generation.

- Paper task:
  - verbalize RDF-style triples without hallucinating unsupported content.
- MoLabel artifact contract:
  - `generation`
- Primary metrics:
  - `grounded_generation_score`
  - `source_coverage`
  - `unsupported_content_rate`
- What makes it meaningful:
  - it tests whether generation stays faithful to structured source triples
    instead of drifting into plausible but unsupported prose.
- Do not flatten:
  - triple coverage into generic semantic similarity,
  - unsupported-content penalties into optional diagnostics.

## 5. What Different Regressions Usually Mean

- Classification regressions usually mean vocabulary drift, OOS handling drift,
  or label-map changes.
- Evidence benchmark regressions usually mean the verdict still works but the
  evidence grouping, completeness, or anchor structure broke.
- QA benchmark regressions usually mean answer normalization drift, support-fact
  serialization drift, or null-handling drift.
- Ranking benchmark regressions usually mean depth handling, duplicate result
  handling, or qrels ingestion changed.
- Span benchmark regressions usually mean offset calculations or normalization
  changed.
- Generation benchmark regressions usually mean source anchors were dropped or
  unsupported-content checks became looser.

When in doubt, inspect `authority/scenario.yaml`, `authority/metrics.yaml`, and
`authority/label-map.yaml` before changing scorer code.
