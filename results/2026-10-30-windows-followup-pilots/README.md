# Windows decision-source and branch-history pilots

**Status:** two distinct physical-host pilots in one session on 30 October 2026. Both raw traces validate against the prewritten analyzers and match their archived executables. Study A passes its predefined controls and shows a large decision-source interaction. Study B passes its added-work timer control but does not show the prespecified two-direction, sham-adjusted history effect. These are native Windows user-mode timing experiments, not a reproduction of Fractal's cross-privilege Apple M1 result.

## Evidence and method

The five [supplied original files and their SHA-256 digests](manifest.json) are preserved byte for byte, including the host snapshot, two `.log` traces and their matching `.exe` files. The two derived JSON summaries are [decision source](decision_source-summary.json) and [history probe](history_probe-summary.json). The source and prespecified estimands were recorded in [the study plan](../../WINDOWS_BRANCH_STUDIES.md) at commit `84f6182`, before these physical pilots. A trace and disassembly alone cannot prove that a particular Git revision produced an executable, so the source-revision association also depends on the documented build and archive workflow.

The snapshot was captured at `2026-10-30T16:36:50Z`. Study A started at `16:37:09Z`; study B at `16:37:24Z`. This is **one measurement session**, not two independent sessions. The snapshot records Windows 11 Pro build 26200, an AMD Ryzen 7 9800X3D, Gigabyte X870E AORUS ELITE WIFI7, BIOS FA9, a present hypervisor and the Balanced power plan. Both traces report CPU signature `0x00b40f40`, invariant TSC and hypervisor presence. The traces record a 47-TSC-tick GCD among measured totals; its physical cause is unknown. Microcode, mitigations, thermal state, competing load and SMT-sibling activity were not captured.

Each analyzer replays the seed-derived stimulus and condition order, validates every complete block and its checksums, and estimates paired *within-block* contrasts with a prespecified 10% trimmed mean. The reported 95% intervals resample complete condition-position cycles **within the one run**. They do not estimate uncertainty between runs, days or hosts. Neither pilot directly counts branch mispredictions.

## A: decision source at one branch instruction

This study keeps the live input stream while selecting, at runtime, whether the same conditional jump follows that live input or a fixed `0011` outcome stream. Its primary estimand is `[(live shuffled − live periodic) − (fixed shuffled − fixed periodic)] / 8192`, calculated within each block before trimming. There were 144 recorded eight-condition blocks, 8,192 calls per condition, and seed `1967219259`.

| Paired contrast | TSC ticks per iteration, 10% trim | Within-run 95% interval |
| --- | ---: | ---: |
| Primary interaction | **+17.083** | **[+16.874, +17.771]** |
| Live-source shuffled − periodic | +16.905 | [+16.840, +17.253] |
| Fixed-source shuffled − periodic | −0.0035 | [−0.0392, −0.0015] |
| Branchless shuffled − periodic | −0.0012 | [−0.0137, +0.0069] |
| Live − fixed, periodic input | −0.0016 | [−0.0117, +0.0016] |

All three negative-control **entire intervals** fit within the predeclared ±0.5 tick/iteration practical tolerance. The fixed-source control's small negative interval excludes zero; it is bounded by the tolerance, not exactly zero. The added-work timer control was positive in 141/144 blocks, with a +3,786.3 tick/batch trimmed mean and positive within-run interval, so its predefined gate also passes. The primary interaction was positive in 141/144 blocks; its first and second half estimates were +16.917 and +17.298.

The raw blocks contain large timing outliers. The primary blockwise interaction ranges from −314.829 to +159.233 ticks/iteration. A paired median is +16.896, an exploratory 20% trim is +16.891, and leaving out any one eight-block cycle yields a 10% trimmed estimate from +16.980 to +17.144. No blocks were removed. These checks support the positive sign while showing that the exact estimate and upper interval depend on the noise and estimator.

The compiled decision-source EXE has SHA-256 `f4b6e8e1970336781c018f70bc3f9360abf369a96faf657b1537c1b1f928fa03`; its executable `.text` section has SHA-256 `0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9`. After accounting for ASLR, the reported branch-site function entry maps to RVA `0x1bf0`; the conditional jump itself is at `0x1c05`. One direct in-loop call at RVA `0x1a8a` is shared by the primary conditions. Disassembly shows a runtime `cmovne` selecting the decision byte before the `test` and conditional jump. The branchless control function at RVA `0x1c09` uses `setne` without a conditional jump. The timed runner is bracketed by fenced TSC reads. This audits the intended instruction arrangement, but timing and disassembly do not isolate a predictor circuit from other decision-dependent execution effects.

**Interpretation:** this one run strongly supports a same-site dependence of batch time on the order of actual conditional-branch decisions, under these controls. It warrants independent seeded replication. It does not identify the hardware event responsible for each extra tick.

## B: history training before a fixed probe

Each episode runs the same 256-call balanced periodic prelude at the conditional site, trains for 256 calls with all zero or all one, then times a fixed 16-call probe. During training, the sham arm uses a separate branchless site; both arms still run the prelude and probe at the conditional site. The prelude standardizes prior activity but does not prove that predictor state was reset. Each of 320 randomized ten-condition blocks sums 128 episodes per condition; seed `2446820360`. For each probe outcome separately, the primary comparison is `(real-trainer mismatch − match) − (sham-trainer mismatch − match)`, formed within blocks and expressed in ticks **per 16-call probe**. These units are different from A's per-iteration units.

| Probe outcome | Real trainer mismatch − match | Sham mismatch − match | Prespecified sham-adjusted contrast, within-run 95% interval |
| --- | ---: | ---: | ---: |
| Probe 0 | +1.556 | +0.505 | **+0.919 [−0.242, +2.021]** |
| Probe 1 | −0.077 | +0.310 | **−0.480 [−1.211, +0.374]** |

The two adjusted intervals contain zero and the point estimates point in opposite directions. The real-trainer probe-0 interval alone is positive [+0.828, +2.184], but that comparison omits the prespecified sham adjustment and cannot be promoted after inspecting the data. Sham intervals themselves include effects comparable to the adjusted estimates; they have not established equivalence to zero.

The separate `PAUSE` added-work control was positive in 315/320 blocks (98.4%) and estimated +57.27 ticks per probe, with interval [+55.93, +57.68]. It passes the timer gate but does **not** establish sensitivity to effects around one tick. The adjusted probe-0 median is +1.469 ticks and an exploratory 20% trim is +1.341; the probe-1 median is −0.367 and the 20% trim is −0.426. Severe timing outliers dominate untrimmed means: the adjusted block extremes reach −25,997.6/+5,483.9 ticks for probe 0 and −7,728.9/+5,806.3 for probe 1. The prespecified 10% analysis remains primary; no blocks were discarded.

The compiled history EXE has SHA-256 `6e7575cb065c1828feaa7ef01b20ae9533a1c049b94f3b0df7181275887a45b3`; its `.text` SHA-256 is `b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b`. After accounting for ASLR, the reported conditional-site function entry maps to RVA `0x1c80`, its jump instruction to `0x1c85`, and the sham function entry to `0x1c8e`. The single in-loop direct call at RVA `0x1ae2` serves the prelude, real training and probe. The primary timed wrapper at RVA `0x1b50` has fenced TSC reads and no added-work branch; the slow timer wrapper at `0x1ba0` is separate. Sham and real training do have different outer caller sites. The 16 probe calls may also overwrite relevant trained state; that is a design limitation and a hypothesis, not an explanation proved by this pilot.

**Interpretation:** the prespecified two-direction, sham-adjusted criterion is not met by this pilot. The result neither demonstrates history transfer nor rules out a smaller or shorter-lived effect.

## Next measurements

Freeze the audited A protocol and run its planned replication with fresh recorded seeds: at least three complete runs in each of two sessions on **different days**, with a host snapshot per session. Repeating the *unchanged* B protocol under the same schedule would test whether its asymmetric result recurs; retain all positive, null and failed-control runs. Do not pool blocks across runs as if they were independent sessions, or let the exploratory 20% trim replace the specified analysis.

A shorter one- or two-call history probe and a smaller calibrated added-work control would address B's possible dilution and sensitivity limitations, but require a separately versioned exploratory pilot and a newly frozen primary rule before confirmatory replication. Keep its results separate from the current protocol. Counterbalance or record A/B run order in future sessions.

Study A tests local decision-order sensitivity as a prerequisite to studying branch behavior. Study B adapts the training-then-fixed-probe sequence in [Ravichandran and Yan's Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) and its pinned artifact (`experiments/utest.c`) within one user-mode process, using latency rather than a cache receiver. These studies do not boot Fractal, measure a cache receiver after a privilege handoff, establish speculative leakage, or reproduce the paper's Apple M1 result.

## Reproduce the analysis

From the repository root, with Python 3:

```bash
python3 scripts/analyze_decision_source.py results/2026-10-30-windows-followup-pilots/decision-source-windows-20261030T163709Z.log --strict --json
python3 scripts/analyze_history_probe.py results/2026-10-30-windows-followup-pilots/history-probe-windows-20261030T163724Z.log --strict --json
```

The [manifest](manifest.json) supplies byte sizes and SHA-256 digests for independent verification of the five original files. The archived JSON summaries were generated by those same commands. The import package contains the evidence and report; running either VS Code task again creates a **new** seed and trace rather than replaying these pilots.
