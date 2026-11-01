# B2 v4 three-run same-day replication, physical Windows session

**Observed:** three prespecified, distinct-seed attempts completed; all 16
apparatus controls passed in each run. Every run's preselected `F(p0,n1)`
estimate was small and its within-run interval failed to cross the frozen
±1 TSC-tick practical-association threshold. This is descriptive evidence
for same-session stability of a near-zero interaction on one host. It does
not prove the true effect is zero or establish a branch-predictor mechanism.

## Complete archive and integrity

Original outer evidence archive:
`b2-replication-windows-20261101T164301064Z.zip`, containing the frozen
session ledger, three original per-run ZIPs and transcripts, the run-level
summary, and SHA-256 manifest. The outer archive must be retained as supplied;
its SHA-256 is
`805ff9fdb9a02d378e834d1dff0125c58a1c735df5d9c8390a1ecf7196ad5c6d`.
This report is a derived summary. All three seeds were written before the
first run: `3844505995`, `283770299`, and `1271025164`. The recorded source
revision was clean Git HEAD `8352e598331a2897b790958385976e5c421575cf`.

The outer archive passes ZIP CRC and all eight manifest member hashes. All
three inner ZIPs pass CRC and their manifest hashes. Each of their ten source
hashes matches the recorded clean Git revision; the raw traces pass the
frozen B2 analyzer's seed-derived schedule, positions, checksum and
architectural-total checks. The archived JSON is reproduced from the raw
data. Each executable and PE `.text` hash matches its provenance; all three
`.text` hashes are the same
`1289fa0d276ca798fdf80b0319730d97fc19391e85f78d71c64e96f62c3b947e`,
also matching the earlier [v4 outcome run](../2026-11-01-windows-b2-outcome/README.md).
The outer auditor confirms one recorded UTC date and the same CPU signature,
Windows build, affinity and hypervisor bit across all three runs. These are
archive consistency checks, not independent hardware attestation.

## Prespecified primary outcome

The outcome is the paired 10%-trimmed blockwise `F = D_real - D_fixed` for
probe 0 and one probe call, in TSC ticks per **complete probe episode**. Each
95% interval below resamples 40-block position cycles **within that run**.
It is not an interval over three independently started runs.

| Run seed | `F(p0,n1)` | Within-run 95% interval | All 16 controls | Practical association beyond ±1 |
| ---: | ---: | ---: | --- | --- |
| 3844505995 | -0.0479 | [-0.1919,+0.0937] | Pass | No |
| 283770299 | +0.0060 | [-0.1219,+0.1308] | Pass | No |
| 1271025164 | +0.0397 | [-0.0692,+0.1454] | Pass | No |

The three eligible run-level point estimates have descriptive median
`+0.0060` and range `[-0.0479,+0.0397]` ticks per episode. These are three
runs, not 9,600 independent experimental units for a cross-run interval.
No data from the earlier initial v4 run were pooled into this summary. The
three new runs and the initial run all have point estimates near zero under
the same practical rule, but the replication was chosen after viewing the
first result and all four runs occurred on one UTC date.

## Secondary outcomes and boundaries

All four `F` strata remain visible inside each raw archive. The p1/n16
secondary result in the third run is `+0.711 [+0.007,+1.409]`, while the
other two p1/n16 intervals include zero. This comparison was secondary and
not multiplicity-adjusted; it does not replace the frozen primary result.
The other secondary stratum estimates and their intervals are in the
machine-readable summary and original per-run analyses.

The same Windows user process supplies both training and probe. The observed
47-tick timing lattice, hypervisor presence, possible carryover and
cross-pair drift still limit mechanistic interpretation. The matched code
section supports transfer of the [initial linked-instruction
audit](../2026-11-01-windows-b2-outcome/README.md) to these three builds,
subject to the source and hash checks above. No user/kernel or ASID boundary,
cache receiver, misprediction counter or speculative-execution event is
measured. These three same-day runs do not establish day-to-day robustness
or reproduce the paper's Apple M1 findings.

Recompute the run ledger from the original ZIP at this source revision with
`python scripts/summarize_b2_outcome_replicates.py
<outer-evidence-zip> --json`. Keep failed-control and failed-build attempts
in any later sessions; do not select a seed based on its result.
