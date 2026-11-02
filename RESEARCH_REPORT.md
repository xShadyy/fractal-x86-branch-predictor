# Native x86 branch studies: consolidated research record

**Evidence through 2 November 2026.** These are native Windows x86 experiments on one AMD Ryzen 7 9800X3D workstation. The strongest observations are repeatable, controlled **same-host timing associations** and a three-run **receiver scheduling association**. No experiment has recovered a trained target, counted mispredictions, established transient execution, or tested a privilege boundary. A passing apparatus gate makes an outcome eligible under its own protocol; it does not identify a hardware mechanism.

## Relationship to Fractal

[Ravichandran and Yan's *Fractal* paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) develops an OS for low-noise microarchitecture reverse engineering and evaluates Apple M1 branch predictors with instruction-fetch and data-execution receivers across security domains. Its Table 1 reports 48 M1 outcomes: conditional/indirect predictor × performance/efficiency core × ordinary/branch-removed receiver × same user and ASID/user-to-kernel/different ASID × fetch/execution. Those are the authors' findings. The [pinned upstream revision](UPSTREAM_FRACTAL_REVISION) identifies the separate upstream project.

This repository runs ordinary user-mode code in one Windows process on AMD x86. Its TSC and data-cache outcomes cannot reproduce or refute an M1 result. A branch-time difference measures neither speculative instruction fetch nor target execution. A hot data line can support target-execution inference only after target specificity, architectural exclusivity and alternative cache-fill paths are validated.

| Paper category | Local measurement status |
| --- | --- |
| Conditional branch present, same-domain data execution | Conditional cache baseline and K1/K2 pilots. K1 fails frozen skip gates. K2 detects schedule-sensitive skip-line heat without trained-label specificity. |
| Indirect branch present, same-domain data execution | I calibrates its receiver but shows no convincing opposite-target signal; H's small-work sensitivity fails. |
| Instruction fetch, including proposed J | No target-specific isolated instruction-cache receiver. J is unimplemented; whole-call timing would not isolate fetch. |
| Branch removed / Phantom | No audited same-address branch-to-NOP receiver experiment. Unimplemented. |
| User-to-kernel, different ASID, M1 core classes, Fractal scheduler/gmap | Untested here. The 9800X3D does not supply M1 performance/efficiency core classes. |

## Host, evidence, and statistical rules

Archived snapshots and later traces identify AMD Ryzen 7 9800X3D, `AuthenticAMD` signature `0x00b40f40`, Windows 11 Pro build 26200, reported hypervisor presence, and process affinity to logical CPU 0. Batch totals show an observed 47-TSC-tick GCD, of unknown cause. Microcode, SMT-sibling load, mitigation state, thermal/frequency drift and competing work were not controlled across sessions.

Randomized complete blocks, frozen gates, held-out calibration, raw traces, executable hashes, and linked PE inspection constrain interpretations. All reported 95% bootstrap intervals resample complete block cycles **within one run**. They are not intervals across runs, dates, hosts, or a processor population. A zero-containing interval is not proof of equivalence; a pilot-informed follow-up is not independent confirmation of the pilot. The [machine-readable results ledger](results/RESULTS_LEDGER.json) preserves archive identifiers, evidence locations, and a digest of historical reports. ZIP SHA/CRC, manifest, strict replay, source tree, and `.text` checks establish internal consistency, not independent attestation of host conditions.

## A and B: two-date timing replication

Each study had one separate pilot, then six complete distinct-seed runs: three on 30 October and three on 31 October. A's primary estimand is the paired shuffled-versus-periodic live-stream interaction under live versus fixed branch decisions, divided by 8,192 iterations. It requires three negative-control **whole intervals** inside ±0.5 TSC ticks/iteration and an added-work timer gate. B subtracts branchless-sham mismatch-minus-match training from same-branch-site training **within each block**, separately for fixed 16-call probe outcomes 0 and 1. B's added-work timer is its formal gate; the original plan had no numerical pass/fail gate for a bidirectional effect.

| Date and study | Three run estimates | Verdict |
| --- | --- | --- |
| 30 Oct, A | +16.850, +17.040, +17.167 ticks/iteration | All negative and timer controls pass. |
| 31 Oct, A | +16.936, +17.047, +17.064 ticks/iteration | All controls pass; descriptive day means +17.019 and +17.016. |
| 30 Oct, B probe 0 | +4.468, +2.781, +2.048 ticks/fixed probe | All within-run intervals above zero, timer passes. |
| 31 Oct, B probe 0 | +2.555, +2.441, +2.048 ticks/fixed probe | All intervals above zero, timer passes; day means +3.099 and +2.348. |
| 30/31 Oct, B probe 1 | −1.256, −0.123, +0.075 / +0.283, +0.832, −0.590 ticks/fixed probe | All six intervals include zero; no bidirectional crossover. |

All 12 traces replay strictly and match their EXE hashes. The six A executable `.text` hashes match the audited pilot's `0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9`; B's six match `b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b`. Static PE inspection locates A's conditional jump at RVA `0x1c05` and B's at `0x1c85`. B's sham uses another address and its 16-call probe can itself change the state sampled. A's controls narrow input-processing explanations; neither study counts branch misses. Day 1 ran A then B, day 2 B then A: day and order effects remain confounded. The [full run summary](results/2026-10-30-31-windows-followup-replication/series-summary.json), [original-file hashes](results/2026-10-30-31-windows-followup-replication/original-file-sha256.json), [raw sessions](results/2026-10-30-31-windows-followup-replication/), and [figure](results/2026-10-30-31-windows-followup-replication/followup-replication.svg) retain details; figure whiskers are within-run intervals.

## Fourteen-study exploratory suite, 31 October

The one-session archive `suite-evidence-suite-20261031T213948Z-8ee83ab7.zip`, SHA-256 `e595d4fb38638961d4c9a2a8eb0ee1f25789b2899cb668a02989d4ec5e2ba40e`, contains 14 paired EXE/traces among 78 members. Manifest and replay checks passed. Ten checks were accepted; four failed declared controls and stay **inconclusive**. These are pilots, not 14 replications. Bracketed ranges below are 95% within-run intervals, in each row's unit.

| Study | Gate | Pilot observation and boundary |
| --- | --- | --- |
| Cache controls | Pass | Held-out hot 100%, cold 0%, architectural load 100%, skip 0%. |
| Conditional cache receiver | Pass controls | Trained-taken/not-taken opposite-line hits 0.2%/0.0%; no convincing target signal. |
| Branch batch | Pass | Adjusted shuffled minus periodic +16.421 [+16.283,+16.879] ticks/iteration; no-load ablation uses another branch address. |
| Single-branch latency | Valid diagnostic | Probe 0 +0.4 [−0.4,+1.4], probe 1 −0.3 [−1.2,+0.6] ticks; few-tick sensitivity unestablished. |
| A decision source | Pass | +17.196 [+16.857,+18.218] ticks/iteration; three practical negatives and timer pass. |
| B1 history | Pass timer | Adjusted probe 0 +2.99 [+1.04,+5.03], probe 1 +0.90 [−1.10,+2.85] ticks/fixed 16-call probe; no crossover. |
| L prelude sweep | **Inconclusive** | Fixed-trainer equivalence fails ±1 gate; prelude contrasts include zero. No path-history length inferred. |
| D intervening activity | Pass | Filler counts 0/16/64/256 yield no resolved difference; no retention depth identified. |
| E training dose | **Inconclusive** | Small-work sensitivity and fixed/zero-dose equivalence fail; no dose threshold inferred. |
| C pattern complexity | Pass | Preselected period-2 versus period-32 −0.0023 ticks/iteration, interval includes zero. Exploratory shuffled versus period-32 +18.261 [+18.107,+18.388] with controls passing. |
| F address sensitivity | Pass controls | Planned same-4K versus offset-128 probe interactions −0.590 [−1.361,+0.148] and +0.447 [−0.748,+1.783] ticks/probe; runtime copies not independently dumped, no index bit inferred. |
| I indirect cache receiver | Pass controls | Opposite-target changes −0.6%/+0.2%, no convincing signal; target 1 shares an instruction line with sham. |
| H indirect target timing | **Inconclusive** | Small-work controls +0.008/+0.143 ticks/probe, intervals include zero; PAUSE alone does not validate fine-scale sensitivity. |
| B2 original probe length | **Inconclusive** | Probe-1 one-call timer +0.318 [+0.036,+0.587], below frozen +1 magnitude gate; probe-0 +1.116 [+0.669,+1.524] is exploratory only. |

Archived linked-PE inspection supports intended branch/timer/target topology, subject to F's runtime copies and I's fetch-line and exclusivity caveats. An RX copy is not Fractal's gmap. Heterogeneous endpoints and failed gates cannot be pooled into a common effect.

## B2: same-site probe outcome

The original B2 pilot's failed gate was retained. [Calibration v2](protocols/B2_CALIBRATION_V2.md) tested apparatus only and failed three 16-call baseline-equivalence intervals despite detectable added work. [Precision v3](protocols/B2_PRECISION_V3.md) changed apparatus under a new frozen protocol and passed 16/16 gates, without collecting a training outcome. [Outcome v4](protocols/B2_OUTCOME_V4.md) then tested one primary real-minus-fixed training interaction at the **same conditional branch site**: probe outcome 0, one probe call, TSC ticks per **complete episode**. Its practical association rule required the whole interval beyond +1 or −1 tick. Fixed-decision training is an ablation, not a predictor-free intervention.

| Stage | Original ZIP SHA-256 | Apparatus | Outcome |
| --- | --- | --- | --- |
| v2 calibration pilot | `9c71dca5d33c1751bfedcf759aa9eb5e5789b53a40ce8b8e437da449c840abce` | Three baseline-equivalence intervals fail | No training endpoint. |
| v3 precision pilot | `d956fc935b24e547154d1979eac1d6a873a7b9d7ce708f3920baf205f1cc88c1` | 16/16 pass | No training endpoint. |
| v4 initial outcome, 1 Nov | `2e52aaffa916e575976fbf81aab7d907173b35945c7985adc8c44d71d3005f35` | 16/16 pass | +0.136 [+0.003,+0.272] ticks/episode. Excludes zero within run, remains below +1 rule. |
| [Three-run v4 replication](protocols/B2_REPLICATION_V1.md), same date | Outer ZIP `805ff9fdb9a02d378e834d1dff0125c58a1c735df5d9c8390a1ecf7196ad5c6d` | 16/16 pass in each | −0.0479 [−0.1919,+0.0937]; +0.0060 [−0.1219,+0.1308]; +0.0397 [−0.0692,+0.1454]. None clears ±1 rule. |

The initial and replication `.text` sections match SHA-256 `1289fa0d276ca798fdf80b0319730d97fc19391e85f78d71c64e96f62c3b947e`; the linked jump is at PE RVA `0x20f5`. All four outcome runs were on one UTC date; replication was chosen after seeing the initial outcome. The tiny first-run exclusion of zero is neither practical association under its frozen gate nor day-level confirmation. PAUSE detects much larger added work; calibrated `dose4` checks a few-tick scale. Pair carryover, host behavior and the observed timing lattice remain unresolved.

## K1: conditional data-cache receiver

[K1's frozen protocol](protocols/CONDITIONAL_RECEIVER_V1.md) aimed to detect a trained but architecturally skipped conditional target by its data-cache line. Two earlier MASM `A2006` attempts stopped at assembly and yielded **no measurement**. One independently checked failed-build ZIP has SHA-256 `81ad2a549331531096356d20d3997a1e1556c6a6582bb595cd26a927328252b2`; the second user-reported failed-build ZIP has SHA-256 `58e2af84ee2d786451d9d555c0b161dbc32683f9b48ada7c56c3ab7ad66d7d92`, without independent ZIP verification. The corrected executable completed 512 blocks, 64 raw episodes per condition. Original ZIP `conditional-receiver-windows-20261101T172116138Z.zip`, SHA-256 `4d5ce4aa5a4c13460abecfec4563e74a400203d452c134072697bfac6acf506f`.

Held-out hot 99.82/99.92%, cold ≤0.006%, architectural load 99.88/99.87%, and no-probe ≤0.006% passed. **Architectural skip was 8.25%/8.06%, above K1's frozen ≤5% gate in both directions.** Adjusted mismatch-minus-match estimates were +0.75 [−1.97,+3.05] and +2.66 [−1.82,+7.47] percentage points. K1 is **inconclusive**, neither an eligible positive nor an eligible null; strict exit code 1 reflects the failed gate. Dropping hot first episodes retrospectively would violate its protocol.

Linked PE inspection maps K1's shared conditional branch to RVA `0x2030`, target bodies to `0x20c2`/`0x203d`, and condition/target data to separate pages. Flush, fence, and fenced reload occur in the path. The optimized collector has a branch into HOT's explicit touch after flush; speculation along that harness branch is one possible contaminant. Target code-fetch layout is asymmetric. A post hoc first-five-episode spike motivated K2, but cannot repair K1's gate or establish its cause.

## K2: receiver order diagnostic

[K2's protocol](protocols/RECEIVER_ORDER_K2.md) compares grouped 64-episode cells with interleaved scheduling at one conditional branch and two target data pages. There are 16 warmup and 256 recorded complete blocks; the first 128 calibrate thresholds and final 128 are held out. Its 20 hot/cold/architectural-load/no-probe apparatus gates differ from K1's: architectural **skip is an outcome, not a gate**. The frozen primary is the within-block grouped probe-0 first-five minus later-59 skip-hit rate. A within-run 16-block-cycle bootstrap interval entirely above +10 percentage points classifies a *condition-entry association for that run*, not trained-target recovery.

| UTC start, seed | Original ZIP SHA-256 | Gates | Primary grouped p0 early minus late, within-run 95% interval | Grouped p1 early minus late | Full-cell skip, grouped p0/p1; interleaved p0/p1 |
| --- | --- | --- | --- | --- | --- |
| 1 Nov 18:31:45, `1992600106` | `7d464c02af3e13e0051ed771756bcf8c220143d0a40226e85d9e598b50260cb5` | 20/20 | **+31.15 [10.99,53.65] pp** | +43.84 [25.25,60.65] pp | 2.69/3.49%; 61.06/46.15% |
| 1 Nov 19:25:10, `1644643828` | `46403c95f5c3754ec41dc729d514ee06ed050950dfe6791f1360ebfe23acb96c` | 20/20 | **+50.37 [34.81,63.63] pp** | +47.39 [33.46,57.71] pp | 4.19/3.81%; 57.68/47.06% |
| 2 Nov 19:05:23, `2013934917` | `16065ccdac9bff43280fc48c1db89e236682f84940b95a42f25913d4e1326b4f` | 20/20 | **+56.51 [42.39,65.93] pp** | +46.61 [21.48,68.67] pp | 4.63/3.75%; 63.83/52.21% |

All three clear K2's **within-run entry rule** on one host across two UTC dates. Grouped p0 early/late rates were 31.41/0.25%, 50.63/0.25%, and 56.72/0.21%. The eight held-out cycles per run vary widely and the interleaved skip line is often hot. The three distinct-seed runs are observations of between-session recurrence; no three-run confidence interval or population estimate is inferred from the many dependent episodes. K2 was designed from K1's exploratory spike, so K1 and K2 are not independent mechanism discovery and confirmation.

Every K2 candidate **trained-label mismatch-minus-match** interval includes zero in grouped and interleaved modes on all dates. Day-two grouped p1, for example, was +1.343 [−0.024,+3.088] pp. The day-two p1 threshold was 258 ticks versus p0 352; an exploratory 188-tick reclassification preserves the main schedule pattern but does not replace frozen calibration. High skip-line heat could involve branch-path activity, prefetch, global history, condition ordering, harness behavior or host state. It does **not** demonstrate which trained target was selected, misprediction, or transient target execution.

The three linked `.text` sections are byte-identical, SHA-256 `54d9af2ea69a7acff3ba2a57e1872550f15b2a3455b1d5046be49dd08fda12c8`; full PE hashes differ in timestamps. Static review maps the shared branch to RVA `0x2680`, targets to `0x2712`/`0x268d`, and condition/target data to distinct pages. HOT uses a separate explicit-touch helper; candidate/skip use flush/fence/branch/fenced reload. Target one shares an instruction line with the branch, whereas target zero has another fetch layout. This verifies intended topology, not the causal source of heat. The [three-run figure](results/2026-11-02-windows-receiver-order-day2/three-run-contrast.svg) and [plot source](results/2026-11-02-windows-receiver-order-day2/plot_three_runs.py) display run-level outcomes without treating episodes as independent replications.

## Provenance, reproduction, and inference

Raw A/B and branch-batch traces/binaries, JSON summaries, plot scripts and original-file ledgers are under [results/](results/). The suite/B2/K1/K2 original ZIPs were supplied separately; their exact hashes appear here and in the [results ledger](results/RESULTS_LEDGER.json). For an original ZIP, verify SHA-256 and manifest, replay the matching `scripts/analyze_*.py` against its `.log` at the recorded source tree, and compare executable and linked `.text` hashes. `scripts/summarize_followup_series.py` recomputes A/B from raw files, and `scripts/summarize_b2_outcome_replicates.py` reads the B2 outer ZIP. Unit tests check parsing and analysis, not physical host execution.

The supported observations are A's repeated same-host decision-order timing association, B's probe-0 association without the intended probe-1 crossover, a B2 same-site interaction below its practical rule, K1 inconclusive after failed skip gates, and K2's repeated schedule-sensitive cache-hit pattern without trained-target specificity. Together they establish no predictor table size, path-history-register length, misprediction count, speculative fetch/execution, domain transfer, Phantom effect, or M1 finding. A future mechanism assay needs a validated exclusive target-specific receiver, complete retention of failed attempts, linked-code and alternative-cache-path audit, and a separately controlled intervention.
