# J feasibility: target code-line timing on native Windows x86

**Status: proposed protocol only. No J executable, physical J trace, or
instruction-cache fetch result exists.** This is a same-process user-mode
pilot that could run from VS Code without booting another OS. Its goal is to
decide whether this AMD workstation has a usable *target-specific code-line
readout* before any branch-predictor fetch or Phantom experiment is claimed.
The implementation, exact condition schedule, thresholds and analysis must
be committed before its first physical run; an observed pilot must never be
retroactively presented as preregistered confirmation.

## Relationship to the paper

Ravichandran and Yan's [Fractal paper, §7.1.1](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
times a `ret` in the trained target's instruction-cache line to observe a
target fetch on Apple M1. It measures target *execution* separately using a
data line loaded by the target. Their single-threaded positive receiver is
established before sender/receiver separation and privilege changes. A timed
`ret` in a Windows x86 process includes call/return prediction, translation,
instruction fetch from several cache levels and timer noise. A result from
this proposed pilot would initially mean **target code-line latency changed**,
not that an isolated L1I event or a particular predictor structure was
identified. The host has reported a 47-TSC-tick lattice and `hypervisor=1`;
[AMD uProf's Windows limitation](https://docs.amd.com/r/en-US/63856-uProf-release-notes/6.1.-CPU-Profiling)
says EBP and IBS profiling are disabled with Hyper-V enabled. Do not assume
hardware fetch-event corroboration is available.

## Candidate physical layout and episode

Create two short `ret` target bodies, A and B, on separate audited code pages
or at least separated far beyond a 64-byte code line. Keep a single indirect
dispatch instruction and call path for all prelude, training and probe calls.
Training selects A or B at that site. The probe always goes to the *other*
target when monitoring one target, so the monitored line is not executed
architecturally by the probe. Flush both target code lines *after* training;
flush a pointer slot before the indirect probe to extend target resolution;
order `CLFLUSH` with `MFENCE` as required by the [AMD instruction
reference](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/24594.pdf).
Measure one monitored line per episode with one fixed, fenced TSC wrapper and
one fixed direct `call` to a `ret` in that line. Run symmetric A-monitored
and B-monitored cells. Do not modify code or call Windows
`FlushInstructionCache` inside the episode. That API is for code generation
or modification, and the extra transition would change the experiment.

The compiled layout is part of the intervention. MASM `.code` `ALIGN 64`
previously failed on this toolchain because the segment alignment was lower;
use measured post-link separation or separate RX pages with exact runtime
byte hashes. Never infer placement from source comments alone. Likewise, a
warm-up or fixed `0011` prelude standardizes activity but is not a proven
reset of an AMD history structure.

## Calibration and comparison arms

Each arm retains identical training labels, monitored target, flushes and
timed readout. Randomize complete blocks and balance measurement position;
retain every attempt and use a fresh, recorded seed.

| Arm | Additional action after the line flush | Purpose |
| --- | --- | --- |
| Architectural hot | Directly call monitored target before timed readout | Held-out sensitivity to a known fetched/executed line. |
| Architectural cold | Do not call monitored target | Held-out cold reference. |
| No dispatch | Omit only the probe dispatch after the same training and flush | Detect training-label residue, readout prediction and harness effects. |
| Ordinary dispatch | Probe architecturally to the opposite target | Candidate association with a trained, unselected code line. |
| Other-line control | Call or probe the other target only | Detect page adjacency, target overlap or generic code warming. |
| Data-only placebo | Load the monitored code line as data in a separate arm | Determine whether lower-cache/data residency also speeds the readout. |

The data-only placebo is a diagnostic; it deliberately touches the code
bytes as data and must not be mixed into the candidate arm. A positive
placebo means a faster timed `ret` is not specific to L1I. Held-out hot/cold
thresholds must be fit on an independent training half of calibration cells,
then evaluated on the other half without retuning. Raw latencies and
thresholded outcomes should both be retained, including outliers.

For each monitored target `m`, define `H_dispatch(m)` as the paired
train-`m` minus train-other difference in the held-out fraction classified
hot after ordinary opposite-target dispatch. Define `H_no_dispatch(m)` with
the identical training comparison when dispatch is omitted. The candidate
interaction is `F(m) = H_dispatch(m) - H_no_dispatch(m)` computed within
complete blocks. Report A and B separately and the prespecified mean of
their blockwise interactions as the one primary feasibility contrast.
Use block/cycle resampling within a physical run for uncertainty; treat
separate runs, not episodes or blocks, as independent replications. The
final executable protocol must freeze numerical calibration, placebo and
practical-effect gates before collection. If hot/cold discrimination or
no-dispatch neutrality fails, the candidate is **inconclusive**, not a
negative predictor result.

## Physical audit and escalation boundary

Archive one ZIP per session with raw samples, every condition and failed
attempt, seed/schedule replay, exact EXE, source/tool hashes, PE `.text`
hash, linked disassembly, runtime target/dispatch addresses, exact target
bytes, Windows build, CPU and affinity, hypervisor status, analyzer output,
and manifest. Audit the *linked PE* and runtime target bytes: one indirect
branch site; target lines on distinct pages/lines; the watched target
architecturally unreachable in the candidate probe; the readout's direct
call and return actually in the watched line; no target-line data read,
prefetch, or unintended call between flush and timed readout. Check the
pointer slot load, fences and timer ordering in compiled instructions.

Only a calibrated, independently repeated directional ordinary-branch
readout would justify designing a branch-versus-NOP [Phantom feasibility
test](PHANTOM_FEASIBILITY.md). Fetch-versus-execution comparison additionally
requires a *corresponding* validated data-line receiver (I for indirect
branches, or K alongside a future conditional fetch receiver). A physical
J null after passed calibration would bound this specific Windows readout,
not refute the paper's M1 results. Cross-thread, ASID and user/kernel claims
remain outside this user-process apparatus.
