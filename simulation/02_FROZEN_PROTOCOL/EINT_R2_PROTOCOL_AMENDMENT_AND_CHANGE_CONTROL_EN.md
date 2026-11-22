# EINT-R2 protocol amendment and change control

## 1. Status

This document records a versioned amendment to the earlier association-centred ODSA simulation. It is not a claim that the earlier protocol was defective. The amendment changes the disciplinary question, estimands, state register and reporting contract because the article is being reconstructed for the economics of innovation and technology adoption.

## 2. Legacy protocol

```text
phase: IM-R3/IM-R4
protocol SHA-256: 157bc88f41ff68261253fb19e79cc2c0aeebe63a4687d1f1073edd25ecc0b8f3
states: active use; project stage; other
groups: small; medium; large
full cells: 432
replications per cell: 4,000
full replicate rows: 1,728,000
primary focus: level, Cramér's V and subgroup-order sensitivity
full results viewed before EINT-R2 design: YES
```

The legacy full run was completed and audited. Its results remain valid for the questions it prespecified. They must not be silently relabelled as evidence for the new economic decision layer.

## 3. New protocol

```text
phase: EINT-R2/EINT-R3
protocol schema: 3.0-econ.1
protocol SHA-256: 1d7361861b4eee84dda9313a52ca3a3643873744d933bcdd208dab795ec18e22
states: five production-planning technology states
analytical units: 8 or 16 synthetic units
unique full cells: 270
replications per cell: 4,000
full replicate rows: 1,080,000
primary focus: decision equivalence, threshold sets, top-k sets, objective-relative loss and partial orders
new decision-layer results viewed before freeze: NO
public Study 2 calibration values viewed before freeze: YES
private source-level results used for calibration: NO
```

## 4. Reason for amendment

The amendment was triggered by a documented disciplinary reconstruction after editorial rejection for insufficient fit with the prior journal. It was not triggered by inspection of new decision-layer outcomes. The new protocol asks a different question:

> When do plausible technology-adoption boundaries produce nonequivalent economic information and nonequivalent actions under a declared objective?

This question requires states and diagnostics that were absent from the legacy three-state association design.

## 5. Scientific changes

| Component | Legacy protocol | EINT-R2 amendment |
|---|---|---|
| State register | active use, project stage, other | manual, standard software, platform, specialised software, integrated system |
| Main estimand | association and level contrast | action-set and objective-relative loss |
| Groups/units | three fixed groups | 8 or 16 synthetic analytical units |
| Ranking output | pairwise disagreement and reversal | pairwise reversal, top-k churn and interval partial order |
| Missingness | complete-case and missingness profiles | unresolved-state weight bounds plus observed complete-case rate |
| Decision objective | implicit managerial relevance | four explicit state objectives |
| Costs | absent | three prespecified false-inclusion/false-exclusion ratios |
| Comparator | absent | four-level ablation |

## 6. Preserved elements

The amendment preserves:

- nested-definition logic;
- explicit observation-process error;
- four independent random-number streams;
- 4,000 replications per full cell;
- worst-case event-probability MCSE below 0.008;
- no hypothesis testing across simulation cells;
- explicit undefined-result reporting;
- separation of population, observed and bounded quantities;
- requirement for a byte-locked protocol before full execution.

## 7. Calibration disclosure

The synthetic reference mixture is calibrated only to the disclosure-cleared Study 2 weighted cross-stratum medians:

- integrated planning: 0.0378009442;
- specialised planning: 0.1066425579;
- digitally enabled planning: 0.7321759478.

These values are not interpreted as global or representative national adoption parameters. No source labels, exact source-level rates, private internal reports or World Bank microdata enter the protocol.

## 8. Post-freeze rule

After protocol SHA-256 lock, the following changes require a numbered amendment and rerun of all affected cells:

- state definitions;
- objective state sets;
- threshold or top-k values;
- cost ratios;
- scenarios or parameter values;
- observation matrices;
- missingness probabilities;
- weighting profiles;
- cell grid;
- primary performance measures;
- tie or interval policy.

Implementation corrections that do not alter scientific quantities may be made before EINT-R3, but each must be documented, tested and shown not to change the protocol hash. Any correction that changes a reported result after full execution requires a result-impact audit.

## 9. EINT-R2 execution boundary

Only validation and four 50-replication smoke cells are authorised in EINT-R2. Smoke output exists solely to test mechanics, schemas and formal invariants. It cannot be cited in the article, abstract, cover letter or supplementary scientific results.

Full execution is rejected by the runner unless the explicit `--authorise-full` flag is supplied. That flag is reserved for the separately authorised EINT-R3 phase.
