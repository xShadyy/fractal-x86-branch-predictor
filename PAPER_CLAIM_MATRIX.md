# Fractal claim matrix and Windows x86 evidence boundary

**Source:** Ravichandran and Yan, [*Fractal: An Operating System Designed for Microarchitecture Reverse Engineering*](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf), especially §§1.2, 5.4, 6 and 7.1–7.4, Table 1. **Platform of those findings:** Apple M1 under Fractal. **Platform of this repository:** AMD Ryzen 7 9800X3D, native Windows x64, ordinary user-mode code, with a hypervisor reported by the host. A Windows x86 observation is a new platform-specific result and cannot confirm or refute an M1 result by itself.

## The complete evaluation matrix in the paper

Table 1 contains **48 outcomes**: indirect or conditional branch predictor (IBP/CBP) × M1 performance or efficiency core × ordinary or branch-removed ("Phantom") receiver × same-user-and-ASID, user-to-kernel, or different-ASID sender/receiver × instruction-cache fetch or data-cache execution channel. The 12 rows below each represent four outcomes. “Seen” means the paper reports that the receiver distinguished trained target choices; “blocked” means it did not. These are the authors' **M1 observations**, not measured outcomes of this repository.

| Predictor | Receiver branch | Sender → receiver | M1 p-core fetch | M1 p-core execution | M1 e-core fetch | M1 e-core execution | Windows x86 status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CBP | Present | Same user, same ASID | Seen | Seen | Seen | Seen | K is unimplemented. The older conditional data-cache probe had a null host trace; no instruction-fetch receiver exists. |
| CBP | Present | User → kernel | Seen | Seen | Seen | Seen | Cannot isolate privilege with a normal Windows process. |
| CBP | Present | Different ASIDs | Seen | Seen | Seen | Seen | Cannot set or mirror ASIDs and preserve the rest of the path here. |
| CBP | Removed | Same user, same ASID | Seen | Blocked | Seen | Blocked | The branch-versus-NOP [feasibility protocol](PHANTOM_FEASIBILITY.md) is unimplemented and requires one audited address and a working instruction-fetch receiver. |
| CBP | Removed | User → kernel | Seen | Blocked | Seen | Blocked | Cannot isolate privilege with a normal Windows process. |
| CBP | Removed | Different ASIDs | Seen | Blocked | Seen | Blocked | Cannot set or mirror ASIDs and preserve the rest of the path here. |
| IBP | Present | Same user, same ASID | Seen | Seen | Seen | Seen | I is an unmeasured candidate data-cache receiver; J is unimplemented. H measures whole-probe latency only. No isolated I-cache receiver exists. |
| IBP | Present | User → kernel | Seen | Blocked | Seen | Blocked | Cannot isolate privilege with a normal Windows process. |
| IBP | Present | Different ASIDs | Seen | Blocked | Seen | Blocked | Cannot set or mirror ASIDs and preserve the rest of the path here. |
| IBP | Removed | Same user, same ASID | Seen | Blocked | Seen | Blocked | The branch-versus-NOP [feasibility protocol](PHANTOM_FEASIBILITY.md) is unimplemented and requires one audited address and a working instruction-fetch receiver. |
| IBP | Removed | User → kernel | Seen | Blocked | Seen | Blocked | Cannot isolate privilege with a normal Windows process. |
| IBP | Removed | Different ASIDs | Seen | Blocked | Seen | Blocked | Cannot set or mirror ASIDs and preserve the rest of the path here. |

The Windows host has **no M1 p/e-core pair**: affinity comparisons between its 16 logical CPUs can study repeatability on this machine, not the paper's core-class claim. Windows Hyper-V presence and the general-purpose scheduler also change what a null trace means. In particular, Fractal's “128 constant branches flush the path history register” (§7.1) is a claim about the authors' setup. The analogous sequences in this repository standardize prior work; they do not establish a reset of the AMD predictor.

## Which eight same-domain analogues have a measurement path?

Ignoring the unavailable M1 core distinction and protected-domain transitions leaves **eight candidate x86 categories**: two predictors × branch present/absent × fetch/execution receiver. “Possible” below means an experiment can be implemented, not that the hardware will show a signal.

| Same-domain x86 category | Current repository evidence | Requirement before a mechanism claim |
| --- | --- | --- |
| IBP, branch present, instruction fetch | J is unimplemented. No target-specific isolated instruction-cache receiver or J executable exists in this package. | Establish an independently calibrated instruction-cache-specific readout and physically audit the receiver before any fetch claim. Whole-call latency would not isolate L1I fetch. |
| IBP, branch present, target execution | Study I implements an opposite-target data-cache receiver. Its first physical Windows run is pending. | Held-out hot/cold and train-matched no-probe gates, exact target-exclusive load audit, independent runs and alternative-cause analysis. |
| CBP, branch present, instruction fetch | No target-specific instruction-cache receiver. | Same receiver calibration and target-only code placement with one verified conditional branch site. |
| CBP, branch present, target execution | K is unimplemented. The older conditional probe has architectural controls, and its archived host trace was null. | A future candidate would need physical branch and exclusive-load audits, held-out hot/cold and no-probe controls. The older null does not prove absence of speculation. |
| IBP, branch removed, instruction fetch | [Protocol proposal](PHANTOM_FEASIBILITY.md) only; no same-address branch/NOP experiment or validated fetch receiver. | First establish a sensitive ordinary-branch fetch receiver. A proposed whole-call J measure, even if implemented, would not supply this prerequisite. |
| IBP, branch removed, target execution | No such receiver; the paper reports no M1 execution in this category. | A tested data-cache receiver and an audited branch-removed path. An x86 null would be bounded by receiver sensitivity. |
| CBP, branch removed, instruction fetch | [Protocol proposal](PHANTOM_FEASIBILITY.md) only; no same-address branch/NOP experiment. | First establish a sensitive conditional instruction-fetch receiver and keep target line and code address controlled. |
| CBP, branch removed, target execution | No such receiver; the paper reports no M1 execution in this category. | A tested data-cache receiver and an audited branch-removed path. |

**Interpretation rule:** the paper distinguishes speculative *fetch* by probing an instruction-cache line at the trained target and speculative *execution* by probing a data line loaded only by that target (§7.1.1). An ordinary TSC branch-latency contrast does neither. **J is unimplemented**; its proposed whole-call timing endpoint would include call/return and target work, so even a calibrated hot-versus-cold contrast could not isolate L1I fetch. Even a calibrated cache association in a Windows executable requires an audit that rules out an architectural target load, target-line overlap, residual training heat, code-layout artifacts and other paths before a tentative transient interpretation. Code patching to replace a branch with NOP may itself disturb the instruction cache and predictor state. A second address with a NOP does not isolate Phantom speculation at the trained address.

## Fractal workflow and system claims

| Paper stage or system feature | Current work | Boundary in this repository |
| --- | --- | --- |
| §6 stage 1: a working single-threaded branch train/receiver µtest | Six existing baselines; B2/C/D/E/F/L timing studies, H indirect timing, and I candidate data receiver. J and K are **unimplemented**. | New source is **not physically validated** on the Windows host. Static analyzer tests do not establish a working receiver. No isolated instruction-fetch receiver exists, and timing studies cannot serve as a data-cache receiver positive control. |
| §6 stage 2: separate sender and receiver, recover the same-domain signal | No validated split-thread pair (G excluded). | Windows scheduler and handoff insert uncontrolled branches and cache work. A future feasibility pilot needs a working unsplit positive control, matched sham handoff, exact affinity verification and auditable timing outside the handoff. A null would remain weak. |
| §6 stage 3 and §7.1–7.3: vary privilege or ASID while preserving code layout and order | No cross-domain study. | A normal user-mode process cannot switch to kernel privilege, assign an ASID, mirror full layouts between protected domains or suppress interrupts. A pair of Windows processes is not an isolated ASID intervention. |
| §§1.2, 5.4: multi-privilege concurrency, cooperative/branchless switching, gmap and sparse mirrored addresses | This repository uses native Windows APIs; the earlier project also launched Fractal in QEMU. | Measuring these **Fractal OS properties** requires running or instrumenting Fractal, outside the requested VS Code Windows user-mode microarchitecture suite. VirtualAlloc RX copies in F are not Fractal's gmap. |
| §7.1.6 and §7.2: p-core versus e-core results | No heterogeneous M1 hardware. | The 9800X3D does not supply M1's two core classes; logical-CPU robustness can still be recorded without representing this paper comparison. |

## Additional x86 questions beyond the paper's M1 result table

The archived balanced-batch and decision-source measurements, plus unmeasured B2/C/D/E/F/H/L, ask about decision order, probe length, training dose, intervening work, whole-path virtual-address arrangement, indirect-target latency and the effect of **prelude pattern and length** on a later one-call timing association. L is a **source-only timing study** comparing two prelude lengths and four sequences while holding its declared work fixed within each length. It does **not** measure an AMD path-history-register length or prove that any sequence reset predictor state. These are bounded measurements **if** their small-work controls and physical instruction audits pass; none yields a predictor table size or misprediction count from time alone. J and K are gaps, not source code or host pilots in this package.

L's source varies prelude context. Further controlled questions could concern condition-line latency, address layout, or repeatability across logical CPUs and days. Those are research directions rather than implemented J/K receivers; each would require its own controls and physical code audit. Repeated blocks within one session are not independent host replications.

## Evidence gates and stopping rule

1. Preserve the source revision, planned conditions and seeds before the first host run. Archive each exact executable, raw trace, disassembly, tool versions, host metadata, and every failed-control attempt.
2. Validate hot/cold, architectural target and no-probe controls on held-out samples **at the scale of the claimed effect**. Do not describe a target hit as speculative fetch or execution if the receiver or exclusive path has not passed.
3. Check the *linked Windows PE* for the same physical branch address, target byte/line separation, actual stores and loads, fences, timer paths and the intended train/probe callsites. Source-level tests and MASM listings alone are insufficient.
4. J, K and the branch-versus-NOP assay are **unimplemented**. A working physical receiver positive control is a prerequisite to a new claim. If the existing candidate receiver fails, retain the null or inconclusive pilot and stop escalation to cross-thread or cross-domain inference.
5. Freeze a supported primary contrast only after the exploratory pilot, then repeat unchanged with independent seeds on separate sessions. Report both probe directions and all planned negative results; use complete runs as replication units.

This matrix covers every **reported §7 evaluation category** and states the concrete measurement boundary. It does not claim to enumerate all future microarchitecture experiments, reproduce Apple M1 behavior on AMD, or establish Fractal's cross-domain findings using Windows user-mode code.
