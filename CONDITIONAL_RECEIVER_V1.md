# K1: same-process conditional target-data receiver

**Status:** source and analysis protocol frozen before the first physical
Windows run. The first physical K1 pilot is now recorded separately in the
[pilot result](results/2026-11-01-windows-conditional-receiver-pilot/README.md):
its executable built and the linked path was audited, but both held-out
architectural-skip gates failed. Retain the original K1 rules and preserve
every null, failed-control and build attempt.

## Question and scope

Does training one conditional branch toward target 0 or target 1 change the
subsequent cache-reload rate of the **architecturally unselected** target data
line, for a fixed probe choice? The branch and both target bodies occupy one
Windows user process on an x86-64 host. Both branch outcomes are tested.
This is an x86 adaptation of the progression in Ravichandran and Yan's
[*Fractal* paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf):
establish a working target-specific same-domain receiver before attempting
separate senders or security-domain changes. The paper's Apple M1 test used
a different branch layout and controlled scheduler. K1 does not boot Fractal
or test a privilege boundary, ASID, instruction-cache fetch or Phantom.

The K1 branch site reads a condition byte, conditionally selects one of two
code bodies, and loads data from one of two separate 4 KiB target arrays.
The bodies are separated by at least 128 NOP bytes; the data lines are page
separated. The same assembly branch site is invoked by a standardized `0011`
prelude, 256 constant-outcome training calls, and the observed probe. The
prelude standardizes recent activity but is not a verified predictor reset.
For probe outcome `p`, the receiver reloads the data line for `1-p`, which
the correctly executed branch never loads. The condition line and both target
lines are flushed **after training** and before the optional probe, and no
probe-byte store is performed after the flush. This cold condition load is
intended to delay branch resolution; only a physical PE audit can establish
the actual linked instruction path.

## Frozen design

For each `p ∈ {0,1}` there are eight cells in every complete block:

| Cell | Training | Probe after flush | Opposite-line receiver purpose |
| --- | --- | --- | --- |
| `candidate_t0_p`, `candidate_t1_p` | Real branch, 256 constant 0 or 1 decisions | Branch choice `p` | Candidate train-label contrast; match is `t=p`, mismatch is `t=1-p`. |
| `no_probe_t0_p`, `no_probe_t1_p` | Exactly matched real training | Omitted | Residual heat or harness effect tied to training label. |
| `hot_p`, `cold_p` | Fixed balanced 0011 train | Omitted; hot touches opposite data line after flush | Establish receiver threshold from the first half and held-out sensitivity. |
| `arch_load_p`, `arch_skip_p` | Train `p` at the same branch site | Branch choice `1-p` or `p` | Validate that the exact branch path loads or does not load the measured data line architecturally. |

One execution collects 512 randomized complete blocks of 16 conditions
after 16 warm-up blocks, with 64 repeated flush/probe/reload episodes per
condition and a new nonzero uint32 seed chosen **before** building/running.
One Fisher–Yates permutation is drawn per 16-block cycle. A rotation puts
each condition once in each temporal position across the cycle. The analyzer
replays the seed, warm-up, sample order, balanced positions, FNV schedule
hash, checksum, architectural return totals, metadata and executable hash.
No adaptive replacement of blocks or rerun to rescue a null is permitted.

## Receiver calibration and analysis

For `p0` and `p1` **separately**, choose a reload-time threshold from only
the first 256 complete blocks' `hot_p` and `cold_p` samples. All outcome
estimates and control gates use the held-out last 256 blocks. A lower reload
time is called a hit. The apparatus is eligible only when, for both `p`:

1. Held-out hot hit rate ≥95% and cold hit rate ≤5%.
2. Held-out same-branch `arch_load` hit rate ≥95% and `arch_skip` ≤5%.
3. Each held-out no-probe t0 and t1 hit rate ≤5%, guarding against residual
   training heat on the line selected by the receiver.

The **one preselected primary** is probe 0's paired, blockwise hit-rate
difference:

```text
adjusted_p0 = (candidate_t1_p0 − candidate_t0_p0)
              − (no_probe_t1_p0 − no_probe_t0_p0)
```

The p1 mirror, with mismatch t0 and match t1, is secondary. Each block's
rate uses its 64 episodes. Report both candidate and no-probe components,
the adjusted point, split halves, and a 95% **within-run** bootstrap interval
resampling entire 16-block cycles. The point uses the mean of the paired
held-out block differences. The analyzer's strict exit fails only for an
invalid trace or failed receiver gate; a null result is a valid experiment.
If gates pass and the entire primary interval is above **+5 percentage
points**, describe a **candidate target-line association within this run**.
The +5-point practical margin is frozen before the first physical run and
matches the maximum cold/no-probe hit-rate allowance; a smaller interval
above zero remains descriptive rather than a candidate classification.
This rule does not infer misprediction counts, transient execution, or a
security boundary. An interval including zero is an eligible null at this
receiver sensitivity. A failed gate makes the candidate comparison
inconclusive. The secondary direction is descriptive, with no
multiple-testing-adjusted claim.

The target-1 body is adjacent to the branch fallthrough, while target 0 is
past a NOP gap; their dispatch/fetch context differs, so symmetry between
p0 and p1 is not assumed. The episodes share predictor state and host
conditions and are not independent host replications. Even a
positive association can arise from cache-line overlap, residual training
heat, prefetch, branch-path work, interrupted timing, compiler changes,
or other mechanisms. Linked executable and actual runtime addresses are
mandatory evidence. CLFLUSH plus reload does not identify which cache level
contains a line. Within-run intervals do not quantify variation between
independent executions, days, processors or host configurations.

## Windows run and evidence

From a clean checkout on the physical workstation, choose **Terminal → Run
Task → K1 conditional target-data receiver (Windows)** in VS Code. It builds
with MSVC and MASM, archives the exact executable, raw per-episode trace,
linked disassembly, build provenance, analyzer output and hashes, then
prints **READY TO SHARE** with one `out\conditional-receiver-windows-*.zip`.
Share that ZIP even when controls fail or the candidate effect is null. If
the build or trace parser fails, share its marked partial diagnostic ZIP.

Before any physical interpretation, inspect the linked PE for the one
conditional branch and a single shared call site, the exclusive loads from
the two page-separated data lines, the absence of a C/harness load of the
opposite line after flush, the order of CLFLUSH/MFENCE before probe, and the
fenced TSC reload. Confirm that the logged branch and target code addresses
map to those bytes and the two target bodies do not share a 64-byte code line.
The source, unit tests, and synthetic traces alone cannot certify this.
