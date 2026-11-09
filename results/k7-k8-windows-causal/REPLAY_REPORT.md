# Frozen replay review of the Windows K7/K8 results

This record reproduces the frozen numerical analysis. The [result report](README.md) adds independent-count and static-code reviews and the warm-condition qualification.

All six saved analyses reproduce exactly from their raw traces under trusted commit `8080faed480a9eef086f1fc0396e38dba7de31c7`. Each attempt contains 163,840 episodes, passes 140 of 140 apparatus gates, and meets its frozen `valid_response` rule. Total recorded episodes: **983,040**. The replay used the clean, hash-matched Python analysis code and treated the uploaded executable, object files and runtime code as data.

`replay.json` contains the checks and per-attempt endpoints. Each `attempt-XX-replayed-analysis.json` is the complete recomputation. The JSON objects match all uploaded `analysis.json` values without differences. `endpoint-table.csv` and `supporting-mode-table.csv` retain unrounded values in percentage points.

## Confirmatory endpoints

Cells below show estimate [lower, upper] in percentage points. These are the frozen Bonferroni-adjusted percentile-bootstrap intervals for six prespecified endpoints per scheduled dependency/receiver repetition pair: nominal 99.1667% per endpoint, nominal 95% family coverage per pair. The bootstrap resamples 16 paired clusters of 16 held-out blocks; it does not represent uncertainty between independent boots. The three repetitions are shown separately and are not pooled.

| Endpoint | Repetition 1 | Repetition 2 | Repetition 3 |
| --- | ---: | ---: | ---: |
| p0_sham_minus_true | +99.902 [+99.609, +100.000] | +99.707 [+98.535, +100.000] | +99.414 [+98.535, +100.000] |
| p0_plain_minus_sham | -0.098 [-0.391, +0.000] | +0.098 [-0.488, +1.270] | +0.098 [-0.684, +1.172] |
| p0_plain_minus_ablate_one | +99.805 [+99.414, +100.000] | +99.707 [+99.316, +100.000] | +99.805 [+99.414, +100.000] |
| p1_plain_minus_ablate_zero | +99.609 [+99.023, +100.195] | +100.098 [+100.000, +100.391] | +99.707 [+99.316, +100.000] |
| p0_plain_minus_sink_both | +99.805 [+99.414, +100.000] | +99.707 [+99.316, +100.000] | +99.805 [+99.414, +100.000] |
| p1_plain_minus_sink_both | +99.414 [+98.926, +99.902] | +100.098 [+100.000, +100.391] | +99.805 [+99.414, +100.000] |

The dependency suppression contrasts exceed the prespecified +10 pp practical margin in all three processes. All three plain-minus-sham intervals fall inside the prespecified equivalence interval of −10 to +10 pp. Each of the four receiver suppression endpoints also exceeds +10 pp in all three processes.

Adjusted contrasts can slightly exceed 100 pp: they subtract a no-probe training contrast before comparing modes. They are not individual hit probabilities and must not be clipped to [0,100].

## Baselines, gates, and calibration

| Attempt | Study | Seed | Gates | p0 threshold | p1 threshold | Observed AUX |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | receiver | 1995552508 | 140/140 | 305 | 352 | 0 |
| 2 | dependency | 1518277132 | 140/140 | 329 | 329 | 0 |
| 3 | receiver | 1943616535 | 140/140 | 352 | 352 | 0 |
| 4 | dependency | 1237717043 | 140/140 | 352 | 399 | 0 |
| 5 | receiver | 227777600 | 140/140 | 305 | 399 | 0 |
| 6 | dependency | 2664525160 | 140/140 | 329 | 376 | 0 |

Thresholds are TSC ticks, not assumed core cycles. Only first-half HOT/COLD observations select them; candidate outcomes never select a threshold. All apparatus gates and reported intervention outcomes use the held-out second half. The plain baseline is eligible in every required bank: p0 for dependency and both banks for receiver. Baseline intervals are descriptive 95% intervals, not additional confirmatory endpoints or apparatus gates.

HOT remains positive in every mode. COLD, NO-PROBE, training-matched candidates, and decoys meet their cold gates. Architectural LOAD is positive when the queried public encoder exists and cold when it is ablated or relocated. Thus the receiver result does not merely reflect an unusable reload sensor.

## Dependency supporting observations

All values below are adjusted training contrasts in pp with descriptive 95% within-run intervals.

| Bank and mode | Repetition 1 | Repetition 2 | Repetition 3 |
| --- | ---: | ---: | ---: |
| p0 / plain | +99.805 [+99.512, +100.000] | +99.805 [+99.512, +100.000] | +99.512 [+99.121, +99.805] |
| p0 / sham_mask | +99.902 [+99.707, +100.000] | +99.707 [+99.121, +100.000] | +99.414 [+98.730, +99.902] |
| p0 / true_mask | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| p0 / lfence | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| p0 / cpuid | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| p1 / plain | +99.707 [+99.414, +100.000] | +99.219 [+98.438, +99.805] | +99.219 [+98.633, +99.707] |
| p1 / sham_mask | +99.805 [+99.512, +100.000] | +99.902 [+99.707, +100.000] | +99.609 [+99.121, +100.000] |
| p1 / true_mask | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| p1 / lfence | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| p1 / cpuid | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |

Every held-out true-mask, LFENCE, and CPUID adjusted contrast is zero in these recorded samples. The corresponding bootstrap interval [0,0] is a consequence of resampling all-zero cluster contrasts. It does not establish an exactly zero population effect or a universal barrier guarantee.

The exposed CPUID record is `hypervisor=1`, `lfence_always_serializing=0`, `cpuid_80000021_eax=0x00000001`, and `ibs=0`. LFENCE suppression is an observed intervention result in this configuration. These data do not establish LFENCE serialization on every configuration or reveal hidden hypervisor/MSR policy.

## Receiver specificity beyond the primary endpoints

Ablating the other, unqueried bank largely preserves the queried bank response. Below, intervals are exploratory 95% paired-cluster intervals, outside the six-endpoint confirmatory family.

| Supporting contrast | Repetition 1 | Repetition 2 | Repetition 3 |
| --- | ---: | ---: | ---: |
| p0_plain_minus_ablate_zero | +0.195 [-0.195, +0.586] | -0.293 [-0.586, +0.000] | +0.195 [-0.293, +0.684] |
| p1_plain_minus_ablate_one | -0.098 [-0.586, +0.391] | +0.488 [+0.195, +0.879] | +0.195 [-0.195, +0.586] |

These differences are small relative to the roughly 100 pp queried-bank suppression. One supporting interval excludes zero, so exact equality would overstate the result. All six intervals remain within ±0.879 pp. The result supports strong bank specificity without asserting that every microarchitectural consequence is identical.

`sink_both` retains the same runtime opcode image as `plain`; validated context bindings move the marker loads to private banks. Loss of the public response supports attribution to the selected public marker access. Private-bank heating was not measured, so this is not a direct private-cache observation.

## Interpretation

The [result report](README.md#supported-result) interprets these contrasts alongside the warm-condition counts and code review. Training and probing both use the installed mode and remain at CPL3. The three fresh processes per study share one reported boot; these within-run intervals do not quantify between-boot or between-host variation.

## Provenance notes

- The working tree was clean at the expected frozen commit before analysis. All 14 plan-listed LF-normalized source hashes match both the trusted repository and the uploaded source archive.
- The evidence and plan archives contain byte-identical plan JSON. The uploaded source archive SHA-256 matches the frozen plan.
- Strict trace replay verifies every planned episode order, seed-dependent token/decoy/reload order, timing checksum, event hash, architectural return, CPL/PC record, code snapshot, context binding, and stable observed TSC_AUX identity.
- All observed AUX values are 0. AUX equality with the Windows processor index was not assumed.
- Byte inspection confirms the binary hash and embedded template. The emitted-code review is recorded separately in [static/short.md](static/short.md).
- Full manifest, ledger, host-before/after, and linked-path review are complementary provenance checks. This report concentrates on exact frozen raw-trace analysis and its interpretation.
