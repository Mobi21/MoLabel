# Grounded Benchmark Paper Map

Date: 2026-04-03
Status: Working research note
Related:

- `docs/research/paper-backed-benchmark-candidates.md`
- `docs/research/grounded-benchmark-system.md`
- `docs/research/grounded-benchmark-clinc150.md`

This note lists candidate papers and the extra metrics we should mine for each
benchmark family before we add more grounded slices.

It is the short index for the broader benchmark taxonomy. The more detailed
family breakdown lives in `docs/research/paper-backed-benchmark-candidates.md`.
The diagnostic metrics added to the CLINC grounded slice should be treated as
the minimum reusable baseline for every future family:

- proposal-vs-review deltas
- operator lift and regression rates
- command-audit counters
- artifact truthfulness checks
- repeated-run stability

## 1. Messy Text Classification

Candidate papers:

- [CLINC150: An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction](https://aclanthology.org/D19-1131/)

Metrics to mine:

- intent accuracy
- out-of-scope recall
- intent exact match
- per-label confusion matrix
- calibration and confidence/error correlation
- proposal-vs-review correction and regression rates

## 2. Chat And Conversation Review

Candidate papers:

- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)

Metrics to mine:

- pairwise win rate
- tie rate
- judge-human agreement
- category-level judge variance
- rubric adherence
- judge stability across repeated runs

## 3. Structured Document Extraction

Candidate papers:

- [FUNSD: A Dataset for Form Understanding in Noisy Scanned Documents](https://arxiv.org/abs/1905.13538)
- [DocVQA: A Dataset for VQA on Document Images](https://arxiv.org/abs/2007.00398)

Metrics to mine:

- exact match
- field-level precision / recall / F1
- link or relation F1
- ANLS for DocVQA-style answers
- page / region grounding accuracy
- tree edit distance for hierarchical structure recovery
- OCR robustness and normalized-answer accuracy

## 4. Pairwise Preference And Ranking

Candidate papers:

- [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)

Metrics to mine:

- pairwise win / loss / tie counts
- Bradley-Terry ranking stability
- judge bias by prompt family
- category-wise ranking variance
- rank correlation across repeated runs

## 5. Multi-Label Taxonomy Work

Candidate papers:

- [GoEmotions: A Dataset of Fine-Grained Emotions](https://aclanthology.org/2020.acl-main.372/)

Metrics to mine:

- micro-F1
- macro-F1
- subset accuracy
- Hamming loss
- label cardinality error
- per-label confusion and imbalance diagnostics

## 6. Multi-Stage Verification Or Research Projects

Candidate papers:

- [The Fact Extraction and VERification Over Unstructured and Structured information (FEVEROUS) Shared Task](https://aclanthology.org/2021.fever-1.1/)

Metrics to mine:

- FEVEROUS score
- supported / refuted / not-enough-info accuracy
- evidence recall
- evidence precision
- retrieval-vs-verification split
- multi-hop evidence coverage
- correction / regression rates across stages

## 7. Reusable Diagnostic Additions

Across all future grounded slices, we should try to keep these first-class:

- proposal-vs-review delta
- accept / edit / correct / reject decision rates
- command-audit counters
- artifact truthfulness checks
- repeated-run stability
- difficulty-stratified scores
- field-level and label-level confusion summaries
- coverage and duplicate-submission checks
- report truthfulness against persisted artifacts
