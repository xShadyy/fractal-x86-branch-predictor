# K5 Windows replication: three fixed attempts across three boots

The defined K5 numerical signature repeated in all three prospective attempts
on the reported AMD Ryzen 7 9800X3D Windows workstation on 5 November 2026.
Every run passes all 88 apparatus gates. The raw traces, runtime snapshots,
source and executable hashes validate, and replay of the frozen analysis
reproduces the saved results exactly. There are no recorded protocol deviations.

This result establishes repeatability of the specified user-mode cache response
on this host/configuration. Its precise predictor and transient-execution
mechanism remain unresolved. The exploratory pilot is excluded from the
three-attempt result.

## Frozen plan and scope

- Study: `k5_windows_three_boot_replication_v1`.
- Plan ID: `b79e0257-13a1-421c-b30f-ec33f3fb7cdf`.
- Source revision: `09d6a7f4da1ceda061cfb07cdca344f282dbcedc`.
- Plan SHA256: `8c381e36c4cc12df599bcd56aa55dca6247d873774f234d8312c5721d838a0aa`.
- The original plan, including all three seeds, is byte-identical to the
  uploaded 4 November progress snapshot, before these three measurements.
- Exactly one attempt was recorded on each of three distinct Windows boots.
  There are no replacement attempts or omitted measurement failures.
- Each run records 393,216 episodes: 512 blocks, 16 interleaved rounds,
  16 conditions and three modes. The first 256 blocks calibrate thresholds;
  the final 256 blocks provide held-out estimates.
- Totals: 1,179,648 recorded episodes, including 589,824 held-out episodes.
  The original fixed 16-block warmup per run is not in the recorded sample set.
- CPU signature `0x00b40f40`; Windows build `26200.9168`; BIOS `FA9`;
  raw microcode registry bytes `3540400b`.
- CPUID and Windows inventory report a hypervisor present. VBS inventory
  reports status 2; this does not by itself identify the state of every
  individual security feature. The result is scoped to this configuration.
- Training and probing remain at CPL 3. Boot, host, compiler and source
  records are local provenance, not independent hardware attestation.

The [original K5 protocol](../../protocols/DEPENDENCY_RECEIVER_K5.md) defines the
measurement and gates. The [replication protocol](../../protocols/DEPENDENCY_RECEIVER_K5_REPLICATION.md)
and [policy](../../protocols/K5_REPLICATION_POLICY.json) define the prospective
attempt count, seeds, boot/configuration rules and final classifications.
The original collector, thresholds and numerical decision rules were unchanged.

## Primary result

For each mode `m`, the adjusted training contrast is:

`A_m = (candidate_mismatch - candidate_match) - (no_probe_mismatch - no_probe_match)`.

The primary endpoint is p0 `A_plain - A_mask`. The p1 bank is secondary.
All effects and intervals below are in percentage points.

| Attempt | Preselected seed | p0 primary effect | 95% within-run interval | Gates |
|---|---:|---:|---:|---:|
| 1 | 1059577839 | +99.707031 | [+99.511719, +99.877930] | 88/88 |
| 2 | 3249956994 | +99.609375 | [+99.438477, +99.780273] | 88/88 |
| 3 | 1849279219 | +99.829102 | [+99.707031, +99.926758] | 88/88 |

| Attempt | p0 plain adjusted | p0 mask adjusted | p0 CPUID adjusted | Secondary p1 interaction |
|---|---:|---:|---:|---:|
| 1 | +99.731445 | +0.024414 | +0.024414 | +99.755859 |
| 2 | +99.609375 | +0.000000 | -0.024414 | +99.829102 |
| 3 | +99.829102 | +0.000000 | +0.000000 | +99.780273 |

Every run satisfies the frozen p0 numerical-signature criteria, including the
dependency and CPUID equivalence requirements. The aggregate classification is
`replicated_k5_numerical_signature_this_host_configuration`.

The descriptive mean primary effect is +99.715169 percentage points; the
observed run range is [+99.609375,+99.829102]. The intervals use the original
within-run 16-block-cycle bootstrap, without pooling episodes across hosts or
boots. The effect is an adjusted cache-hit-rate contrast.
Complete unrounded effects, intervals and secondary outcomes are in
[summary.json](summary.json) and [analysis-replayed.json](analysis-replayed.json).

## Original evidence and validation

The [final evidence ZIP](k5-replication-evidence-20261105T141751734Z-5dc97b6d.zip)
contains the plan/source snapshot, all three attempts, their console logs,
before/after host records and complete inner evidence ZIPs. Each inner ZIP
contains the raw trace, executed binary, runtime mode snapshots, linked
disassembly, build provenance, source snapshot, manifest and saved analysis.
The final outer archive's 43 hashed files and all 16 frozen sources validate.

The [prior-day progress ZIP](k5-replication-evidence-20261104T175337116Z-3241a92d.zip)
contains the same plan and zero started measurement attempts. Its purpose is
to preserve the plan as supplied before collection. The two intermediate
5 November cumulative uploads contain one and two attempts respectively;
their hashes and unchanged-prefix checks are retained in
[outer-integrity.json](outer-integrity.json). They are not duplicated here,
because the final ZIP contains their original attempt records unchanged.

The old Python-alias setup error is retained from 4 November. It happened
before plan creation and consumed no measurement attempt.

The [audit ZIP](k5-replication-audit-20261105.zip) is the previously generated
validation record. [Independent raw counts and PE checks](independent-counts-and-pe.json)
reproduce, for each run, both calibrated thresholds, all 48 held-out hit rates,
all 48 decoy rates, all 88 gate decisions and all eight p0/p1 adjusted and
interaction point estimates. Frozen-analysis replay separately checks the
sample schedule, architectural returns, CPL/PC records, end checksums and
event hashes, source/binary/runtime provenance, timestamps and intervals.

The independent check also matches all 31,365 recorded disassembly instruction
rows and all 107,520 `.text` bytes per executable to the corresponding PE file.
All three `.text` sections are identical to the previously reviewed pilot,
SHA256 `62e686e78ce63a547cd665796a63a2584a9458d04ea45fdf3338c9ff8e090468`.
The prior targeted linked-code review is retained inside the audit ZIP.

Original input hashes are in [INPUTS-SHA256.json](INPUTS-SHA256.json). The
result-directory inventory is in [FILES-SHA256.json](FILES-SHA256.json).
The evidence ZIPs were copied byte for byte; no measurement was rerun during
this review or publication preparation, and no uploaded executable was executed.

## Rechecking without collecting measurements

To reproduce the independent cell-count and disassembly-byte checks, run from
this result directory with Python 3:

```text
python audit_raw_counts.py k5-replication-evidence-20261105T141751734Z-5dc97b6d.zip --output independent-recheck.json
```

The [executed independent script](audit_raw_counts.py) reads archives and PE
bytes only. The optional `--pilot-exe` argument additionally checks equality
with an original pilot executable; the recorded independent report used that
argument. Without it, the local raw-count and PE/disassembly checks still run.
Use a new output path to preserve the recorded report.

For exact frozen-analysis replay, use a separate checkout of source revision
`09d6a7f4da1ceda061cfb07cdca344f282dbcedc`, extract a copy of the final outer
ZIP into a fresh review folder, then run that revision's
`scripts/k5_replication.py package` action with `--repo`, `--folder` and a new
`--archive` path. This replays existing evidence and creates a review archive;
it does not collect. Later research code should not replace the frozen sources
or be used to silently reinterpret the original result.

Joseph Ravichandran and Mengjia Yan's
[Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
provides the methodological context for this independent x86 study.
