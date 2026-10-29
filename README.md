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

Choose **Terminal → Run Task → Balanced branch patterns: build, run, analyze (Windows)**. This follow-up compares `0011` repeated against a fresh, deterministically shuffled sequence in each block. Both have exactly 4,096 zeroes and 4,096 ones, so the target executes the same number of times. Each 8,192-call batch reads the same condition address and calls the same assembly branch from one loop site. All input copying, pattern generation, and output formatting occur outside the timed interval. A single timer pair surrounds the complete batch.

Every block also times both patterns through a branchless assembly control, which uses the same input and target addresses but has no conditional jump. It reads the target on every iteration, whereas the branch version reads it on only half; this comparator does not perfectly match memory traffic. A separate positive timer control inserts one `PAUSE` every 128 iterations. Six samples occur in each of 144 blocks, with balanced positions across each set of six blocks. The raw trace records all timings and their order, a deterministic seed, a verified pattern hash, the CPU signature and hypervisor bit, the branch addresses, and the executable's SHA-256 digest. The task saves an EXE with the same timestamp as each log so later builds do not overwrite the measured binary.

The analyzer reports the paired random-minus-periodic timing difference, the corresponding branchless difference, and their interaction after subtracting the branchless difference. The adjusted 10% trimmed mean is computed on each block's interaction and need not equal the difference between separately trimmed branch and branchless estimates. The analyzer resamples complete six-block cycles for a within-run bootstrap interval and reports the two halves separately. It requires a working positive timer control before a timing result can be considered interpretable. A statistically detectable branchless contrast is reported with its magnitude, not used as a post hoc pass/fail threshold. An interaction is **not** a direct count of branch mispredictions, and a zero result cannot establish that predictions did not occur. Run the task multiple times under documented workload conditions and keep every raw trace, including null results.

The earlier single-call latency trace on the Windows host contained only values divisible by 47 TSC ticks. Its cause is undetermined. [AMD uProf 5.3 release notes](https://docs.amd.com/r/en-US/63856-uProf-release-notes/6.1.-CPU-Profiling) document that EBP/IBS CPU profiling is disabled when Windows has Hyper-V enabled; interpret the balanced timing experiment within that constraint.

## Linux development check

The same experiment can be built in an x86 Linux environment with a C compiler and Python 3:

```bash
./scripts/check_native.sh
```

The Linux runner writes a raw trace in `out/`. Use `./scripts/record_host.sh` for an inventory of that Linux environment. The separate Fractal build scripts remain in `scripts/` for kernel experiments.
