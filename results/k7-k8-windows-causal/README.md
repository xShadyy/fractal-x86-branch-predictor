# K7/K8 Windows results and independent audit

Measurements collected 8 November 2026; publication review 9 November 2026.
All six planned process attempts meet their frozen criteria. Raw-trace replay,
independent counts and review of the emitted MSVC code agree with the saved
results. The Windows collection is complete.

[Reproduction and file guide](REPRODUCE.md) · [Machine-readable summary](SUMMARY.json)

## Supported result

On the reported Ryzen 7 9800X3D / Windows configuration, the defined cold-
condition training-sensitive public-cache response repeats across three fresh
processes per study. It is sensitive to resolved-condition masking, while the
matched independent-register sham preserves that primary response within the
predeclared equivalence margin. Removing the queried bank's encoder load or
binding the encoder to private banks suppresses the public response. Removing
only the opposite bank's load leaves a large queried-bank response.

The comparisons strengthen attribution to the tested marker-encoding path.
The mode is installed before training and remains active during probing, so
the measured contrast combines its effects on both phases.

## Prospective record and validation

- Source revision: `8080faed480a9eef086f1fc0396e38dba7de31c7`.
- Plan ID: `393a8d31-fca4-408b-806d-db3021a10a8f`.
- Plan SHA-256: `c99ea01daf6a5d16dc17572ec191e8b730a15d2254c84c64147cc45580197ca2`.
- The supplied plan-only ZIP has no attempts and an empty attempt ledger. Its
  plan, source archive and build artifacts are byte-identical to the final
  evidence. Its local timestamps precede collection. It was supplied alongside
  the final ZIP, so it is not an externally timestamped preregistration.
- Exactly six planned slots are recorded: three fresh processes per study on
  one boot, each with a distinct preselected seed. There are no recorded
  replacements, failed attempts or source/configuration deviations.
- The randomized study-order draw placed receiver before dependency in every
  pair. This is not counterbalanced order; cross-study time/order comparisons
  remain confounded. The primary interventions are compared within each run.
- Each attempt contains 163,840 episodes. Total: **983,040 recorded episodes**,
  including **491,520 held-out episodes**. Each held-out mode/cell has 1,024
  observations; episodes are not independent process/host replications.
- Every attempt passes **140/140 held-out apparatus gates**, 840 decisions in
  total, with classification `valid_response`.
- Both ZIP CRCs and exact manifests validate: 84 hashed final members and 12
  hashed plan-only members. All 14 source files match the trusted Git revision,
  and all 12 started/finished ledger records and chronological sequences match.
- The frozen analyzer reproduces all six saved analysis objects exactly.
  A separate histogram/count implementation matches 12 calibration thresholds,
  480 wanted rates, 480 decoy rates, all 840 gates, 60 adjusted outcomes and all
  18 primary point estimates. Primary patterns remain strong in both reload
  orders and all four within-block episode positions.
- All 31,674 recorded disassembly rows match PE bytes, covering all 109,264
  virtual `.text` bytes. The 304 omitted raw-file alignment bytes are zero.
  All 30 runtime snapshots match the trusted mode bytes and trace hex.
- Targeted emitted-code review verifies the fresh-tag stores after training,
  all 256 public/private bank flushes, final MFENCE/serialization, shared probe
  call, ABI register preservation, runtime bindings and expected CPL/PC/AUX
  metadata. No material static implementation defect was found. No uploaded
  executable, object file or runtime machine code was executed by this audit.

The audit establishes file and code consistency. Hardware attestation and an
independently reproduced compiler build were outside its scope.

## Prespecified primary results

Entries are percentage-point effects followed by the frozen adjusted within-run
interval. Each endpoint has approximately 99.1667% nominal coverage under the
six-contrast Bonferroni rule. Coverage concerns one scheduled repetition pair,
not all 18 intervals simultaneously. The paired 16-block percentile bootstrap
is approximate and does not provide across-process/boot/host confidence.

| Primary contrast | Repetition 1 | Repetition 2 | Repetition 3 |
|---|---:|---:|---:|
| K7 p0: sham minus true mask | +99.902 [+99.609, +100.000] | +99.707 [+98.535, +100.000] | +99.414 [+98.535, +100.000] |
| K7 p0: plain minus sham | -0.098 [-0.391, +0.000] | +0.098 [-0.488, +1.270] | +0.098 [-0.684, +1.172] |
| K8 p0: plain minus bank1 ablation | +99.805 [+99.414, +100.000] | +99.707 [+99.316, +100.000] | +99.805 [+99.414, +100.000] |
| K8 p1: plain minus bank0 ablation | +99.609 [+99.023, +100.195] | +100.098 [+100.000, +100.391] | +99.707 [+99.316, +100.000] |
| K8 p0: plain minus private banks | +99.805 [+99.414, +100.000] | +99.707 [+99.316, +100.000] | +99.805 [+99.414, +100.000] |
| K8 p1: plain minus private banks | +99.414 [+98.926, +99.902] | +100.098 [+100.000, +100.391] | +99.805 [+99.414, +100.000] |

The p0 plain-minus-sham intervals all lie within the prespecified +/-10 pp
margin. Every suppression contrast clears +10 pp. Supporting p1 dependency
results have the same broad pattern. True-mask, LFENCE and CPUID adjusted
responses are zero in all six dependency bank/run combinations. Zero empirical
bootstrap intervals do not prove an exactly zero population effect.

In receiver attempt 3, p1's adjusted plain contrast is
`(1024 - 0 - 0 + 1) / 1024`, or 100.09765625 pp. Subtracting the omitted-probe
correction produces the +100.098 pp value. Corrected contrasts can exceed
100 pp; the table retains those values without clipping.

## Plot methods

The cold-condition matrices show all 60 supporting per-mode point estimates,
rounded to two decimal places. Each column is one process within the named
queried bank. Both matrices use the same continuous color scale, including the
small negative value and values above 100 pp. Confidence intervals are not
encoded in the cells: supporting 95% within-run intervals remain in
`supporting-mode-table.csv`, and the separate confirmatory intervals appear
in the primary table above. Processes are not pooled.

The warm-condition bars show the six observed counts, each out of 1,024. They
start at zero and carry no inferred interval or additional confirmatory test.
The renderer uses bundled Inter fonts; its inputs, versions and font hashes
are recorded in `FIGURE-PROVENANCE.json`.

![K7 and K8 per-process adjusted contrast matrices](windows-causal-responses.png)

## Important exploratory qualification: the warm-condition sham

Sham equivalence applies to the declared **cold-condition primary endpoint**.
The warm-condition p0 supporting cell gives a different result:

| Repetition | Plain hits / 1,024 | Sham hits / 1,024 | Sham minus plain |
|---|---:|---:|---:|
| 1 | 317 | 160 | -15.332 pp |
| 2 | 293 | 126 | -16.309 pp |
| 3 | 275 | 130 | -14.160 pp |

The sham response is 14.160–16.309 pp lower than plain in these three
processes. This exploratory comparison is outside the six confirmatory
contrasts. Its cause remains unresolved.

![Exploratory warm-condition counts](warm-sham-exploratory.png)

## Host and measurement scope

The reported host is an 8-core/16-thread Ryzen 7 9800X3D, CPU signature
`0x00b40f40`, on Gigabyte X870E AORUS ELITE WIFI7, BIOS FA9, raw microcode bytes
`3540400b`, Windows 11 Pro build 26200.9168, Balanced power plan. The six attempts
share the reported boot beginning 2026-11-08T11:32:04.5000000Z. Before/after
inventories match the plan. VBS reports status 2 and hypervisor presence is true;
these facts do not establish every individual security feature's state.

The CPUID view reports `lfence_always_serializing=0`, leaf 80000021 EAX=1 and
IBS=0. LFENCE's observed suppression is a result of this tested configuration;
the absent advertised bit does not establish the actual LFENCE configuration,
and neither it nor CPUID suppression uniquely identifies a predictor mechanism.
All reload AUX values are zero. Affinity requests Windows logical CPU 0, but
constant AUX under a hypervisor is a weak independent migration witness.

All 1,966,080 recorded wanted/decoy timings are multiples of **47 TSC ticks**.
Pooled calibration HOT medians are 94 ticks and COLD medians 470 ticks. The clean
class separation validates the declared classifier on held-out controls, but
these values must not be read as precise instruction-cycle measurements. The
cause of the quantization was not established.

All training and probing occur at CPL3. The measurements do not identify the
exact predictor or isolate an exclusively transient path; instruction fetch,
private-bank heat and user-to-kernel influence remain unmeasured. Mode snapshots
record initial installations, and emitted code checks later installations,
without an independently attested instruction trace for every episode.
Allocation addresses vary across processes; the fixed-site claim is within
each process.

## Decision and use

The six-attempt Windows plan is complete. The next hardware phase needs a new
question and a validated native Linux backend. Inventory the available laptop
before choosing it or Linux booted directly on the Ryzen. Novelty relative to
prior work requires a separate literature comparison.

## Evidence and audit files

The package retains the two original uploaded ZIPs byte-for-byte in `inputs/`.
Their SHA-256 values are recorded in `integrity.json`. No new measurements were
collected during this audit. `replay.json` and the six replayed analyses retain
exact numerical results; `endpoint-table.csv` has all 18 primary intervals;
`supporting-mode-table.csv` has all 60 per-mode/bank outcomes. Independent
counts, code reviews, scripts and figure sources are included separately.
`FIGURE-PROVENANCE.json` records rendering versions, data hashes and uncertainty
scopes; [the reproduction guide](REPRODUCE.md#regenerate-the-figures) gives the
plot command.
