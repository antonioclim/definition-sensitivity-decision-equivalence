# ADEMP and executable protocol for the economic ODSA decision layer

## A — Aims

The simulation has four aims:

1. identify when substantively defensible adoption boundaries are numerically different but decision-equivalent;
2. identify when boundary changes alter threshold sets, top-k sets or robust partial orders;
3. separate structural definition sensitivity from sampling, weighting, unresolved-state and misclassification effects;
4. establish what the full decision layer reveals beyond single-definition reporting, generic multi-definition robustness and semantic ODSA alone.

## D — Data-generating mechanisms

### State mixture

Each synthetic unit has a five-state probability vector. The reference mixture exactly reproduces the public Study 2 weighted medians for the three registered definitions. Between-unit variation is introduced without clipping or silent renormalisation.

### Scenarios

Six scenarios are frozen:

- `null_common`;
- `aligned_diffusion`;
- `broad_margin_only`;
- `middle_compensation`;
- `strict_to_broad_reversal`;
- `mixed_nonmonotone`.

The scenarios distinguish common movement, broad-margin heterogeneity, compensation within a nested boundary, exact population reversal and non-linear order changes.

### Design modules

The full design contains 270 unique cells after exact deduplication:

- core module: 192 memberships;
- sample-size module: 30 memberships;
- weighting module: 18 memberships;
- observation module: 54 memberships.

Some cells belong to more than one module. The grid registry records all memberships and assigns one stable cell identifier to each unique parameter combination.

### Sampling and allocation

The design uses 8 or 16 units. The core module uses base sample sizes of 100 and 500. The sample-size module adds 50, 250 and 1,000. Allocation is balanced or follows a prespecified linear gradient from 0.5 to 1.5 times the base size, normalised to mean one.

### Weights

Record weights are independent gamma variables with mean one. The coefficient of variation is 0, 0.5 or 1.0. Gamma additivity permits exact simulation of state-level weight sums without constructing or retaining record-level data.

### State misclassification

Three profiles are frozen:

- no misclassification;
- 10% swapping within the broad positive class;
- 10% swapping across broad or middle boundaries.

The matrices are row-stochastic and nondifferential with respect to analytical unit.

### Unresolved states

Three profiles are frozen:

- no unresolved state;
- 5% state-independent unresolved probability;
- state-dependent probabilities from 3% to 15%.

The simulation retains unresolved weight. Lower and upper rates assign all unresolved weight outside or inside the positive class. These are deterministic assignment bounds.

## E — Estimands

### Definition-specific population rates

For each unit and definition, estimate the generating rate and observed weighted complete-case rate.

### Structural state mismatch

For every definition-objective pair, calculate state-level false-inclusion mass, false-exclusion mass and cost-weighted semantic loss.

### Action sets

For every objective, definition and rule, calculate:

- the objective-aligned population benchmark;
- the definition-induced population action set;
- the observed action set.

Population action loss isolates the structural definition mechanism. Observed action loss incorporates sampling and the observation process. No additive decomposition between them is assumed.

### Order and interval estimands

Calculate pairwise strict reversal, interval-order determinacy, threshold ambiguity and guaranteed or possible top-k membership.

## M — Methods

The protocol applies:

- exact nested-definition identities;
- fixed threshold and top-k rules;
- lexicographic point tie-breaking with tie flags;
- set-valued interval membership;
- objective-relative state and action loss;
- four-level comparator ablation;
- four SeedSequence-derived streams in the full execution.

No significance test is used to rank simulation cells. The design reports effect magnitudes, event frequencies, undefined-result frequencies and Monte Carlo uncertainty.

## P — Performance measures

Primary performance measures are:

- threshold symmetric difference;
- top-k churn;
- Jaccard overlap;
- state-level false inclusion and false exclusion;
- population action loss;
- observed action loss;
- pairwise strict reversal;
- partial-order determinacy;
- threshold ambiguity;
- guaranteed and possible top-k membership;
- comparator-ablation event frequencies.

Secondary measures are observed mean absolute rate error, unresolved share and boundary-tie frequency.

## Monte Carlo precision

Each full cell uses four independent streams of 1,000 replications, giving 4,000 replications. At an event probability of 0.5, the worst-case Monte Carlo standard error is approximately 0.007906 and the approximate 95% half-width is 0.01550.

Continuous metrics report the sample standard deviation across replications divided by the square root of the number defined. Cells with more than 5% undefined values for a primary metric cannot support a comparative claim for that metric.

## Deterministic versus stochastic outputs

Population state, semantic and structural action diagnostics are computed once per cell because they do not vary across Monte Carlo replications. Sampling and observation diagnostics are pooled across replications. This factorisation avoids repeating deterministic calculations and reduces full-run cost without changing an estimand.

## Full-run authorisation

The authorised EINT-R3 command will be:

```bash
python run_protocol.py \
  --protocol ../02_FROZEN_PROTOCOL/eint_r2_decision_protocol.yml \
  --freeze ../02_FROZEN_PROTOCOL/eint_r2_decision_protocol.freeze.json \
  --output-dir <EINT_R3_OUTPUT_DIRECTORY> \
  --mode full \
  --authorise-full \
  --workers <VALIDATED_WORKER_COUNT>
```

Before execution, the runner verifies the frozen SHA-256. Without `--authorise-full`, full execution terminates before the first cell.


## Parallel execution implementation

The full runner can parallelise independent cells. Cell seeds are derived from the frozen cell key and do not depend on worker count. Results are written in frozen cell order through an incremental CSV sink, preventing multi-gigabyte in-memory accumulation and preserving stable output order. Parallel execution changes runtime only, not the scientific design.
