# K2: condition-entry and scheduling diagnostic for a conditional receiver

**Pre-physical protocol, version 1.** K2 is a new, pilot-informed experiment.
The [K1 physical pilot](results/2026-11-01-windows-conditional-receiver-pilot/README.md)
was inconclusive because both architectural-skip hit rates exceeded its frozen
5% gate. Its first five episodes per condition showed an exploratory spike.
K2 does not remove those K1 episodes, relax K1's gate, or pool K1 with K2.
This document fixes K2's question, cells, controls and interpretation before
the first K2 Windows measurement.

## Question

Does an opposite-target cache-hit spike recur near entry into a group of
repeated conditional probes, and does it depend on scheduling the same
conditions in groups versus interleaving them? The additional separated HOT
control path tests whether K1's collector layout was a plausible contaminant,
but any difference from K1 will also include other code-layout changes.
K2 is a same-process Windows user-mode diagnostic on the Ryzen host. It does
not test Fractal OS, privileged code, ASIDs, M1, or a Phantom branch.

## Fixed collector and allocation

Reuse K1's one MASM conditional branch site and two target bodies, with
page-separated target data and condition lines. Both branch outcomes return
different values to verify the architectural path. For every observed
episode, run the same `0011` 128-call prelude and 256-call constant trainer,
set the probe condition, flush both target data lines and then the condition
line, execute `MFENCE`, optionally invoke the branch, and reload the
architecturally unselected target data line with a fenced TSC timer. The HOT
positive control touches that line after the flush in a separate noinline
function; the candidate/skip path must not have an architectural HOT touch.
Inspect the *linked executable* for this property and for any post-flush
speculative contamination path before interpreting physical data.

For each probe choice `p ∈ {0,1}`, use the same eight cells as K1: training
label 0 or 1 with probe `p` (`candidate_t0`, `candidate_t1`), the matched
training labels with probe omitted (`no_probe_t0`, `no_probe_t1`), calibrated
HOT and COLD without a branch probe, and same-site `arch_load`/`arch_skip`.
The latter train toward `p`, then respectively select or skip the measured
opposite target. `arch_skip` is an **outcome in K2**, since its excess hit
rate is precisely the phenomenon under investigation.

Every recorded macroblock contains both schedule modes and every one of the
16 cells, with **64 complete episodes per cell per mode**:

| Mode | Within-mode execution |
| --- | --- |
| Grouped | Run all 64 episodes of one cell, then advance to the next cell. |
| Interleaved | Run one episode of each cell in order, repeated for 64 rounds. |

Use 16 warm-up macroblocks, then 128 recorded macroblocks. Preselect one
nonzero 32-bit seed before the build. A continuing xorshift state supplies a
Fisher–Yates condition permutation at each 16-block cycle boundary,
including warm-up; rotate the base order by `block % 16`. The first mode is
`(block + (seed & 1)) & 1`, with the other mode second, balancing mode order
within every cycle. Log the seed, each sample's block/mode/cell/position,
all 64 occurrence timings and an FNV hash replaying every actual episode's
mode, kind and occurrence index in execution order. The trace also records
an episode checksum and the expected prelude, training and probe return
totals so the analyzer can detect missing rows or wrong architectural paths.
No blocks or early episodes may be dropped because of their outcome. Record
the exact binary hash, source revision, compiler versions, CPU metadata,
affinity, executable and linked disassembly in the evidence ZIP.

## Calibration and gates

Use only the first 64 recorded macroblocks to choose four reload thresholds,
one for each `(mode, p)` from its HOT and COLD distributions. Use the final
64 blocks for every outcome and gate. A lower reload time than or equal to
the threshold is a hit. For each mode and probe choice, require held-out
HOT ≥95%, COLD ≤5%, same-branch architectural LOAD ≥95%, and each of the
two training-matched NO-PROBE cells ≤5%. These are 20 apparatus gates in
total. Do not gate on `arch_skip`, since it is a measured K2 outcome.
An invalid trace or failed apparatus gate withholds K2 classification while
retaining its raw and descriptive results.

## Frozen comparisons and decision

For each held-out macroblock, compute the grouped `arch_skip_p0` hit rate
for occurrence indices **0–4** and **5–63**. Their *within-block difference*
is K2's sole primary endpoint, in percentage points. Its point estimate is
the average of 64 held-out block differences. Report a 95% **within-run**
bootstrap interval resampling complete 16-block position cycles. If all
apparatus gates pass and the entire interval is above **+10 percentage
points**, classify the outcome as a recurrence of a practically large
condition-entry association under the new harness. Otherwise report the
point and interval without claiming a recurrence. This margin is fixed
based on the large K1 pilot spike and is not a threshold for speculation.

Prespecified secondary descriptive contrasts are the same early-minus-late
rate for p1, both p choices in the interleaved mode, and the paired
grouped-minus-interleaved difference of those early-minus-late contrasts.
Report full-cell skip rates, candidate matched/mismatched cells, calibration
and held-out halves, and changes across cycles. Secondary intervals are
not multiplicity adjusted and cannot replace the primary classification.

The first K2 physical execution is an engineering pilot, even if controls
pass. A repeat with an independently chosen seed, unchanged code and
separate session is needed for stability. The repeated episodes within one
run are dependent; bootstrap intervals do not describe host-to-host or
day-to-day variation. Grouped/interleaved scheduling changes predictor
context and time order, so a difference does not by itself identify
branch prediction, transient execution, prefetch, a cache level, or
Fractal's cross-domain mechanism. A null does not prove those mechanisms
absent. Keep all failed-control and null attempts.

## One Windows run

After importing the K2 source revision into a clean checkout, run the VS Code
task **K2 receiver order diagnostic (Windows)**. It builds with MSVC and
MASM, chooses and prints a seed before execution, analyzes the full trace,
and prints `READY TO SHARE:` with one evidence ZIP even for failed controls.
Upload that ZIP for independent source-hash, trace, linked-instruction and
control audit. No USB boot is part of this user-mode diagnostic.
