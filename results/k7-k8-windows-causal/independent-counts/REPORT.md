# Independent K7/K8 raw-count audit

All six uploaded Windows traces agree exactly with their archived calibration thresholds, all 80 heldout wanted rates, all 80 decoy rates, all 140 apparatus gates, every adjusted outcome and all primary point estimates. The script uses only the Python standard library and never imports the project analyzers or executes the uploaded EXE.

Each trace has 163,840 rows: 81,920 calibration and 81,920 heldout rows. Each heldout mode/condition cell has exactly 1,024 observations, four in every heldout block. The six runs therefore contain 983,040 recorded rows and 491,520 heldout rows.

| Attempt | Study | Seed | p0 threshold | p1 threshold | Gates |
|---|---|---:|---:|---:|---:|
| attempt-01 | receiver | 1995552508 | 305 | 352 | 140/140 |
| attempt-02 | dependency | 1518277132 | 329 | 329 | 140/140 |
| attempt-03 | receiver | 1943616535 | 352 | 352 | 140/140 |
| attempt-04 | dependency | 1237717043 | 352 | 399 | 140/140 |
| attempt-05 | receiver | 227777600 | 305 | 399 | 140/140 |
| attempt-06 | dependency | 2664525160 | 329 | 376 | 140/140 |

| Attempt | Declared primary endpoint | Exact point estimate (pp) |
|---|---|---:|
| attempt-01 | p0_plain_minus_ablate_one | +99.804687500 |
| attempt-01 | p1_plain_minus_ablate_zero | +99.609375000 |
| attempt-01 | p0_plain_minus_sink_both | +99.804687500 |
| attempt-01 | p1_plain_minus_sink_both | +99.414062500 |
| attempt-02 | p0_sham_minus_true | +99.902343750 |
| attempt-02 | p0_plain_minus_sham | -0.097656250 |
| attempt-03 | p0_plain_minus_ablate_one | +99.707031250 |
| attempt-03 | p1_plain_minus_ablate_zero | +100.097656250 |
| attempt-03 | p0_plain_minus_sink_both | +99.707031250 |
| attempt-03 | p1_plain_minus_sink_both | +100.097656250 |
| attempt-04 | p0_sham_minus_true | +99.707031250 |
| attempt-04 | p0_plain_minus_sham | +0.097656250 |
| attempt-05 | p0_plain_minus_ablate_one | +99.804687500 |
| attempt-05 | p1_plain_minus_ablate_zero | +99.707031250 |
| attempt-05 | p0_plain_minus_sink_both | +99.804687500 |
| attempt-05 | p1_plain_minus_sink_both | +99.804687500 |
| attempt-06 | p0_sham_minus_true | +99.414062500 |
| attempt-06 | p0_plain_minus_sham | +0.097656250 |

## Exact count interpretation

For each mode and p, the adjusted outcome is (mismatched candidate hits minus matched candidate hits minus mismatched omitted-probe hits plus matched omitted-probe hits) divided by 1,024. The endpoint then subtracts the two modes' adjusted outcomes. This difference of differences is not a single hit probability; values slightly above +100 percentage points are mathematically valid and must not be clipped.

- attempt-03, `p1_plain_minus_ablate_zero`: [(1024 - 0 - 0 + 1) - (0 - 0 - 0 + 0)] / 1024 = +100.097656250 pp.
- attempt-03, `p1_plain_minus_sink_both`: [(1024 - 0 - 0 + 1) - (0 - 0 - 0 + 0)] / 1024 = +100.097656250 pp.

## Stratum checks

Reload-order and episode occurrence strata were independently counted and matched the archived strata exactly. The CSV records their raw counts; JSON also records stratum-specific endpoint point estimates. These are descriptive checks, without multiplicity adjustment or separate confidence intervals.

- attempt-01: largest reload-order cell difference is 3.222 pp in `plain/warm_mismatch_p1`; largest episode range is 6.250 pp in `plain/warm_mismatch_p0`.
- attempt-02: largest reload-order cell difference is 4.013 pp in `sham_mask/warm_mismatch_p0`; largest episode range is 5.078 pp in `sham_mask/warm_mismatch_p1`.
- attempt-03: largest reload-order cell difference is 2.873 pp in `ablate_zero/warm_mismatch_p0`; largest episode range is 7.812 pp in `ablate_zero/warm_mismatch_p0`.
- attempt-04: largest reload-order cell difference is 2.871 pp in `sham_mask/warm_mismatch_p1`; largest episode range is 8.984 pp in `sham_mask/warm_mismatch_p1`.
- attempt-05: largest reload-order cell difference is 4.731 pp in `ablate_one/warm_mismatch_p1`; largest episode range is 5.859 pp in `ablate_zero/warm_mismatch_p0`.
- attempt-06: largest reload-order cell difference is 3.184 pp in `plain/warm_mismatch_p1`; largest episode range is 8.984 pp in `sham_mask/warm_mismatch_p1`.

Across both reload orders and all four episode occurrences, the smallest suppression point estimate is 98.437500 pp; the largest absolute plain-minus-sham point estimate is 0.781250 pp. These descriptive strata do not expose a loss of the large primary pattern, although they do not independently establish interval coverage.

## Exploratory warm-condition limitation

The matched sham is equivalent to plain for the declared cold-condition primary outcome. It is not inert in every condition: with a warm condition line, p0 sham responses are consistently smaller than plain. This is a secondary observation, without a new confirmatory test or unique mechanism attribution.

| Dependency attempt | Warm p0 plain hits /1024 | Warm p0 sham hits /1024 | Plain minus sham (pp) |
|---|---:|---:|---:|
| attempt-02 | 317 | 160 | +15.332031 |
| attempt-04 | 293 | 126 | +16.308594 |
| attempt-06 | 275 | 130 | +14.160156 |

## Control and timing checks

| Attempt | HOT hit range /1024 | Largest matched candidate hits /1024 | Largest omitted-probe hits /1024 | Largest decoy hits /1024 | Timing gcd |
|---|---:|---:|---:|---:|---:|
| attempt-01 | 1021–1024 | 3 | 0 | 1 | 47 |
| attempt-02 | 1023–1024 | 2 | 0 | 1 | 47 |
| attempt-03 | 1021–1024 | 1 | 1 | 1 | 47 |
| attempt-04 | 1022–1024 | 3 | 1 | 1 | 47 |
| attempt-05 | 1021–1024 | 4 | 0 | 1 | 47 |
| attempt-06 | 1023–1024 | 5 | 1 | 1 | 47 |

The timing gcd is computed across every wanted and decoy timing, including calibration. All values are multiples of the recorded gcd; the calibration HOT median is 94 and COLD median is 470 in all banks and attempts. This quantization does not remove the observed cache-class separation, but these values should be described as recorded TSC differences rather than precise instruction-cycle latencies. The audit does not determine the cause of the quantization.

## Limits

This audit confirms arithmetic agreement with the recorded traces. It does not independently attest physical hardware, boot history or provenance, and does not recompute bootstrap intervals. The interventions act during both training and probing; suppression therefore concerns the whole intervention. The private-bank control measures loss of the public-bank response, without a private-bank heat sensor. Same-boot fresh processes are not independent boot or host replications.

All six CPU records report hypervisor=1, IBS=0 and LFenceAlwaysSerializing=0. This last feature bit being zero does not by itself establish that LFENCE is nonserializing in the recorded environment; any LFENCE suppression is an observed intervention outcome under that environment. None of these arithmetic checks proves a unique predictor mechanism or user-to-kernel influence.
