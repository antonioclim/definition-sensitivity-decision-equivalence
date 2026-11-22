# EINT-R3 full-execution, convergence and reproduction audit

## Execution identity

The frozen EINT-R2 protocol was executed without scientific amendment.

```text
protocol schema: 3.0-econ.1
protocol SHA-256: 1d7361861b4eee84dda9313a52ca3a3643873744d933bcdd208dab795ec18e22
unique cells: 270
streams per cell: 4
replications per stream: 1,000
replications per cell: 4,000
total replications: 1,080,000
pooled/deterministic rows: 1,076,760
stream-specific rows: 1,708,560
workers: 4
execution result: PASS
```

The monitored run reached `cell_0270` and closed normally. No cell was removed, rerun selectively or replaced after inspection.

## Structural validation

The output validator passed with zero failures. Every expected cell, metric row, stream row and defined value was present. No undefined results occurred in either pooled or stream summaries.

Pooled summaries were independently reconstructed from the four stream files for 427,140 stochastic metric keys. Maximum absolute discrepancies were 3.975e-14 for means, 3.359e-12 for standard deviations and 0.0 for minima and maxima.

## Stream diagnostics

Across 427,140 stochastic metric keys, the median R-hat was 1.000000, the 99th percentile was 1.001168 and the maximum was 1.004012. No key exceeded 1.01. There was no zero-with-between-stream-drift case. Stream-index standardised mean differences were close to zero and positive fractions were close to one half.

These diagnostics assess the stability of independent Monte Carlo streams. They are not evidence that the synthetic DGP is externally valid and they do not substitute for economic identification.

## Reproduction audit

The prespecified reference cell (`cell_0051`) was rerun independently at the full four-stream by 1,000-replication depth. Its 3,988 pooled/deterministic rows and 6,328 stream rows were byte-identical to the corresponding rows extracted from the 270-cell run.

Before the full run, two cells executed sequentially and with four workers produced exactly equal ordered Python results. The frozen source archive, manifest and checksum ledger all passed before execution.

## Deterministic preview parity

The deterministic pre-execution preview and the deterministic rows extracted from the full run contained the same 115,488 row identities and integer counts. They were not byte-identical because 144 semantic rows differed at machine precision. The maximum absolute difference was 2.220e-16; no value exceeded the declared 1e-12 absolute and relative tolerance. This is recorded as tolerant numerical parity, not falsely described as byte identity.

## Privacy boundary

No output contains country or source-stratum labels, respondent identifiers, microdata, contact information or the author's identity. The forbidden-token scan returned zero hits.

## Verdict

```text
full execution: PASS
structural output validation: PASS
four-stream convergence: PASS
reference-cell byte reproduction: PASS
deterministic tolerant parity: PASS
privacy boundary: PASS
scientific interpretation: restricted to the frozen synthetic design
```
