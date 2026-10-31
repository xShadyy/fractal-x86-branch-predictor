# Study L: pre-training history preparation on Windows x86

**Status:** the [31 October Windows pilot](results/2026-10-31-windows-suite-pilot/README.md)
built and measured Study L. Four small-work and PAUSE timer pairs passed, but
the fixed-trainer practical-equivalence intervals did not fit inside the
prespecified ±1 tick/probe margin. The study remains **inconclusive** under
its original protocol; the complete raw trace and executable are retained.

The [Fractal paper, §7.1](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
uses 128 constant branches before training or probing its Apple M1 indirect
branch to prepare path history. This study asks a narrower x86 question:
**with an identical short training phase and one-call receiver, does the
earlier prelude sequence change the training/probe latency association?**
It does not assume that any prelude resets x86 predictor state.

## Intervention

One MASM conditional instruction and one noinline C feeder serve every
prelude, real/fixed training call and timed probe. The branch returns the
live byte on both outcomes. A separate branchless sham has a different
address and path, and is a secondary control. The pilot's linked Windows PE
shows a shared conditional site at RVA `0x1c60` for prelude, training and
probe, with small work called inside the timed path. This instruction audit
does not make a failed fixed-trainer control pass.

The prelude always occurs **before** the immediately following 32-call
training phase. Two lengths, 128 and 256 calls, each use four sequences:

| Prelude | Decisions | Counts within either length |
| --- | --- | --- |
| `p4` | Repeated `0011` | Equal zeros and ones |
| `p32` | Sixteen zeroes, sixteen ones, repeated | Equal zeros and ones |
| `c0` | Constant zero | All zero |
| `c1` | Constant one | All one |

The balanced `p4` versus `p32` comparison holds both the number of calls
and the counts of each decision constant while changing their order. The
constant arms directly examine preparation resembling the paper's
constant-branch sequence, but they change the number of zero/one outcomes.
Treat their contrast as a **whole sequence** comparison.

After the prelude, real training makes all 32 decisions equal to label
`t`. Fixed training executes the **same conditional site** but makes
decisions follow `0011` while reading and returning the same all-`t`
live bytes. Sham training reads all-`t` through a separate branchless
site. The same conditional site then receives one measured fixed outcome
`p`. Both `t` and `p` take values 0 and 1.

This is 2 lengths × 4 patterns × 3 trainers × 2 labels × 2 probes =
96 main conditions. Twelve fast/small-work/`PAUSE` timer controls at
`p4` for both lengths and probe outcomes give **108 conditions**. There
are **108 warmup** and **864 recorded randomized complete blocks**, eight
position-balanced 108-block cycles, with **32 episodes per condition**.
Random seed, schedule hash, every block/position/timing total, architectural
checksum, CPU/affinity/hypervisor/build, EXE SHA-256 and source/tool
provenance are recorded. No effect size or positive sign is a pass gate.

## Preselected analysis

For each prelude and each receiver outcome, within a complete block subtract
the matched trainer label from the mismatched label. Subtract the fixed
trainer's difference from the real trainer's difference to form the
adjusted association `F(n,pattern,p)` in TSC ticks per **whole one-call
probe episode**. The primary question is
`F(128,p32,p) - F(128,p4,p)`, reported separately for `p=0` and
`p=1`. Both directions must remain visible, including null or reversed
associations. The 256-minus-128 changes for each pattern and the
`c1`-minus-`c0` comparisons are exploratory secondary outcomes.
Real-minus-sham is reported separately and cannot substitute for the
same-site fixed trainer.

The analyzer pairs inside blocks, applies a declared 10% trim to block
differences and resamples entire 108-block position cycles for within-run
95% intervals. It requires the fixed trainer's mismatch-minus-match
interval to fit within ±1 tick per probe for each cell before calling it
negligible. A result-dependent small-work timer must resolve a few-tick
effect between 1 and 8 ticks per probe with positive interval lower bound;
the separate `PAUSE` wrapper must have a positive lower bound and be
positive in at least 95% of blocks. Those thresholds are **pilot checks**
of this exact optimized binary, not promised hardware instruction costs.
If controls fail, preserve all data and classify the study inconclusive.

## Physical pilot and boundaries

The integrated VS Code suite includes Study L. It is also independently
available through `scripts/check_prelude_sweep_windows.ps1 -Seed <uint32>`.
The script selects and prints a seed before building if omitted. It archives
the timestamped EXE, raw trace, build log/provenance, full executable and
`.text` hashes, and disassembly when available. The pilot's two predeclared
balanced-history interactions were +0.441 [−3.039,+4.247] ticks/probe for
probe 0 and +1.605 [−2.475,+5.968] for probe 1, both within-run intervals
including zero. Its fixed-trainer gate failed; no prelude effect or null was
validated. The test's
short 32-call training itself can overwrite prelude-dependent state, and
prelude pattern also changes the architectural work and branch outcomes.
Fixed and sham trainers reduce, but do not remove, these confounds.

A reproducible association would show sensitivity to this implemented
prelude/training/probe sequence. A null would bound sensitivity of this
receiver and timer. Neither result identifies the path-history-register
length, counts mispredictions, proves transient target execution, or tests
Fractal's M1 privilege/ASID isolation. Independent physical sessions are
needed before interpreting repeatability.
