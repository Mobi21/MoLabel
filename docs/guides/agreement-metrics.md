# Agreement metrics

`AgreementMetricsService.analyze` in
`packages/molabel-core/src/molabel/core/quality/agreement_metrics.py` computes
these metrics. The `agreement_analysis` workflow step calls it. This page gives
the formula behind each field of `AgreementMetricSummary`, and the cases where a
field is null.

## Units and values

A unit is one field of one record. Its values are the labels that the
annotations in scope gave that field, after `canonical_label_value` turns them
into strings. Values are compared as nominal categories, so two values agree
only when the strings are equal.

- An annotation that lacks the field is a missing value for that unit.
- An explicit null label is a missing value too, the way Krippendorff (2011)
  treats a unit that a coder left blank. It never pairs with another value. A
  "none" answer that should count as agreement must be an option in the task
  schema, such as `none`.
- A unit with fewer than two values cannot be paired. The service leaves it out
  of every metric.

`analysis_type` decides which annotations are in scope for `overall` and
`fields`.

| `analysis_type` | Sources in `overall` and `fields` | `human_agent` summaries |
| --- | --- | --- |
| `both` (default) | every source | computed |
| `inter_annotator` | `human`, `import` | not computed |
| `human_agent` | the `human_agent` summaries | computed |

## Per field and pooled

The analysis covers the label fields passed to `analyze(fields=...)`, which is
the `fields` config of an `agreement_analysis` step, or every label key it
finds. It computes every metric once per label field and once pooled.

- `fields` in the result maps each label field to its own
  `AgreementMetricSummary`. `human_agent_fields` does the same for the
  human-agent pairs.
- `overall` and `human_agent` pool the units of every label field into one
  variable.

The formulas below run on one field's units for a per-field summary, and on
every field's units for a pooled one. Read a field's own summary for that
field's reliability. The pooled summary is not an average of the fields. A
label that two fields share counts as one category. If the fields use different
label sets, labels that can never meet in one unit still lower the agreement
expected by chance, and that raises the pooled coefficients.

## Notation

For each pairable unit `u`:

- `m_u` is the number of values in `u`.
- `n_uc` is the number of values in `u` that equal label `c`.

Over all pairable units, `n_c = sum_u n_uc` and `n = sum_c n_c`. `N` is the
number of pairable units.

## Summary fields

| Field | Formula | Null when |
| --- | --- | --- |
| `comparisons` | `sum_u m_u (m_u - 1) / 2`, the value pairs within units | never, 0 with no pairable unit |
| `agreements` | `sum_u sum_c n_uc (n_uc - 1) / 2`, the matching pairs | never, 0 with no pairable unit |
| `percent_agreement` | `agreements / comparisons` | no pairable unit |
| `krippendorff_alpha` | Krippendorff's alpha, nominal metric. See [Krippendorff's alpha](#krippendorffs-alpha). | no pairable unit, or one label in all values |
| `fleiss_kappa` | Fleiss' kappa. See [Fleiss' kappa](#fleiss-kappa). | no pairable unit, units hold different numbers of values, or one label |
| `cohen_kappa` | Cohen's kappa for two raters. See [Cohen's kappa](#cohens-kappa). | no pairable unit, not exactly two raters, a unit holds two values from one rater, or one label |
| `null_reasons` | Maps each null field above to the reason it is null. | never |

`percent_agreement` counts pairs, so a unit with four values weighs six pairs
and a unit with two values weighs one.

### Krippendorff's alpha

The coincidence matrix counts every ordered pair of values within a unit and
divides by `m_u - 1`, so each pairable value adds 1 to the matrix:

```text
o_ck = sum_u (number of c-k pairs in u) / (m_u - 1)

krippendorff_alpha = 1 - D_o / D_e
D_o = (1 / n) * sum over c != k of o_ck
D_e = (1 / (n (n - 1))) * sum over c != k of n_c n_k
```

This is the general form on page 1 of Krippendorff (2011) with the nominal
difference function. Section C of that paper works it for any number of raters
and missing values. `D_e` divides by `n (n - 1)`, not `n^2`, because a value
cannot pair with itself. With one label in all values, `D_e` is 0 and alpha is
null.

### Fleiss' kappa

Every unit must hold the same number of values `m`. The raters of one unit need
not be the raters of another (Fleiss 1971).

```text
P_u  = (sum_c n_uc^2 - m) / (m (m - 1))
P    = (1 / N) * sum_u P_u
p_c  = n_c / (N m)
P_e  = sum_c p_c^2
fleiss_kappa = (P - P_e) / (1 - P_e)
```

If units hold different numbers of values, `fleiss_kappa` is null and the
reason points to `krippendorff_alpha`, which handles that case.

### Cohen's kappa

Cohen's kappa compares exactly two raters, each with its own marginals
(Cohen 1960). An annotation's rater is its `rater_id`. An annotation without a
`rater_id` falls back to its `source` as the rater. `cohen_kappa` is defined
only when every pairable unit holds one value from each of the same two raters.
Then each unit is a pair `(a, b)`:

```text
p_o = (number of units where a == b) / N
p_e = sum_c (share of units where a == c) * (share of units where b == c)
cohen_kappa = (p_o - p_e) / (1 - p_e)
```

These cases make `cohen_kappa` null.

- Annotations from three or more raters. Use `fleiss_kappa` or
  `krippendorff_alpha`.
- Two annotations with the same rater in one unit. Two people who both label
  as `human` with no `rater_id` cannot be told apart. Give each annotation the
  reviewer's id as `rater_id` to get a human-human `cohen_kappa`.
- Both raters use the same single label, so `p_e` is 1.

## The human-agent summary

`human_agent` pairs each human value in a unit with each agent value. A human
value comes from source `human` or `import`, and an agent value from source
`agent`. Each pair is a unit with two values from two raters, `human` and
`agent`. A record with two human values and one agent value gives two pairs.
Human-human pairs never count.

All of the formulas above then apply to those pairs.

- `cohen_kappa` is Cohen's kappa of the `confusion_matrix`, with human values as
  rows and agent values as columns.
- `fleiss_kappa` on two-value units equals Scott's pi.
- `krippendorff_alpha` is the two-rater alpha over the same pairs.

## Records from review events

In a running workflow, `agreement_analysis` reads its records from the
workflow's review events and agent outputs, unless the step's
`agreement_records` config or the `agreement.records` context variable passes
records in. `molabel.core.quality.review_agreement` builds them.

- The records are the workflow's active record set.
- Each reviewer is one rater. The annotation's source is `human` and its
  `rater_id` is the reviewer's id.
- Each agent run of the workflow is one rater. The annotation's source is
  `agent`, its `rater_id` is the agent run's id, and its labels are the run's
  output for the record. `inter_annotator` leaves these out, and the human-agent
  summary pairs them with the reviewers' values.
- Only events on tasks in the workflow's review queues count.

The human-agent summary pairs every reviewer's value for a record with every
run's output for it, including runs the reviewer never saw. The reviewer's
value is the labels they submitted, so it is the reference for each run. A
blind reviewer saw no run, and their value still measures every run.

A reviewer can leave several events on one record. One of them counts.

- A correction supersedes the event before it, so the head of the correction
  chain counts: the event no other event supersedes.
- A reviewer can have two chain heads for one record, from two tasks in
  different queues, such as a loop pass that reviews the record again. The
  latest head counts.

The counted event's labels are the reviewer's value. Submit and correct store
them when the reviewer acts, and agreement reads them as stored. The event's
decision, after `canonical_review_decision` maps a legacy name such as
`accept_ai` or `correct`, says whether they count.

| Decision | Value |
| --- | --- |
| `accept` | The labels the reviewer sent. An accept with no labels stores the labels of the proposal the reviewer was shown. With no proposal shown, it stores none and gives no value. |
| `edit` | The labels the reviewer sent. |
| no decision | The labels the reviewer sent. |
| `reject` | No value. Rejecting a proposal does not say which label is right. |
| `skip` | No value. |

An event that stores no labels gives no value, whatever its decision.

Each claim and reveal records the agent output it returns, or none, as the
task's `shown_agent_output_id`. Under `hide_agent_outputs_by_default` a claim
shows no output until the reviewer reveals one, and under `no_agent` no output
is ever shown. The output shown is the newest one for the record and task
schema, so it can come from a later run than the one the queue was built from.
Submit and correct copy the id to the event's `agent_output_id`, and agreement
never looks the proposal up again.

Two reviewers see the same record only when the queue holds two tasks for it.
A `human_review` step with `overlap_count: 2` creates two tasks per record, and
the queue never hands one reviewer both. The step resumes once every task is
submitted, so each record then has two reviewers.

A step with `overlap_count: N` needs N distinct reviewers. With fewer, each
reviewer submits one copy of every record, the queue then looks empty to all of
them, and the remaining copies stay `available`. The step cannot resume, and
advancing it returns 409 with a message such as "3 copies need 3 distinct
reviewers; 2 have submitted". A new reviewer can claim the remaining copies.

## Measuring a queue

`GET /api/v1/quality/agreement?workspace_id=...&queue_id=...`, the CLI's
`molabel quality agreement --queue-id <id>`, and the GUI's calibration screen
measure a queue outside any workflow, from the same review events. They run
`analyze` twice: `inter_annotator` for the reviewers against each other and
`human_agent` for each reviewer value paired with each proposal the queue's
tasks are bound to. Each scope lists its `skipped_fields`, the fields whose
Krippendorff's alpha is null, with the reason.

## Workflow outputs

The `agreement_analysis` step's summary holds `pooled`, `fields`, `human_agent`
and `human_agent_fields`. `pooled` is the result's `overall`. The earlier keys
stay for compatibility and carry the pooled values. `overall` repeats `pooled`,
and `kappa`, `percent_agreement`, `fleiss_kappa`, `krippendorff_alpha` and
`human_agent_agreement` repeat single pooled metrics.
[The API specification](../architecture/api-specification.md#get-qualityagreement)
lists every key.

The step also writes the pooled `agreement.kappa` (`cohen_kappa`),
`agreement.percent_agreement`, `agreement.fleiss_kappa`,
`agreement.krippendorff_alpha` and `agreement.human_agent_agreement` to
`context.metrics`, and the per-field summaries to
`context.variables["agreement.fields"]`.

A null metric is removed from `context.metrics`, which also clears a value from
an earlier loop pass. Readiness gates and conditional predicates read a missing
metric as 0.0. A loop with a `metric` termination keeps running while its metric
is missing. The step summary keeps every key, with null for an undefined metric.
The step also writes the number of records it analyzed to its summary's
`record_count` and to `context.variables["agreement.record_count"]`.

## The quality_check gate

`quality_check` compares `config.min_agreement` with Krippendorff's alpha of
each field in `context.variables["agreement.fields"]`. The check fails when any
measured field's alpha is below the threshold, whatever the pooled alpha is.

Alpha is defined for any number of raters and handles missing values, so the
gate works for three or more reviewers. Earlier versions compared
`min_agreement` with `agreement.kappa`. That is Cohen's kappa, which is null
with three or more raters, so those workflows always failed the gate.

### Thresholds

`min_agreement` now means Krippendorff's alpha, not Cohen's kappa. Configs keep
the `min_agreement` key, and its threshold now applies to alpha. A threshold
chosen for kappa is worth checking against the alpha standard below.

Krippendorff (2004, p. 241) asks for alpha of at least .800 to rely on a
variable. A variable between .667 and .800 supports only tentative
conclusions, and one below .667 should not be relied on. Every bundled template
sets `min_agreement: 0.80` and cites this standard. MoLabel does not rewrite
existing workflow files, so a workflow created from an earlier template keeps
the threshold it was created with.

### Null fields

A field's alpha is null when the data cannot show agreement on it, for one of
two reasons:

- No unit has two values for the field, as when only one rater set it.
- Every value is the same label, so chance alone predicts full agreement.

The gate skips such a field. The field goes into the check's `skipped_fields`
with its null reason and does not fail the gate. Its summary stays in the
`agreement_analysis` output, so a field where every rater chose one label still
shows its comparisons and a `percent_agreement` of 1.0.

List a field in the `quality_check` step's `fields` config to require it. A
listed field fails the gate when its alpha is null, when `agreement_analysis`
did not report it, or when its alpha is below the threshold.

```yaml
- id: quality
  type: quality_check
  config:
    # Reliable alpha per Krippendorff (2004, p. 241).
    min_agreement: 0.80
    fields: [sentiment, topic]
```

To leave a field out of both the analysis and the gate, list the fields to
analyze in the `agreement_analysis` step's `fields` config.

### Nothing measured

When nothing was measured, the check fails with a `code` and a `reason`, and
the step result's `warnings` repeat both. It never reads a missing agreement as
0.0.

| `code` | When |
| --- | --- |
| `NO_AGREEMENT_RECORDS` | No `agreement_analysis` step ran, or it found no records. |
| `NO_MEASURED_FIELDS` | Every field was skipped. |

### The check entry

The check's entry in the step's `details` lists every field's alpha, the fields
that failed, and the fields it skipped:

```json
{
  "check": "min_agreement",
  "metric": "krippendorff_alpha",
  "threshold": 0.8,
  "actual": 0.125,
  "passed": false,
  "fields": {"sentiment": 1.0, "topic": 0.125, "flag": null},
  "failing_fields": {"topic": 0.125},
  "skipped_fields": {
    "flag": "Every compared value is the same label, so chance alone predicts full agreement and the coefficient is 0/0."
  },
  "code": null,
  "reason": null
}
```

Only the fields decide. The gate fails on `topic` here whatever the pooled alpha
is.

`actual` and `metrics["quality.agreement"]` hold the lowest alpha of the fields
the gate did not skip. When a required field is null, or nothing was measured,
`actual` is null and `quality_check` removes `quality.agreement`. So
`quality.agreement` reaches the threshold exactly when the gate passes. A loop
that terminates on `quality.agreement` at the gate's threshold stops when the
gate would pass, and keeps running while the gate cannot measure.

## Level of measurement

All three coefficients use the nominal difference: two values either match or
they do not. Task schema fields of type `ordinal` and `numeric` call for
Krippendorff's ordinal and interval difference functions, and `multi_select`
calls for a set distance. The service does not receive the task schema, so it
does not apply them.

## Reference tests

`tests/unit/test_agreement_reference_values.py` checks the service against
these published examples, each to the precision the source prints.

| Source | Data | Field | Published value |
| --- | --- | --- | --- |
| Krippendorff (2011), section A, pp. 2-3 | 2 observers, 10 binary units | `krippendorff_alpha` | 0.095 |
| Krippendorff (2011), section B, pp. 3-4 | 2 observers, 12 nominal units | `krippendorff_alpha` | 0.692 |
| Krippendorff (2011), section C, pp. 4-5 | 4 observers, 12 units, 7 missing values | `krippendorff_alpha` | 0.743 |
| Fleiss (1971), Table 1 | 30 patients, 6 diagnoses each | `fleiss_kappa` | 0.430 |
| Viera and Garrett (2005), Table 1, p. 361 | 2 residents, 100 lectures | `cohen_kappa` | 0.57 |

The Fleiss (1971) rows are the R `irr` package's `diagnoses` dataset. Neither
those rows nor the 0.430 have been checked against a copy of the paper.

## References

- Cohen, J. (1960). A coefficient of agreement for nominal scales.
  *Educational and Psychological Measurement*, 20(1), 37-46.
- Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters.
  *Psychological Bulletin*, 76(5), 378-382.
- Krippendorff, K. (2004). *Content Analysis: An Introduction to Its
  Methodology* (2nd ed.). Sage. The reliability chapter, p. 241, sets the
  .800 and .667 standards.
- Krippendorff, K. (2011). Computing Krippendorff's alpha-reliability.
  Departmental Papers (ASC) 43, University of Pennsylvania. Version 2011.1.25,
  literature updated 2013.9.13.
- Viera, A. J., and Garrett, J. M. (2005). Understanding interobserver
  agreement: the kappa statistic. *Family Medicine*, 37(5), 360-363.
