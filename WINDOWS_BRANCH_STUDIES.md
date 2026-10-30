# Two Fractal-inspired branch studies on Windows

These are two **native user-mode** x86 experiments on the physical Windows host. They extend the [archived six-run branch-pattern series](results/2026-10-30-windows-v2-replication/README.md) with distinct, falsifiable questions. Neither program boots Fractal, changes privilege level, or reproduces a result from Fractal on Apple M1.

## Research connection and limits

Ravichandran and Yan's [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) introduces an operating system for microarchitecture reverse engineering. The authors' S&P artifact (`experiments/utest.c`, `SP_RESULTS.md`) includes conditional-branch training followed by a receiver probe on the same CPU, with user/user and user/kernel configurations. The artifact measures instruction-fetch or data-execution effects using a cache-based endpoint. Its results concern Apple M1. The [upstream source](https://github.com/jprx/fractal) is pinned in [UPSTREAM_FRACTAL_REVISION](UPSTREAM_FRACTAL_REVISION).

Our first new study checks whether the earlier x86 batch contrast depends on the **order of actual branch decisions**, while keeping the input stream and branch address under explicit control. The second asks whether **prior branch outcomes change the latency of an otherwise fixed probe** at one conditional branch instruction. This mirrors the training-then-probing logic at a local, same-domain level. The endpoint here is TSC timing, rather than Fractal's cache observations. A positive result in either study cannot establish cross-privilege predictor sharing, transient access, or a count of mispredictions.

| Study | Intervention | Primary comparison | What would challenge the interpretation |
| --- | --- | --- | --- |
| A: decision source | One branch follows the live input or a fixed `0011` control stream, selected at runtime at the same branch instruction | Difference between the two shuffled-minus-periodic input contrasts | A similar pattern effect when the branch follows only the fixed stream |
| B: history crossover | Train one branch site with all 0 or all 1 before a fixed short probe; compare a branchless sham trainer | Mismatch-minus-match latency after real training, minus the corresponding sham contrast, separately for probe 0 and probe 1 | No directional difference, or a comparable difference after sham training |

## Study A: branch-decision source

`programs/decision_source_windows.asm` has one conditional jump and one common return. It always reads the live input, the periodic control byte, and a runtime mode byte. The mode selects which byte sets the branch outcome; the function always returns the original live input. The same C loop writes both bytes and calls that assembly site in all four primary conditions. Both possible decision streams contain 4,096 zeroes and 4,096 ones per 8,192 calls; the shuffled stream is freshly generated in every block. The fixed mode always follows `0011`, even when the live input is shuffled. No target byte is read at a branch target.

There are eight conditions per block: live decision with periodic/shuffled input, fixed decision with periodic/shuffled input, two branchless input controls, and a fast/slow added-work timer control. The seed is selected before compilation; the first eight blocks are warm-up, followed by 144 randomized complete blocks with balanced condition positions. Copying and pattern generation happen outside the timer. One fenced TSC pair times each 8,192-call batch.

The **primary estimand** is the 10% trimmed mean of the following *blockwise* interaction, divided by 8,192:

```text
[(live shuffled - live periodic) - (fixed shuffled - fixed periodic)] / 8192
```

The analyzer reports the two component contrasts, branchless contrast, medians, split halves, and 95% bootstrap intervals formed by resampling complete eight-block position cycles within the run. Its predeclared practical negative-control tolerance is ±0.5 TSC ticks per iteration: the full within-run intervals of the fixed-mode pattern contrast, branchless pattern contrast, and live-minus-fixed contrast under periodic input must each fit inside that margin. In the last comparison both modes execute the same periodic branch outcomes; it checks for a mode-dependent baseline. The timer control must be positive in at least 95% of blocks with a positive within-run interval lower bound. These checks can mark a run inconclusive; **the primary result is never required to be positive**. Passing the tolerance check does not prove exact equivalence or a predictor mechanism.

## Study B: branch-history crossover

`programs/history_probe_windows.asm` defines one no-target-load conditional branch and a separate branchless sham site. Every episode first runs a balanced `0011` reset through the conditional site, then trains with 256 all-zero or all-one inputs through that site or the sham, then times a fixed 16-call probe through the conditional site. The same noinline C runner and its single in-loop assembly call serve reset, real training, and the probe. Only the probe is inside the fenced TSC interval. Each recorded condition sums 128 such episode durations to reduce sensitivity to the observed coarse TSC lattice. The sham controls for input values and preceding work imperfectly because it executes a different training site.

Each complete block contains the four real-trainer train/probe combinations, four sham-trainer combinations, and a fast/slow probe timer pair. Conditions are randomized and position-balanced in ten-block cycles. Ten warm-up blocks precede 320 recorded blocks, giving 32 complete position cycles. The analyzer checks the exact seed-derived schedule, all sample/checksum records, metadata and controls, then reports 10% trimmed paired-block estimates and within-run bootstrap intervals over complete position cycles.

For **probe 0**, training 1 is the mismatch and training 0 the match; for **probe 1**, training 0 is the mismatch and training 1 the match. The two primary comparisons subtract the corresponding sham mismatch-minus-match difference **within each block**. They are reported separately in TSC ticks per fixed 16-call probe, averaged over 128 episodes. These units are not directly comparable with Study A's ticks per 8,192-call iteration. A simple pooled average of the two outcomes is not a substitute for seeing both signs separately. The timer positive control uses a separate slow wrapper with one unconditional `PAUSE` in each short timed probe. The primary probe wrapper contains no timer-control branch. This added-work check does not measure an isolated `PAUSE` cost or establish sensitivity to every possible small history effect.

The probe can itself retrain the branch during its 16 calls. Reset, training and sham loops can also leave different global history or cache/power states. A null result with valid controls limits this particular timing probe's sensitivity; a positive result supports a local history-dependent latency effect but is not a direct predictor-miss event measurement.

## Before drawing conclusions

The Windows build scripts archive an EXE beside every timestamped raw trace and record its SHA-256, seed, CPU signature, hypervisor bit, Windows build and branch addresses. The optimized EXEs must be inspected after the first physical pilot to confirm one intended branch instruction and one in-loop call site per study. This check cannot be completed by Python tests in this Linux workspace. Inspect both the program output and the raw files. Keep failed-control or null runs rather than deleting them.

The pilots establish compilation, instruction identity, functioning controls and approximate sensitivity. After auditing the pilot binaries, freeze a measurement revision and repeat complete runs with distinct automatically recorded seeds. Aim for at least three runs in each of two sessions on different days if the pilots justify replication. Capture a host snapshot in every session, retain all run-level estimates, and compare sessions without treating individual blocks from different runs as independent sessions. The fixed parameters and analysis rules above were written before observing any physical data from these new studies; pilot-driven changes should be versioned and documented before replication.

## Run in the existing VS Code repository

Prerequisites are the same as for the validated Windows branch-batch task: MSVC x64 Build Tools, Python 3, and PowerShell. No new repository or OS boot is involved.

1. Import the accompanying bundle into the existing checkout. Confirm `git status --short` is empty and note the commit from `git log -1 --oneline`.
2. In VS Code choose **Terminal → Run Task → Record Windows host snapshot** once for the pilot session.
3. Choose **Terminal → Run Task → Decision source: build, run, analyze (Windows)** once.
4. Choose **Terminal → Run Task → Branch history crossover: build, run, analyze (Windows)** once.
5. Preserve the timestamped `out/decision-source-windows-*.log` and matching `.exe`, `out/history-probe-windows-*.log` and matching `.exe`, and `out/host-windows-*.json`. Share those five files and the two terminal outputs for instruction-level and statistical review. The generic EXE names in `out/` are overwritten by the next build.

The tasks choose independent nonzero seeds before each build. To replay a recorded stimulus, run `./scripts/check_decision_source_windows.ps1 -Seed <decimal-uint32>` or `./scripts/check_history_probe_windows.ps1 -Seed <decimal-uint32>` from PowerShell in the repository root. The tasks print a control verdict and archive the raw trace before an inconclusive result returns a nonzero exit code. If a task fails during assembly or compilation, keep and share its full terminal output; a new binary or validated run has not yet been established in that case.
