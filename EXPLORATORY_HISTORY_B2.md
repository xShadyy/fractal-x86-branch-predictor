# Proposed B2 history-probe pilot: probe length and same-site control

**Status:** the [31 October physical pilot](results/2026-10-31-windows-suite-pilot/README.md) built and measured B2. The linked PE includes its shared branch and small-work instructions, but the probe-1 one-call timer missed the declared magnitude gate, so the pilot is **inconclusive** as a whole. Its probe-0 one-call contrast remains exploratory. Keep it separate from the frozen [B1 protocol](WINDOWS_BRANCH_STUDIES.md) and [B1 two-day archive](results/2026-10-30-31-windows-followup-replication/README.md); their estimates and intervals must not be pooled.

## Question and prior observation

B1 timed 16 consecutive calls to one conditional branch after 256 calls of all-zero or all-one training. Its sham-adjusted probe-0 mismatch-minus-match contrast was positive in all six replicated runs, approximately +2.05 to +4.47 TSC ticks **per 16-call probe**. Probe 1 changed sign between runs, and all six within-run intervals included zero. B1's branchless sham used a different training address, and the first probe call could change the branch state seen by the next 15 calls. B2 asks whether the one-sided contrast appears on a **single-call probe** and whether it survives a control that executes the same conditional branch with fixed decisions during training.

The [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) first develops a same-domain branch train/receiver test before varying privilege and address-space domains. B2 stays within one native Windows user-mode process and observes TSC latency rather than the paper's cache receiver. Its results cannot establish speculative fetch or execution, privilege-domain sharing, or a branch-misprediction count.

## Intervention and instruction identity

Every episode starts with the same balanced 256-call `0011` prelude at the conditional site, then 256 training calls, then one timed fixed-outcome probe of length `n ∈ {1, 16}` at that site. The prelude standardizes prior activity; it does not prove predictor state is erased. The train input label `t ∈ {0, 1}` sets all 256 live training bytes. The probe outcome `p ∈ {0, 1}` sets every probe byte to the same value.

Three training arms use the same live bytes and retain their architectural outputs:

| Arm | Training decisions | Purpose |
| --- | --- | --- |
| `real` | The conditional jump follows the all-`t` live bytes. | Intervention whose history effect is questioned. |
| `fixed` | The **same conditional jump** follows `0011`, selected at runtime without a data-dependent choice branch, while it still reads and returns the all-`t` live bytes. | Holds training-site instruction address, number of calls, and live input values while changing the branch-decision stream. It does not create a predictor-free baseline. |
| `sham` | A separate branchless site reads and returns the all-`t` bytes. | Preserves a comparison with B1; its different address and call path remain limitations. |

The pilot assembly function for `real` and `fixed` must always load both the live and periodic bytes, select the decision byte with a branchless operation such as `cmov`, execute one conditional jump, and return the live byte through a common return path. A single direct call instruction inside the C branch runner must serve the prelude, real/fixed training and both probe lengths. The branchless sham has its own site. All primary arms use the same fenced TSC wrapper for the probe, with the probe length passed as a count; training, input preparation and output formatting remain outside that interval. The mode and fixed stream must be set before the timed probe, and the probe always selects live decisions. These are intended properties to confirm in the **physical Windows EXE disassembly**, not assumptions established by source or Linux tests.

## Complete condition set and schedule

For each probe length, the twelve real/fixed/sham conditions below cover both train labels and both probe outcomes. Each of the three timer conditions also covers **both probe outcomes** at each length. The table shows conceptual labels; an implemented trace must use stable, explicitly enumerated names.

| Arm | Train label | Probe outcome | Probe lengths | Conditions |
| --- | --- | --- | --- | ---: |
| Real conditional | 0 and 1 | 0 and 1 | 1 and 16 | 8 |
| Same-site fixed `0011` | 0 and 1 | 0 and 1 | 1 and 16 | 8 |
| Branchless sham | 0 and 1 | 0 and 1 | 1 and 16 | 8 |
| Timer fast after real train 0 | 0 | 0 and 1 | 1 and 16 | 4 |
| Timer small added work after real train 0 | 0 | 0 and 1 | 1 and 16 | 4 |
| Timer `PAUSE` added work after real train 0 | 0 | 0 and 1 | 1 and 16 | 4 |
| **Total** | | | | **36** |

Use **128 episodes per condition**, **36 warm-up blocks** and **720 recorded complete blocks**. Each recorded block contains all 36 conditions in a seed-derived shuffled order. Generate one base permutation per 36-block cycle, then rotate its positions so every condition occupies each position once per cycle. This gives **20 complete position cycles**. The seed is a nonzero 32-bit value chosen and printed before compilation. The trace must contain run dimensions, `n`, `t`, `p`, arm, block and position, exact schedule/pattern hashes, all raw summed TSC durations, an architectural-result checksum, addresses, CPU signature, logical CPU affinity, hypervisor bit, Windows build, UTC start, and the SHA-256 of the timestamped EXE actually launched. The session record must also include Git HEAD and dirty status, source/assembly/analyzer SHA-256 hashes, exact `cl`, `ml64` and linker paths and version strings, full build flags, and a ledger of failed builds and runs. Label unknown microcode and mitigation state as unknown. Keep failed-control and null traces. The **3,317,760 recorded episodes** entail **1,726,894,080 prelude/training/probe calls** (approximately 1.727 billion); warm-up adds approximately 86.3 million. Actual runtime must be measured in the pilot rather than assumed.

## Estimands, units and uncertainty

Let `Y(a,t,p,n)` denote one block's sum of the 128 episode durations for trainer arm `a`. For probe 0, mismatch is training 1 and match is training 0. For probe 1, mismatch is training 0 and match is training 1. Form every contrast **inside each block before trimming**:

```text
D_a(0,n) = [Y(a,1,0,n) - Y(a,0,0,n)] / 128
D_a(1,n) = [Y(a,0,1,n) - Y(a,1,1,n)] / 128
F(p,n)   = D_real(p,n) - D_fixed(p,n)
S(p,n)   = D_real(p,n) - D_sham(p,n)
```

The four `F(p,n)` contrasts, separately for `p=0,1` and `n=1,16`, are **planned exploratory outcomes and must all be reported**. One interval excluding zero among the four is not a confirmatory discovery or a frozen B2 mechanism claim. The four `S(p,n)` contrasts are secondary triangulation with B1's branchless sham. Report the underlying `D_real`, `D_fixed` and `D_sham` as well. Apply the predeclared 10% trimmed mean to each blockwise contrast and resample complete 36-block cycles for within-run 95% bootstrap intervals. Report paired medians, first/second halves and an explicitly exploratory 20% trim without replacing the primary estimator. A positive result is not a prerequisite for a valid trace.

Every `F` and `S` estimate is in **TSC ticks per complete probe episode**, not ticks per call. For `n=1` an episode contains one timed call; for `n=16` it contains 16 timed calls. Report both the total `F(p,16)` and descriptive `F(p,16)/16`, but do not treat the 16 calls as independent samples. Form the exploratory length interaction `F(p,1) - F(p,16)` **within each block before trimming**, then report its 10% trimmed mean and whole-cycle within-run interval. Do not subtract two separately trimmed point estimates and call that the paired interaction. No sign is predetermined. A similar *total* contrast at lengths 1 and 16 would be consistent with an early-call effect, while a larger total at 16 could reflect later calls; neither pattern proves how hardware state evolved or implies automatic first-call dilution. Probe length also changes loop work, so comparisons across lengths are diagnostics, not an isolated first-call cost.

## Controls and interpretation gates

1. **Structure and provenance:** the optimized Windows EXE must have the intended single conditional jump, branchless mode selection, one in-loop direct callsite for real/fixed/probe, the separate branchless sham, and identical primary timed wrapper across arms. Archive its SHA-256 and `.text` hash. If compilation, disassembly, seed replay, checksum, EXE pairing or architectural-output checks fail, preserve the files but do not interpret the timing contrasts.
2. **Coarse timer control:** a separate wrapper adds one unconditional `PAUSE` after the same probe. Compare `PAUSE` to fast within **each length and probe outcome**. Require a positive 95% within-run cycle-bootstrap lower bound and at least 95% positive paired blocks for each pair. This checks that known substantial extra work is detectable; it does not certify sensitivity at the observed 2 to 4 tick scale.
3. **Small timer control:** a second separate wrapper adds a short, result-dependent integer operation chain after the same probe, with the output consumed so compilation cannot remove it. Its exact instructions and measured cost must be audited in the first physical B2 pilot. Before using a positive B2 result as evidence at the few-tick scale, require for **each length and probe outcome** a positive 95% within-run cycle-bootstrap lower bound, an upper bound below **+8 ticks per probe**, and a point estimate in **[+1,+8] ticks per probe**. Report the positive-block sign fraction descriptively, with no sign-fraction pass threshold for this small control. If the calibration range is not achieved, report the pilot and version any changes before a confirmatory run. No instruction cost is presumed from source code alone.
4. **Same-site fixed control:** the fixed arm's mismatch-minus-match `D_fixed(p,n)` should have its full within-run interval inside a predeclared practical tolerance of **±1 tick per probe** for each outcome and length before describing that control as negligibly affected by live train bytes. Failure does not invalidate the trace; it prevents a clean decision-stream interpretation. The sham is reported independently and is never assumed equivalent to zero.

The small control itself may alter register dependencies and the separate sham has a different training site. Both are controls with limited scope. If the branch-mode selection, timed wrappers or small-work code do not compile as intended, revise the version and re-audit before collecting a new physical run. Do not silently change the n=1/n=16 choice, control thresholds or exclusions after inspecting outcomes.

## Falsifiable readings and next decision

| Pilot observation | What it would challenge or support |
| --- | --- |
| `D_fixed(0,n)` resembles `D_real(0,n)`, or its interval exceeds the ±1 margin. | Live train bytes, common-loop work or the mode baseline could account for part of B1's one-sided contrast. |
| `F(0,1)` is near zero despite adequate few-tick timer sensitivity, while `F(0,16)` is positive. | The simple claim that B1's probe-0 difference is concentrated in its first call is challenged. |
| `F(0,1)` is positive and `F(0,16)/16` is much smaller, with controls passing. | Consistent with concentration near the beginning of the probe, but also compatible with other evolving execution states. |
| Probe-1 `F(1,1)` and `F(1,16)` remain mixed. | The anticipated bidirectional history pattern remains unsupported. |
| `S` differs materially from `F` at the same outcome and length. | The choice of sham or its different training site matters and needs a further controlled ablation. |

This pilot is intended to identify a defensible next comparison. Once its binary, control sensitivity and outcome pattern are inspected, document any changes, select **one** probe length, outcome and primary comparator in a **new frozen confirmatory protocol**, and repeat with independent seeds on different days. Do not count blocks as independent day-level observations. A positive latency contrast alone still cannot count mispredictions, identify a unique predictor mechanism, or make a claim about user/kernel isolation. AMD's [uProf release notes](https://docs.amd.com/r/en-US/63856-uProf-release-notes/6.1.-CPU-Profiling) state that EBP/IBS profiling is disabled on Windows when Hyper-V is enabled; the current host snapshots report a present hypervisor. No profiler or boot change is required by this proposal.
