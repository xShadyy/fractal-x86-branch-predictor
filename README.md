# x86 Branch Predictor Experiments

Independent microarchitecture experiments on x86, informed by [Fractal](https://github.com/jprx/fractal) and the [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) by Joseph Ravichandran and Mengjia Yan. The repository pins the upstream revision and contains independent measurement code.

## Run from VS Code on Windows

Install [VS Code](https://code.visualstudio.com/), Microsoft C++ Build Tools with **Desktop development with C++** and a Windows SDK, and Python 3. Open this repository in VS Code and press **Ctrl+Shift+B**. The `Cache probe: build, run, analyze (Windows)` task compiles a native x64 executable, pins it to one allowed logical CPU, records a raw trace in `out/`, and runs the analyzer. It locates the MSVC build environment automatically through `vswhere`.

The output reports the CPU signature, a threshold fitted from the first half of the calibration samples, and held-out hit rates for four controls. The task returns an error if the controls are inconclusive. `out/` is ignored by Git.

For the paired single-task branch experiment, open **Terminal → Run Task** and choose **Branch probe: build, run, analyze (Windows)**. This task uses `ml64.exe` to assemble one fixed conditional branch and writes a separate `spec-probe-windows-*.log` trace under `out/`.

## Measurement

The program interleaves 1,024 samples in each class: a known cached line, a flushed line, a line loaded at an architecturally executed branch target, and a line skipped by the branch. A fence before the target load keeps speculation out of this calibration. Only the subsequent cache-line reload is timed. The full record is buffered until the measurement ends.

The analyzer uses the first half of the hot and cold samples to fit a cache-hit threshold and evaluates all four controls on the held-out half. Its acceptance gate requires at least 95% hits for the cached and target-loaded classes, and at most 5% hits for flushed and skipped classes. Inspect the optimized instructions when changing compiler settings or branch code.

## Paired branch experiment

Each block runs 128 training calls at the same assembly branch address for each label. The measured call always skips the target. Its condition line and target line are flushed beforehand, and only the later target-line reload is timed. The two training labels appear in randomized, balanced order within 1,024 blocks. Hot and cold controls run in every block. Two additional controls execute and skip the target at the same assembly branch site, without training. Samples are buffered and include the branch address, CPU signature, seed, order, and raw cycles.

The branch analyzer chooses its threshold using hot and cold controls from the first half of blocks. It checks both these and the same-branch-site controls on the second half, then reports the paired difference in probe cache-hit rates and a within-run bootstrap interval. Repeat runs and inspect their raw traces before interpreting the effect. The task fails only when the controls are invalid or the trace is incomplete; a zero effect means this probe did not detect a difference. It cannot establish whether the branch was mispredicted or whether a transient target load could reach the cache.

## Branch timing follow-up

If the branch probe detects no cache effect, choose **Terminal → Run Task → Branch latency: build, run, analyze (Windows)**. This separate experiment trains the same assembly branch site with condition 0 or 1 for 128 calls, then times one call with condition 0 or 1. Both the condition and target lines remain cached. Each of 4,096 blocks contains all four train/probe combinations in shuffled order. The trace is saved under `out/` and validated before analysis.

For each measured outcome, the analyzer compares training that matches it against training that differs. It reports medians, paired differences and a within-run bootstrap interval in TSC ticks. A repeated timing difference consistent in both measured outcomes would support further investigation, but does not itself count mispredicted branches. It may include effects from other predictor state, instruction placement, the two return paths, or system noise. Keep a copy of each raw trace and inspect the optimized binary before interpreting the result.

## Balanced branch predictability experiment

Choose **Terminal → Run Task → Balanced branch patterns: build, run, analyze (Windows)**. The current version compares `0011` repeated against a fresh, balanced shuffle in each block. Both patterns contain exactly 4,096 zeroes and 4,096 ones. Each 8,192-call batch reads the same condition address and calls one fixed assembly site from one loop call site for that condition. Input copying, pattern generation and output formatting occur outside the timed interval. A single fenced TSC timer pair surrounds the complete batch. The task selects and prints a new nonzero seed before each run; to reproduce a specific stimulus, invoke `scripts/check_branch_batch_windows.ps1 -Seed <decimal-uint32>` from PowerShell.

Each block measures the two patterns through three sites: the original conditional branch, a second conditional branch that returns the same values **without loading the target byte**, and a branchless input comparator. The sites occupy different code addresses. The branchless comparator always reads the target, whereas the original conditional branch does so only for nonzero inputs; neither control perfectly isolates one hardware mechanism. A separate timer control uses one loop site with a runtime mode to insert `PAUSE` every 128 iterations in the slow class. It checks sensitivity to known extra work, not the isolated cost of `PAUSE`. Inspect the actual Windows binary before drawing an instruction-level conclusion; the earlier version compiled its fast and slow timer paths differently.

Eight samples occur in each of 144 blocks, with balanced positions across each eight-block cycle; eight warm-up blocks precede recording. The trace records each timing and its order, seed, pattern hash, CPU signature, hypervisor bit, Windows build number, branch addresses and executable SHA-256. A matching timestamped EXE is archived alongside each log. Run **Terminal → Run Task → Record Windows host snapshot** once per measurement session to capture the OS version, power plan, processor and firmware metadata in `out/`. Review that inventory before sharing it.

The analyzer reports paired random-minus-periodic contrasts for the loaded branch, no-load branch and branchless comparator, plus within-block interactions. The adjusted 10% trimmed mean is computed on blockwise differences and need not equal the difference between separately trimmed estimates. It resamples complete eight-block cycles for an interval **within one run** and reports split halves. The timer positive control must pass for an interpretable timing result. The loaded-minus-no-load comparison is an ablation at different branch addresses, **not** the isolated cost of loading the target. Timing does not count branch mispredictions or show predictor sharing across privileges. Repeat full runs with independently recorded seeds in more than one session; retain null results and compare run-level estimates rather than pooling all blocks as if sessions were independent.

The [archived two-run Windows baseline](results/2026-10-30-windows-branch-batch/README.md) used the earlier six-condition, fixed-seed trace format. The current analyzer still validates those version 1 logs; version 2 adds the no-load branch and per-run seeds. The original branch-loaded contrast was repeatable in that baseline, but only physical version 2 measurements can evaluate the new control.

The [first physical version 2 pilot](results/2026-10-30-windows-v2-pilot/README.md) includes its raw trace, matched executable, host snapshot, outliers and analysis. Its no-load branch retains the outcome-order timing contrast. It is one run with one seed; inspect the documented limitations and collect the planned independent replications before making a broader claim.

The [six-run version 2 replication](results/2026-10-30-windows-v2-replication/README.md) preserves three runs in each of two same-day sessions with six distinct seeds, matching executables and host snapshots. It reports run-level results, outlier sensitivity and limits on inference across sessions. The outcome-order timing effect persists at the no-target-load branch, but its cause is not identified by timing alone.

## Two follow-up Windows studies

The [study plan and run instructions](WINDOWS_BRANCH_STUDIES.md) describe two new native user-mode controls inspired by the training/probing methodology of the Fractal authors. **Decision source: build, run, analyze (Windows)** uses one branch instruction with a runtime-selected live or fixed-periodic decision stream while retaining the same live input. **Branch history crossover: build, run, analyze (Windows)** compares a fixed short probe after matched or mismatched training, with a branchless sham trainer. Both are separate experiments with independent trace formats, seeds, matching archived EXEs, predefined contrasts and controls. The [physical-host pilots and instruction audit](results/2026-10-30-windows-followup-pilots/README.md) preserve both outcomes: the decision-source interaction passes its predefined controls, while the sham-adjusted history probe is inconclusive. These user-mode timing studies do not test Fractal's privilege switching or reproduce its Apple M1 results.

The [two-day follow-up series](results/2026-10-30-31-windows-followup-replication/README.md) preserves six runs per study on one Windows host, three per study on each of two different dates. The decision-source interaction recurs with all predefined controls passing. The history experiment has a positive sham-adjusted probe-0 contrast in every run but a mixed probe-1 contrast, so it does not establish the planned two-direction crossover. Its report includes raw traces, matched EXEs, snapshots, a manifest, run-level figure and reproducible series analysis.

The [integrated research report](RESEARCH_REPORT.md) consolidates the archived A/B evidence. The [instruction audit appendix](results/2026-10-30-windows-followup-pilots/INSTRUCTION_AUDIT.md) records their optimized bytes. The [complete Windows research program](WINDOWS_RESEARCH_PROGRAM.md) maps what this user-mode host can test, and the [suite protocol](WINDOWS_MULTI_EXPERIMENT_SUITE.md) defines the new B2/C/D/E/F/H/I pilots, controls, and limits. Those new studies have not yet been measured or instruction-audited on the physical workstation.

For one full physical session, choose **Terminal → Run Task → Full branch research pilot: baseline and seven studies (Windows)**. The task records a host snapshot, reruns six existing cache/branch baselines (including the balanced batch, single-branch latency, A and B1), then runs the seven new studies in a preselected order with independent seeds. It preserves each attempted build/run in `out/suite-*/session.json` and continues the other studies if one fails. Actual runtime is unknown and could be substantial. Next choose **Exploratory suite: package latest evidence ZIP (Windows)** to collect the session record, host snapshot, original traces, matched executables, build sidecars, transcripts and available disassembly into one local `out/suite-evidence-*.zip`. Review the host snapshot before sharing. The new physical binaries and timer sensitivity require inspection before interpreting results.

The earlier single-call latency trace on the Windows host contained only values divisible by 47 TSC ticks. Its cause is undetermined. [AMD uProf 5.3 release notes](https://docs.amd.com/r/en-US/63856-uProf-release-notes/6.1.-CPU-Profiling) document that EBP/IBS CPU profiling is disabled when Windows has Hyper-V enabled; interpret the balanced timing experiment within that constraint.

## Linux development check

The same experiment can be built in an x86 Linux environment with a C compiler and Python 3:

```bash
./scripts/check_native.sh
```

The Linux runner writes a raw trace in `out/`. Use `./scripts/record_host.sh` for an inventory of that Linux environment. The separate Fractal build scripts remain in `scripts/` for kernel experiments.
