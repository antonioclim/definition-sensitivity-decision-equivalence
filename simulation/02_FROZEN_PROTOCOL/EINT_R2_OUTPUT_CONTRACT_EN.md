# EINT-R2 output contract

## 1. Output levels

The runner produces two scientific summary levels and one mechanics object.

### `CELL_METRIC_SUMMARY.csv`

Contains:

- deterministic population metrics calculated once per cell;
- pooled stochastic observed metrics across all streams;
- Monte Carlo standard error for stochastic metrics;
- undefined counts;
- minimum and maximum replicate values.

### `STREAM_METRIC_SUMMARY.csv`

Contains stream-specific stochastic summaries for convergence auditing. Deterministic population rows are not repeated by stream.

### `REPLICATE_MECHANICS.json`

Produced only in smoke mode. It contains sample-size, unresolved-count and probability-range checks, not scientific replicate-level outcome data.

## 2. Common columns

| Column | Meaning |
|---|---|
| `cell_id` | stable identifier from the deduplicated frozen grid |
| `stream_id` | `deterministic`, `pooled` or stream identifier |
| `metric_scope` | `deterministic_population` or `stochastic_observed` |
| `metric_family` | level, contrast, semantic, action loss, partial order, ablation or QA family |
| `metric_name` | exact scalar diagnostic |
| `definition` | definition or contrast identifier |
| `objective` | declared objective or `NA` |
| `rule` | threshold, top-k or other rule identifier |
| `parameter` | threshold, k, materiality value or compound frozen parameter |
| `cost_profile` | cost profile or `NA` |
| `n_defined` | number of finite values entering the summary |
| `n_undefined` | number of undefined values |
| `mean` | deterministic value or Monte Carlo mean |
| `sd` | zero for deterministic metrics; replicate SD for stochastic metrics |
| `mcse` | zero for deterministic metrics; simulation MCSE for stochastic metrics |
| `minimum`, `maximum` | replicate range or deterministic value |

Grid-factor columns precede these common columns.

## 3. Metric families

### `level`

Population mean, range, observed mean and observed mean absolute error.

### `contrast`

Mean level delta, pairwise disagreement and strict reversal for each nested contrast.

### `cross_definition_action`

Threshold-set symmetric difference, top-k churn and Jaccard overlap between definitions.

### `semantic`

State-objective false-inclusion mass, false-exclusion mass and cost-weighted semantic loss.

### `action_loss`

Population or observed action disagreement relative to the objective-aligned benchmark. False-inclusion, false-exclusion, symmetric difference and Jaccard values are recorded once because they do not depend on cost. Cost-weighted loss is recorded separately for each cost profile.

### `partial_order`

Determinate pair share, threshold ambiguity, guaranteed top-k share and possible-set excess.

### `tie_audit`

Boundary-tie event frequencies for point top-k selection.

### `ablation`

Prespecified events distinguishing the four comparator layers.

## 4. Result eligibility

```text
deterministic_population from frozen full grid: manuscript-eligible after EINT-R3 audit
stochastic_observed from authorised 4,000-replication full run: manuscript-eligible after EINT-R3 audit
smoke output: never manuscript-eligible
private source-level empirical diagnostics: excluded from this output contract
```

## 5. Prohibited fields

No output may contain:

- country or source-stratum label;
- respondent or establishment identifier;
- telephone or contact information;
- World Bank microdata;
- human-participant data;
- private internal report payloads.
