# EINT-R3 deterministic preview/full-run parity note

The deterministic preview and the unique deterministic rows recovered from the authorised full run contain the same 115,488 identity keys and exact count fields.

A strict byte/value comparison failed for 144 semantic rows because floating-point values differed by at most 2.2204460492503131e-16. No difference exceeded the declared absolute or relative tolerance of 1e-12.

```text
identity key sets: PASS
integer counts: PASS
maximum absolute floating difference: 2.220e-16
values beyond tolerance: 0
verdict: TOLERANT NUMERICAL PARITY PASS
```

The files are deliberately not described as byte-identical.
