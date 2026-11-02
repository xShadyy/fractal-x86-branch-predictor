# B2 v3: prospective adjacent-pair precision diagnostic

**Status:** apparatus diagnostic to run on the physical Windows workstation.
The completed [v2 pilot](../RESEARCH_REPORT.md)
has ZIP SHA-256
`9c71dca5d33c1751bfedcf759aa9eb5e5789b53a40ce8b8e437da449c840abce`.
Its three 16-call baseline gates failed and its selected candidate was null.
That result remains in the attempt ledger, with no change to its trace or
original thresholds. The exploratory v2 observation that widely separated
conditions had larger timing differences motivates this new schedule, but
does not establish temporal drift or interruption as the cause. We also
increase the predetermined episode and block counts; this design cannot
isolate the effect of closer pairing from the effect of sample size.

## Frozen scope

This program calibrates measurement precision **within one Windows user
process**. It trains the live assembly branch with `t=0` for the timer
conditions and compares fixed-decision `t=0/1` training for neutral controls.
It does not collect the real-arm `t=1` versus `t=0` outcome contrast, switch
privilege, use a speculative receiver, or assess the Fractal paper's hardware
claims. The `dose4` wrapper was chosen for this diagnostic after the v2
pilot. V3 cannot count as independent validation of a B2 outcome.

For each `p ∈ {0,1}` and `n ∈ {1,16}`, four adjacent condition pairs are
measured: identical `fast_a/fast_b` timer paths, `fast_c/dose4` small-work
paths, `fast_d/pause` coarse timer paths, and `fixed_t0/fixed_t1` trainers.
That is 16 pairs, 32 conditions in each complete block. Pair members have
the same prelude, training length and probe length; the fixed trainer's
decision stream stays periodic while its live value changes with `t`.
Every condition uses 256 calls for the 0011 prelude, 256 training calls, and
then `n` live probe calls at the same assembly branch address. Each recorded
condition total aggregates 256 episodes. Only the probe and its timer wrapper
are inside the fenced `RDTSC` interval. The optimized physical instructions
must be checked in the archived executable.

Preselect one nonzero uint32 seed. After 32 warm-up blocks, record **2,560**
complete blocks, 80 position-balanced 32-block cycles. Shuffle pair order
and orientation from the seed at each cycle, rotate the 16 pair slots over
the first 16 blocks, and invert within-pair orientation for the next 16.
Each condition occupies every one of 32 positions once per cycle. The
analyzer replays the seed through warm-up and recording, validates all 81,920
sample identities/positions and checks the schedule hash, prelude and fixed
pattern hash, architectural sums, trace checksum, and metadata before
analysis. No adaptive stopping or optional exclusion of blocks is allowed.

## Predeclared controls and analysis

Within each block and each `p,n` stratum, compute these paired differences
then divide by 256 episodes. The unit is TSC ticks per complete probe
episode, including all `n` calls, **not** ticks per branch call. Use a
10%-trimmed mean as the point estimate and 2,000 whole-32-block-cycle
bootstrap resamples for a within-run 95% interval. Report the paired median,
first/second half estimates, 20%-trimmed descriptive sensitivity estimate,
positive block fraction, and observed timer GCD without using any of them
to replace the frozen gates.

| Difference | Gate, in ticks per probe episode |
| --- | --- |
| `fast_b - fast_a` | Entire 95% interval strictly within `(-1,+1)` in all four strata. |
| `fixed_t(1-p) - fixed_t(p)` | Entire 95% interval strictly within `(-1,+1)` in all four strata. |
| `dose4 - fast_c` | Interval lower bound `>0`, upper bound `<8`, and 10%-trimmed point in `[1,8]` in all four strata. |
| `pause - fast_d` | Interval lower bound `>0` and at least 95% positive blocks in all four strata. |

All sixteen gates must pass. A gate failure is an **inconclusive precision
diagnostic**, even if another stratum or timer control passes. A successful
run establishes that this paired apparatus met its specified controls on
one host at that time. It does not retroactively validate v2 or establish a
branch predictor mechanism. Inspect the archived linked instruction paths
and plan a separately frozen independent B2 outcome study before making
any mechanism claim.

## One Windows run from VS Code

1. Merge the source revision in the existing repository. Start from a clean
   Git working tree. Select **Terminal → Run Task → B2 v3 paired precision
   diagnostic (Windows)**. The task builds with MSVC and `ml64`, chooses and
   records the seed, runs the physical executable and analyzer, and may take
   several minutes. Do not run the older Focus or B2 v2 task for this step.
2. Upload the one `out\b2-precision-windows-<UTC timestamp>.zip` printed
   after `READY TO SHARE:`, whether the controls pass or are inconclusive.
   An inconclusive gate intentionally exits nonzero but preserves the entire
   trace. If a build, run, or trace parse fails, share the separately labeled
   `Diagnostic evidence ZIP (partial)` for debugging.

The flat ZIP includes the exact timestamped EXE and raw trace, build log and
provenance JSON, PE disassembly, analysis JSON, strict analyzer output and
SHA-256 manifest. The provenance records a clean Git HEAD, hashes of direct
and imported source, exact compiler flags and tool versions, executable and
PE `.text` hashes, run seed and separate collection/control statuses. An
internal hash match checks archive consistency, not hardware authenticity.
