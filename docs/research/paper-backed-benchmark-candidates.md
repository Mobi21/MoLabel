# Paper-Backed Benchmark Candidates And Scoring Requirements

Date: 2026-04-03
Status: Research note for benchmark planning only
Related:

- `docs/research/grounded-benchmark-system.md`
- `docs/research/grounded-benchmark-clinc150.md`
- `docs/research/grounded-benchmark-feverous.md`
- `docs/research/grounded-benchmark-hatexplain.md`
- `docs/prd/agent-benchmark-and-evaluation.md`

## 1. Purpose

This note extends the current grounded benchmark work from one-off paper notes
into a reusable taxonomy of benchmark families.

The goal is not to commit to new fixtures yet. The goal is to make the next
paper-backed benchmark additions legible and implementable:

- which papers are strong candidates,
- which task families they represent,
- which paper-specific metrics and artifact checks each family needs,
- and which MoLabel capabilities should be built once and then reused.

CLINC150 remains the current grounded classification starting point. The focus
here is cross-paper expansion.

Support requirements below are design recommendations inferred from the task
contracts in the cited papers and benchmark docs. They are not claims that the
papers themselves require MoLabel to implement a specific product surface.

## 2. Selection Criteria

Strong MoLabel benchmark candidates should meet most of these conditions:

- the paper defines a stable task contract and an accepted primary metric,
- the dataset is public or at least sliceable with clear provenance,
- the task benefits from review, adjudication, or evidence inspection,
- the benchmark exposes more than raw accuracy,
- a small but faithful authority-pack slice is realistic,
- and the task pressures the CLI-first operating model rather than only the
  underlying model.

## 3. Benchmark Taxonomy

| Task type | Strong paper-backed candidates | Paper-specific metrics beyond plain accuracy | Artifact checks MoLabel should support | Highest-priority MoLabel gaps |
|---|---|---|---|---|
| Classification | [CLINC150](https://aclanthology.org/D19-1131/), [BANKING77](https://arxiv.org/abs/2003.04807), [MASSIVE](https://aclanthology.org/2023.acl-long.235/) | macro F1, OOS recall, per-intent recall, calibration and abstention curves | one valid label per record, valid OOS handling, label-map integrity | selective prediction, calibration reporting, intent confusion analysis |
| Multi-label classification | [GoEmotions](https://aclanthology.org/2020.acl-main.372/), [EURLEX57K](https://arxiv.org/abs/1905.10892) | micro/macro F1, Jaccard, exact-set match, tail-label recall | duplicate-label rejection, hierarchy consistency, thresholded set outputs | set-valued labels, hierarchical taxonomy validation, threshold tuning |
| Extraction / span labeling | [CUAD](https://arxiv.org/abs/2103.06268), [MultiSpanQA](https://aclanthology.org/2022.naacl-main.90/) | token/span F1, overlap or IoU, field-normalization accuracy, multi-span EM/F1 | offsets must resolve into source text, overlap rules, normalized value checks | span-native annotations, normalization pipelines, multi-span outputs |
| Evidence attribution | [Evidence Inference 2.0](https://aclanthology.org/2020.bionlp-1.13/), [ERASER](https://aclanthology.org/2020.acl-main.408/) | evidence precision/recall/F1, plausibility, comprehensiveness, sufficiency | cited evidence units must exist, no dangling evidence ids, completeness of evidence sets | rationale/evidence schemas, faithfulness scoring hooks, sentence/span anchoring |
| Fact verification | [FEVEROUS](https://arxiv.org/abs/2106.05707), [SciFact](https://aclanthology.org/2020.emnlp-main.609/), [FEVER](https://aclanthology.org/N18-1074/) | verdict plus evidence joint score, evidence F1, NEI quality, retrieval recall | valid verdict labels, complete gold evidence-set matching, table-cell refs if present | nested evidence sets, joint scorers, retrieval-plus-verification reports |
| Retrieval / ranking | [BEIR](https://arxiv.org/abs/2104.08663), [MS MARCO](https://arxiv.org/abs/1611.09268) | MRR, nDCG@K, Recall@K, MAP, cost-latency tradeoffs | ranking depth, stable corpus hashes, no duplicate ids, qrels consistency | ranked-result artifact type, qrels ingestion, retrieval run comparators |
| QA with evidence | [HotpotQA](https://aclanthology.org/D18-1259/), [QASPER](https://arxiv.org/abs/2105.03011), [Natural Questions](https://aclanthology.org/Q19-1026/) | answer EM/F1 plus supporting-facts EM/F1 plus joint score, answerability metrics | evidence sentences must exist, multi-hop completeness, answer normalization | joint answer-plus-evidence schemas, unanswerable handling, multi-doc support |
| Structured generation | [ToTTo](https://aclanthology.org/2020.emnlp-main.89/), [WebNLG](https://aclanthology.org/W17-3518/) | grounded generation metrics such as PARENT, content-selection precision, unsupported-content rate | generated fields must be traceable to highlighted cells or source triples | grounded-generation scorers, source-coverage checks, hallucination validators |
| Toxicity / hate speech / rationale | [HateXplain](https://arxiv.org/abs/2012.10289), [Toxic Spans](https://aclanthology.org/2022.acl-long.259/), [Social Bias Frames](https://aclanthology.org/2020.acl-main.486/) | macro F1, per-target F1, rationale token F1, plausibility and faithfulness, fairness slices | target-group fields valid, rationale spans align, label-rationale coherence | target-community fields, bias-slice reporting, rationale faithfulness scoring |
| Table / document grounding | [TabFact](https://arxiv.org/abs/1909.02164), [DocVQA](https://openaccess.thecvf.com/content/WACV2021/html/Mathew_DocVQA_A_Dataset_for_VQA_on_Document_Images_WACV_2021_paper.html), [doc2dial](https://aclanthology.org/2020.emnlp-main.652/) | table-verdict accuracy with cell grounding, ANLS for document QA, grounding precision/recall | stable row/col ids, section/page/cell anchors, OCR-normalized text integrity | hierarchical document anchors, cell references, optional page-region support |

## 4. Cross-Cutting Scorer And Checker Primitives

MoLabel should not add paper support one scorer at a time. The right move is to
add reusable benchmark primitives and then map each paper into them.

### 4.1 Label-Set Scoring

Needed for GoEmotions, EURLEX57K, Social Bias Frames, and any overlapping-label
taxonomy work.

Core support:

- micro, macro, weighted, and per-label F1,
- Jaccard and exact-set metrics,
- threshold sweeps for score-to-label conversion,
- and hierarchy-aware validation for parent-child label rules.

### 4.2 Span And Offset Scoring

Needed for CUAD, MultiSpanQA, Toxic Spans, and rationale-bearing tasks.

Core support:

- exact-match scoring for contiguous or discontiguous spans,
- token-level precision, recall, and F1,
- partial-overlap scoring for near-miss spans,
- and normalization-aware comparison for extracted values.

### 4.3 Evidence-Set Scoring

Needed for FEVER, FEVEROUS, SciFact, HotpotQA, QASPER, and Evidence Inference.

Core support:

- nested evidence-set semantics,
- verdict plus evidence joint metrics,
- evidence precision, recall, and F1,
- retrieval recall over gold evidence units,
- and support for multiple acceptable gold evidence sets.

### 4.4 Ranking And Retrieval Scoring

Needed for BEIR, MS MARCO, FEVER-style retrieval stages, and evidence-first QA.

Core support:

- MRR,
- nDCG at configurable cutoffs,
- Recall@K and Precision@K,
- MAP where relevant,
- and latency and cost sidecars so retrieval quality is not evaluated in
  isolation from operator practicality.

### 4.5 Grounded Generation Scoring

Needed for ToTTo and eventually other schema-bound or table-grounded generation
benchmarks.

Core support:

- text-quality metrics only as secondary diagnostics,
- source-grounded factuality checks as the primary measure,
- unsupported-content detection,
- source-coverage checks,
- and structure-aware validation when outputs must conform to a schema or
  one-sentence constraint.

### 4.6 Calibration, Abstention, And Escalation Scoring

Needed across ambiguous classification, verification, moderation, and QA tasks.

Core support:

- coverage-versus-risk reporting,
- abstain precision and recall,
- expected calibration error or Brier-style diagnostics,
- and benchmark rules for when operator review should be preferred over forced
  low-confidence automation.

### 4.7 Review And Adjudication Scoring

Needed wherever the benchmark includes simulated humans or disagreement.

Core support:

- whether the agent routed the right cases to review,
- whether obviously flawed human inputs were challenged,
- whether disagreements were preserved rather than flattened,
- and whether final adjudication improved or degraded task quality.

## 5. Recommended Candidate Families

### 5.1 Classification

Primary next candidate:

- [BANKING77](https://arxiv.org/abs/2003.04807)

Secondary candidates:

- [CLINC150](https://aclanthology.org/D19-1131/) as the existing baseline and
  continued smoke fixture
- [MASSIVE](https://aclanthology.org/2023.acl-long.235/) once multilingual
  support is worth the added surface

Why this is a good fit for MoLabel:

- intent datasets are compact enough for repeatable operator runs,
- fine-grained intent confusion exposes rubric quality rather than only model
  strength,
- and out-of-scope or low-confidence routing is directly relevant to review
  workflows.

Expected benchmark shape:

- one utterance per record,
- single label from a fixed intent map,
- optional `oos` or abstain path,
- and a benchmark slice that preserves common confusions rather than only easy
  intents.

Likely operational concerns:

- class imbalance,
- near-duplicate paraphrases,
- OOS thresholding,
- and few-shot versus full-data benchmark profiles.

Paper-specific metrics needed:

- macro F1,
- per-intent recall,
- OOS precision and recall where the paper supports it,
- confusion concentration for high-overlap intents,
- and calibration or selective-prediction curves for review routing.

Paper-specific artifact checks needed:

- exactly one label per record,
- all labels must resolve through the authority-pack label map,
- abstain or OOS must be explicit rather than encoded as an invalid label,
- and explanation or rationale fields must not silently substitute for the
  scored label.

What MoLabel would need to add to support it well:

- first-class abstain and low-confidence review routing,
- confusion-matrix reporting in benchmark summaries,
- and calibration reporting rather than accuracy-only quality pages.

### 5.2 Multi-Label Classification

Primary next candidate:

- [GoEmotions](https://aclanthology.org/2020.acl-main.372/)

Secondary candidate:

- [EURLEX57K](https://arxiv.org/abs/1905.10892)

Why this is a good fit for MoLabel:

- MoLabel should prove it can handle overlapping labels rather than only
  single-choice tasks,
- GoEmotions brings ambiguity and annotator disagreement,
- and EURLEX57K brings long-document, long-tail label behavior.

Expected benchmark shape:

- one text document per record,
- zero or more labels from a controlled vocabulary,
- optional hierarchy or parent-child constraints,
- and thresholded outputs if the model emits scores.

Likely operational concerns:

- long-tail labels,
- threshold sensitivity,
- partial annotator disagreement,
- and documents whose length makes manual review slower and more selective.

Paper-specific metrics needed:

- micro F1,
- macro F1,
- Jaccard,
- exact-set match as a harsh secondary metric,
- and per-label support-aware diagnostics for tail labels.

Paper-specific artifact checks needed:

- no duplicate labels in a prediction set,
- no labels outside the authority-pack vocabulary,
- hierarchy rules must hold if the label space is structured,
- and blank prediction sets must be distinguishable from parser failures.

What MoLabel would need to add to support it well:

- set-valued label outputs,
- threshold configuration and sweeps,
- hierarchy-aware validation,
- and review UIs that let operators compare two label sets cleanly.

### 5.3 Extraction / Span Labeling

Primary next candidate:

- [CUAD](https://arxiv.org/abs/2103.06268)

Secondary candidate:

- [MultiSpanQA](https://aclanthology.org/2022.naacl-main.90/)

Why this is a good fit for MoLabel:

- the task is operationally close to real review work,
- CUAD turns extraction into a human-audit problem instead of a pure sequence
  labeling problem,
- and MultiSpanQA forces MoLabel to support discontiguous multi-span answers.

Expected benchmark shape:

- one long source document per record or per question-document pair,
- one or more text spans or extracted fields,
- optional normalized values derived from raw spans,
- and in some cases "no span" or "no related clause" outputs.

Likely operational concerns:

- long documents,
- overlapping spans,
- sentence-boundary versus token-boundary mismatches,
- and normalization disagreements even when the source span is correct.

Paper-specific metrics needed:

- token-level precision, recall, and F1,
- exact span match,
- partial-overlap metrics for near misses,
- field-normalization accuracy,
- and separate scoring for extraction presence versus extraction boundaries.

Paper-specific artifact checks needed:

- every stored offset must resolve into the canonical source text,
- discontiguous spans must keep stable ordering,
- overlap must obey the task rules,
- and normalized fields must trace back to the selected span set.

What MoLabel would need to add to support it well:

- span-native task schemas,
- char-offset and token-offset storage,
- multi-span outputs,
- and reusable normalizers plus validators for post-processed extracted fields.

### 5.4 Evidence Attribution

Primary next candidate:

- [Evidence Inference 2.0](https://aclanthology.org/2020.bionlp-1.13/)

Secondary candidate:

- [ERASER](https://aclanthology.org/2020.acl-main.408/) as the rationale metric
  umbrella and multi-dataset standard

Why this is a good fit for MoLabel:

- evidence attribution is where review, challenge, and adjudication become
  essential,
- the task is not solved by label correctness alone,
- and the papers already motivate rationale plausibility and faithfulness rather
  than only span overlap.

Expected benchmark shape:

- one prompt or claim paired with a long document,
- one decision label,
- one or more supporting evidence spans or sentences,
- and sometimes explicit intervention/comparator/outcome metadata.

Likely operational concerns:

- very long inputs,
- multiple valid evidence locations,
- ambiguous or incomplete human evidence selections,
- and evidence that is sufficient for a label but not minimal.

Paper-specific metrics needed:

- evidence precision, recall, and F1,
- rationale plausibility,
- comprehensiveness,
- sufficiency,
- and decision-plus-evidence joint metrics.

Paper-specific artifact checks needed:

- every evidence pointer must resolve into a valid document unit,
- evidence must be attached to the scored prediction rather than stored as free
  text,
- evidence groups must remain complete,
- and "no evidence" must be explicit where permitted.

What MoLabel would need to add to support it well:

- sentence- and span-level evidence anchors,
- faithfulness-evaluator hooks,
- grouped evidence outputs rather than one flat rationale blob,
- and benchmark reports that separate label correctness from evidence quality.

### 5.5 Fact Verification

Primary next candidate:

- [FEVEROUS](https://arxiv.org/abs/2106.05707)

Secondary candidates:

- [SciFact](https://aclanthology.org/2020.emnlp-main.609/)
- [FEVER](https://aclanthology.org/N18-1074/) as a sentence-only fallback if a
  simpler verification pack is needed

Why this is a good fit for MoLabel:

- verdict and evidence must both be preserved,
- FEVEROUS already aligns with MoLabel's grounded benchmark direction,
- and SciFact adds domain-specific verification over scientific literature.

Expected benchmark shape:

- one claim per record,
- one verdict from a closed set such as support, refute, or NEI,
- retrieved or selected evidence units,
- and sometimes mixed text plus table evidence.

Likely operational concerns:

- multi-hop evidence assembly,
- retrieval errors masking reasoning errors,
- nested evidence-set semantics,
- and the need to keep NEI distinct from unsupported but overconfident verdicts.

Paper-specific metrics needed:

- paper-faithful joint verdict-plus-evidence score,
- verdict accuracy,
- evidence precision, recall, and F1,
- NEI precision and recall,
- and retrieval recall over gold evidence units.

Paper-specific artifact checks needed:

- verdict label must be from the official label space,
- table evidence references must resolve to stable cell ids where relevant,
- evidence must satisfy at least one complete gold evidence set for joint
  success,
- and NEI predictions must not carry fabricated supporting evidence.

What MoLabel would need to add to support it well:

- nested evidence-set scoring,
- stable text and table evidence anchors,
- stage-separated retrieval versus verification reporting,
- and explicit joint-score support in the benchmark summary model.

### 5.6 Retrieval / Ranking

Primary next candidate:

- [BEIR](https://arxiv.org/abs/2104.08663)

Secondary candidate:

- [MS MARCO](https://arxiv.org/abs/1611.09268) for a simpler ranking-first
  benchmark profile

Why this is a good fit for MoLabel:

- retrieval is increasingly the front half of evidence-grounded work,
- BEIR stresses generalization across domains instead of one tuned corpus,
- and ranking quality should be measurable before answer generation starts.

Expected benchmark shape:

- one query per record,
- one ranked list of document or passage ids,
- optional reranking stage outputs,
- and stable qrels stored in the authority pack.

Likely operational concerns:

- large corpora,
- reproducible indexing,
- score cutoffs that affect cost,
- and benchmark drift if corpus versions are not locked.

Paper-specific metrics needed:

- nDCG at fixed cutoffs,
- MRR,
- Recall@K,
- MAP where relevant,
- and quality-versus-latency comparisons for practical operator runs.

Paper-specific artifact checks needed:

- ranked outputs must use stable corpus ids,
- depth must be explicit and fixed,
- duplicate ids in a ranked list are invalid,
- and the run must declare which corpus snapshot was used.

What MoLabel would need to add to support it well:

- ranked-list artifacts,
- qrels ingestion,
- corpus snapshot hashing,
- and benchmark report views that compare first-stage retrieval to reranked
  retrieval.

### 5.7 QA With Evidence

Primary next candidate:

- [HotpotQA](https://aclanthology.org/D18-1259/)

Secondary candidates:

- [QASPER](https://arxiv.org/abs/2105.03011/)
- [Natural Questions](https://aclanthology.org/Q19-1026/)

Why this is a good fit for MoLabel:

- HotpotQA forces answer quality and evidence quality to move together,
- QASPER is a strong paper-reading benchmark for long scientific documents,
- and Natural Questions adds answerability and long versus short answer
  distinctions.

Expected benchmark shape:

- one question per record,
- one answer payload,
- one or more supporting facts or evidence units,
- and optional unanswerable or long-answer modes.

Likely operational concerns:

- answer normalization,
- multi-hop retrieval failures,
- more than one acceptable answer string,
- and evidence that is sufficient but not minimal.

Paper-specific metrics needed:

- answer exact match and token F1,
- supporting-facts exact match and F1,
- joint answer-plus-supporting-facts score,
- and answerability or abstention metrics for datasets with null cases.

Paper-specific artifact checks needed:

- evidence ids must resolve to valid source units,
- answer strings must use the dataset's normalization rules,
- multi-hop tasks must preserve all required hops,
- and unanswerable predictions must not attach fabricated support.

What MoLabel would need to add to support it well:

- joint answer-and-evidence schemas,
- answer normalization helpers,
- multi-document evidence handling,
- and explicit null-answer task support.

### 5.8 Structured Generation

Primary next candidate:

- [ToTTo](https://aclanthology.org/2020.emnlp-main.89/)

Secondary candidate:

- [WebNLG](https://aclanthology.org/W17-3518/)

Why this is a good fit for MoLabel:

- MoLabel should benchmark grounded generation, not only extraction and
  classification,
- ToTTo is controlled and therefore auditable,
- and the highlighted-cell contract is close to the kind of traceability MoLabel
  should preserve.

Expected benchmark shape:

- structured input such as a table or triple set,
- optional highlighted or selected source units,
- one constrained generation output,
- and paper-direct versus MoLabel-operated views if source annotations are
  projected.

Likely operational concerns:

- fluent but unsupported hallucinations,
- normalization differences that are semantically correct but paper-incorrect,
- and evaluation metrics that overreward style while missing grounding errors.

Paper-specific metrics needed:

- PARENT or another source-grounded generation metric,
- content-selection precision and recall,
- unsupported-content rate,
- and text metrics such as BLEU only as secondary diagnostics.

Paper-specific artifact checks needed:

- every selected input unit must exist in the source table or graph,
- output constraints such as one sentence must be enforced,
- generated facts should be traceable to selected source units,
- and unsupported copied text should be flagged separately from supported
  paraphrase.

What MoLabel would need to add to support it well:

- grounded-generation artifact types,
- source-coverage and hallucination checks,
- and benchmark-native comparison tools that show source units next to generated
  claims.

### 5.9 Toxicity / Hate Speech / Rationale Tasks

Primary next candidate:

- [HateXplain](https://arxiv.org/abs/2012.10289)

Secondary candidates:

- [Toxic Spans](https://aclanthology.org/2022.acl-long.259/)
- [Social Bias Frames](https://aclanthology.org/2020.acl-main.486/)

Why this is a good fit for MoLabel:

- moderation and rationale tasks are annotation-heavy and disagreement-heavy,
- HateXplain already bundles class labels, target communities, and rationales,
- and Social Bias Frames adds implied bias rather than only explicit abuse.

Expected benchmark shape:

- one post or comment per record,
- one label or structured bias frame,
- optional target-group fields,
- and optional rationale spans.

Likely operational concerns:

- severe class imbalance,
- ambiguous edge cases,
- unsafe content handling in fixtures and UI,
- and disagreement about whether a rationale is necessary or minimal.

Paper-specific metrics needed:

- macro F1,
- per-target or per-community F1,
- rationale token F1 or overlap,
- plausibility and faithfulness checks,
- and fairness slices across target groups.

Paper-specific artifact checks needed:

- target-group ids must come from the authority vocabulary,
- rationale spans must align to source text,
- label and rationale combinations must obey task rules,
- and operator overrides on sensitive cases should be auditable.

What MoLabel would need to add to support it well:

- target-community fields in task schemas,
- safer artifact display defaults,
- rationale faithfulness scoring,
- and quality summaries sliced by group rather than only overall label scores.

### 5.10 Table / Document Grounding

Primary next candidate:

- [TabFact](https://arxiv.org/abs/1909.02164)

Secondary candidates:

- [DocVQA](https://openaccess.thecvf.com/content/WACV2021/html/Mathew_DocVQA_A_Dataset_for_VQA_on_Document_Images_WACV_2021_paper.html)
- [doc2dial](https://aclanthology.org/2020.emnlp-main.652/)

Why this is a good fit for MoLabel:

- FEVEROUS mixes structured and unstructured evidence, but TabFact isolates the
  table-grounding problem cleanly,
- DocVQA is the right future benchmark once page-region support exists,
- and doc2dial is a lighter-weight document-grounding task if multimodal support
  is deferred.

Expected benchmark shape:

- one statement, question, or turn paired with a table or document,
- one answer or verdict,
- optional grounded cell, section, or page references,
- and possibly OCR-normalized text alongside raw document content.

Likely operational concerns:

- stable cell identifiers,
- OCR noise,
- multi-page context,
- and lossy projection from regions into text spans.

Paper-specific metrics needed:

- verdict accuracy plus grounded-cell precision and recall for table tasks,
- ANLS for document QA where the paper uses it,
- and answer-plus-grounding joint metrics once MoLabel supports region anchors.

Paper-specific artifact checks needed:

- row, column, and cell ids must be stable,
- page or section anchors must exist,
- OCR-normalized text must be versioned,
- and answers must be traceable to at least one grounded source unit.

What MoLabel would need to add to support it well:

- stable table-cell anchors,
- hierarchical document anchors,
- optional page-region or bounding-box support,
- and projection warnings whenever a paper-direct grounding format cannot be
  preserved losslessly.

## 6. Recommended Sequencing

Recommended order after the current CLINC150, FEVEROUS, and HateXplain work:

1. `BANKING77` for next-step classification that keeps operational complexity
   low.
2. `GoEmotions` for the first set-valued labeling benchmark.
3. `Evidence Inference 2.0` or `HotpotQA` to force evidence-first scoring
   primitives.
4. `BEIR` once ranked retrieval artifacts exist.
5. `CUAD` once span-native task schemas and long-document review flows are
   stable.
6. `ToTTo` once grounded-generation checks exist.
7. `TabFact` as the bridge from text-grounded verification to cell-grounded
   verification.
8. `DocVQA` only after document-region support is a conscious product decision.

## 7. Framework Gaps Before Full Support

The biggest framework gaps are not dataset-specific. They are reusable missing
capabilities:

- set-valued label support with threshold tuning,
- span-native task schemas with stable offsets,
- nested evidence-set scoring,
- ranked retrieval artifacts and qrels support,
- joint answer-plus-evidence scoring,
- grounded-generation scoring and hallucination checks,
- calibration and abstention reporting,
- target-group-aware moderation reporting,
- and stable text, table, and document anchor types that survive projection from
  paper-direct formats into MoLabel.

Without those capabilities, MoLabel can still ship benchmark slices, but the
result will overstate paper coverage and under-measure the actual operator and
review surfaces that the benchmark is supposed to test.
