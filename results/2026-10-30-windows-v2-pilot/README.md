# Windows branch ablation: first version 2 run

**Status:** one validated physical-host pilot with one independent seed. This is a same-domain, user-mode timing experiment, not a misprediction counter or a user-to-kernel measurement. The relevant disassembly matches the experiment source at `16cbdba`; the raw trace itself does not record a Git commit. A later analysis-only change prints near-zero control effects with more precision and reports the number of positive block contrasts.

## Preserved artifacts and host

- [Complete trace](branch-batch-windows-20261030T130133Z.log), 144 blocks × eight conditions, 8,192 iterations per condition; eight warm-up blocks. Seed `1618039151` was selected before compilation; the run started at `2026-10-30T13:01:33Z`.
- [Matching executable](branch-batch-windows-20261030T130133Z.exe), SHA-256 `e0e6d0ef1c6c7ef18a000381ae6bdaccc00eb5e0106e50ef641fdf8b532200d1`, matching the trace's `BATCH_BINARY` record. Its `.text` section has SHA-256 `7ecae6f5ee8c9114e750f30c9c196b1c0685d9f0f0f302fb8d752296baa0d469`.
- [Host snapshot](host-windows-20261030T125908Z.json), captured 2 minutes 25 seconds before the run: Windows 11 Pro, build 26200, AMD Ryzen 7 9800X3D, 8 cores/16 threads, Gigabyte X870E AORUS ELITE WIFI7, BIOS FA9, Balanced power plan, hypervisor present. The trace records affinity to logical CPU 0 and invariant TSC. Microcode revision, exact mitigations, and background workload were not recorded.

The analyzer replays the recorded seed to validate pattern hash and complete eight-condition order, checks every sample and checksum, and resamples 18 complete eight-block position cycles for **within-run** bootstrap intervals. The archived EXE disassembly confirms one direct call from each 8,192-iteration loop to its respective site. At RVA `0x1c10`, the loaded branch uses `test; je` and loads `[rdx]` on the nonzero path. At `0x1c1e`, a distinct branch uses the same `test; je` pattern, returns 1 via `mov al,1; nop`, and does not read `[rdx]`. The branchless site at `0x1c2c` reads both bytes. Logged addresses map to these RVAs after ASLR. The timer control uses one scalar loop for both modes, testing a runtime flag before `PAUSE` every 128 iterations in slow mode.

## Results

All pattern contrasts below compare balanced shuffled outcomes against repeated `0011`, measured as TSC ticks per loop iteration. Point estimates are 10% trimmed means of within-block paired differences. Intervals are 95% bootstraps of whole eight-block cycles **inside this one run**.

| Contrast | Estimate | Within-run interval | Positive blocks |
| --- | ---: | ---: | ---: |
| Branch with target read | +16.280 | [16.241, 16.327] | 142/144 |
| Branch without target read | +16.649 | [16.609, 16.711] | 143/144 |
| Branchless comparator | −0.002176 | [−0.004155, −0.000099] | 43/144 |
| Loaded branch pattern effect minus branchless effect, paired by block | +16.283 | [16.227, 16.340] | 141/144 |
| No-load branch pattern effect minus branchless effect, paired by block | +16.668 | [16.608, 16.801] | 142/144 |
| Loaded minus no-load *pattern effect*, paired by block | −0.387 | [−0.561, −0.320] | 18/144 |

The branchless estimate is detectable by this run's bootstrap but about 0.013% of the loaded branch estimate in absolute value. An interval excluding zero is not a claim of hardware equivalence or practical importance. The `PAUSE` timer control was positive in 142/144 blocks; its trimmed mean slow-minus-fast contrast was +3,811 batch ticks, and its acceptance gate passed. This is an added-work check, not an isolated `PAUSE` instruction cost. Adjusted contrasts in the two halves were +16.278 and +16.290; no-load branch contrasts were +16.629 and +16.667.

The complete trace contains substantial isolated spikes. For example, block 92 has `branch_periodic=968717` ticks, versus roughly 33,000 in nearby ordinary blocks, giving an adjusted block contrast of −96.605 ticks per iteration. In block 21, `branchless_random=407443` versus roughly 29,500 ordinarily, giving an adjusted block contrast of −29.926. These blocks remain in the archive. Interruption or scheduling noise is a plausible explanation, not established from this trace. The pre-existing 10% trimmed estimator and paired medians both remain near +16.3 for the adjusted contrast. The GCD of recorded batch totals is again 47 TSC ticks; its cause remains unknown.

## Interpretation and replication

The strong timing contrast persists at a conditional branch that **does not read the target byte inside the timed function**, so that target-byte load is not necessary for this effect in this binary. The harness touches the target line before timing in every condition. This supports further study of outcome-dependent control flow and prediction, but the trace does not count wrong predictions or identify a unique microarchitectural cause. Loaded and no-load branches occupy different addresses and have different taken-path instructions, so their −0.387 contrast cannot be interpreted as the isolated cost of the target load. The two earlier [version 1 runs](../2026-10-30-windows-branch-batch/README.md) used a different binary, condition set and fixed seed; their +16.08/+16.09 estimates do not isolate the influence of changing seed.

For a follow-up replication, freeze the version 2 measurement code and keep **all** subsequent runs. Plan six further complete runs, three in one session and three in a later session, each with its automatically recorded seed. Capture a Windows host snapshot once per session and retain each matching log/EXE pair. Check the binary `.text` for consistency, compare **run-level** estimates and control outcomes, and report null or failed-control runs instead of discarding them. Do not pool individual blocks from separate runs as if they were independent sessions. This plan is a replication target, not a claim that six runs prove a mechanism.

From the repository root, reproduce this analysis with:

```bash
python3 scripts/analyze_branch_batch.py results/2026-10-30-windows-v2-pilot/branch-batch-windows-20261030T130133Z.log --strict --json
```
