# B2 v2: same-process timer calibration pilot

**Status:** prospective apparatus pilot. The six earlier B2 Focus traces failed
their original control gates and remain inconclusive. This separately versioned
pilot checks whether a revised timed wrapper is both detectable and small
enough to study later. It contains no real training-arm outcome, cannot repair
or pool with the earlier B2 traces, and is not evidence for Fractal's
cross-privilege or predictor-sharing claims.

## Frozen design

Use one native x64 Windows executable built from
`programs/b2_calibration_windows.c`, `programs/history_b2_windows.asm`, and
`programs/cpu_features.c`. The x64 assembly provides the same conditional
branch site for the prelude, training, and probe. Verify that physical topology
in the archived linked disassembly before interpreting any candidate. The
process pins one allowed logical CPU and requires invariant TSC. A reported
hypervisor is retained in metadata.

There are 32 conditions in each randomized complete block: six timed wrappers
(`fast_a`, `fast_b`, `oldsmall`, `dose4`, `dose8`, `pause`) for every
`p ∈ {0,1}` and `n ∈ {1,16}`, plus `fixed_t0` and `fixed_t1` for every
`p,n`. `fast_a` and `fast_b` invoke **the identical timed function**, providing
a label/placebo check. The `dose4` and `dose8` labels specify four or eight
serial source-dependent operations after the branch work, rather than a fixed
number of machine instructions or cycles. The prelude uses 256 calls; training
uses 256 calls; each condition aggregates 128 episodes. The 24 wrapper
conditions train the live branch with `t=0` only. The eight fixed conditions
use `t=0/1` live values while training follows a fixed periodic branch
decision stream. Every probe follows its live value. No condition trains a
real `t=1` decision path and measures its difference from a real `t=0` path.

One nonzero 32-bit seed generates 32 warm-up blocks followed by 1,280 recorded
blocks. Every recorded block contains each condition once; seeded Fisher–Yates
order followed by 32-position rotation balances positions. The raw trace
contains all 40,960 condition totals, seed, schedule and pattern hashes,
architectural output totals, the executable hash, and the pinned CPU. The
sidecar build JSON records source and toolchain provenance. The analyzer
replays and validates the trace before computing any contrast.

For each stratum `p,n`, subtract the `fast_a` total in the **same block** from
each wrapper total and divide the blockwise difference by 128 episodes.
`fixed_neutral` compares `fixed_t(1-p)` with `fixed_t(p)` within the same block
and length. Report the 10%-trimmed mean, paired median, first and second half,
20%-trimmed sensitivity estimate, positive-block fraction, and two-sided 95%
within-run bootstrap interval. Bootstrap resamples the complete 32-block
rotation cycles 2,000 times. Intervals describe this run conditional on its
hardware and environment; blocks are not independent host replications.

## Predetermined calibration gates

The following apply separately to **all four** `p,n` strata. Bounds are in
TSC ticks per episode's probe and are strict where indicated.

| Check | Required gate |
| --- | --- |
| `fast_b - fast_a` placebo | Entire 95% interval strictly inside `(-1,+1)`. |
| `pause - fast_a` timer control | Interval lower bound above `0`; difference positive in at least 95% of blocks. |
| `fixed_t(1-p) - fixed_t(p)` neutral comparator | Entire 95% interval strictly inside `(-1,+1)`. |
| One eligible candidate (`dose4` or `dose8`) minus `fast_a` | Interval lower bound above `0`, upper bound below `8`, and 10%-trimmed point estimate in `[1,8]`. |

All placebo, timer, and neutral gates must pass. Then select the **first**
candidate meeting its gate in all four strata, in the frozen priority order
`dose4`, `dose8`. The original `oldsmall` wrapper remains a reported diagnostic
and is ineligible for selection because its corresponding earlier B2 control
failed; its source similarity does not guarantee identical compiled code. Its
positive-small-work gate uses the same bounds as the eligible candidates but
does not determine the selected wrapper.
Otherwise set `selected_candidate` to null and
`calibration_controls_pass` to false. A null candidate is an informative
apparatus result, never a license to relax these bounds or choose a favorite
stratum. The observed GCD of timed totals and the sensitivity estimates are
reported even when gates fail; quantization can affect resolution.

Passing this pilot selects a wrapper to predeclare in a **new, independently
collected validation**. Selection on these measurements cannot itself count
as independent validation. Only after the control and linked-instruction
audit should a separately frozen real-arm B2 study be considered. Timing
alone does not count branch mispredictions or identify predictor state.

## Run once from VS Code on the Windows host

1. Merge the source revision and start from a clean Git working tree. Select
   **Terminal → Run Task → B2 v2 calibration-only pilot (Windows)**. This task
   is standalone; the old Focus suite and old `History B2` task are separate.
2. Let the runner finish. A completed trace prints `READY TO SHARE:` and an
   absolute `out\b2-calibration-windows-<UTC timestamp>.zip` path. Upload that
   **one ZIP** for inspection, whether the control gates pass or remain
   inconclusive. An inconclusive strict check intentionally sets a nonzero task
   exit code while retaining the full trace and archive.
3. If build, runtime, or raw trace validation fails, the runner prints a
   `Diagnostic evidence ZIP (partial)` path instead. Share that archive to
   debug; it is not a completed measurement.

The flat archive contains the exact timestamped `.exe`, raw `.log`, build
`.log` and `.json`, linked `.disasm.txt`, analyzer `.analysis.json` and strict
output `.strict.log` when available, plus a `.manifest.json` with SHA-256 hashes
of every included evidence file. The build JSON records seed, Git HEAD and
clean-tree state, hashes of direct and imported source files, compiler tool
versions, executable and `.text` hashes, and separate collection and control
statuses. The ZIP remains useful when the gates fail. Keep all failed attempts
and do not substitute another build for the archived executable.
