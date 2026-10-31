# Same-site branch-presence experiment: feasibility gate

**Status:** protocol proposal, not an implemented or measured Phantom result. This is deliberately absent from the Windows batch task until a physical instruction-cache receiver and a patch-survival positive control work on this host.

## What the paper actually tests

In [Fractal §7.3](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf), Ravichandran and Yan replace the receiver's dispatch branch with a NOP while keeping the other train/receiver parameters fixed. Their sender and receiver are precisely ordered and mapped at mirrored virtual addresses. The reported M1 result is a fetch signal with the branch absent, without target execution. The distinction depends on the separate instruction-cache and data-cache receivers of §7.1.1. Our Windows process cannot reproduce that scheduler, mirroring, privilege setup, or M1 hardware.

The scientific question feasible to pose on this x86 host is narrower: after training an indirect branch at a fixed virtual address, does execution through **that same address** with the indirect jump replaced by an equal-length NOP yield a train-label-dependent instruction-cache effect at an architecturally unreachable target? A timing-only result or a target data-cache hit is not a substitute for an instruction-cache fetch receiver.

## Why this is gated

Two processes can use matching virtual addresses but introduce separate address spaces, scheduler handoff and potentially different mitigations. Two distinct sites in one process test address aliasing, not branch absence at the trained site. A single ordinary Windows process would need to modify executable bytes between training and probe. VirtualProtect, writing code and FlushInstructionCache introduce kernel transitions, cache changes and branch history before the probe. These operations may destroy the very state being tested. There is no trustworthy inference from a NOP null unless a matched, modified-but-still-branching control retains a label-dependent signal.

The [measured data-cache receiver I](results/2026-10-31-windows-suite-pilot/README.md) passed architectural receiver controls but showed no convincing opposite-target data-line association. It cannot certify that a target *instruction line* was fetched. An instruction-cache fetch receiver with independently passing architectural hot, cold and no-probe controls must first succeed in a physical Windows executable. Until then, more iterations or a branchless C function cannot turn this into a Phantom test.

## Conditional protocol if the prerequisite passes

Use one fixed, audited virtual dispatch site. An indirect jmp rax is two bytes (FF E0), and a two-byte NOP can occupy the same bytes without moving the fall-through return or the distant target lines. The register/pointer setup before the site and target addresses must stay fixed. A build-specific byte audit must verify the exact encoding before any patch is attempted; an assumed encoding is insufficient.

For each randomized complete block, use both training labels and both receiver target lines. Every cell executes the same code-protection transitions, byte write and instruction-cache synchronization:

| Probe variant | Bytes after training | Purpose |
| --- | --- | --- |
| Branch retention | Write the original branch bytes back, flush instruction cache, then probe the branch | Positive control that training information survives the patch sequence. |
| Branch removal | Write the equal-length NOP, flush instruction cache, then probe the fall-through path | Candidate branch-absent receiver. |
| No probe | Follow the same train/patch/flush sequence and omit the dispatch call | Check residual target heat, patch-driven prefetch and harness effects. |
| Architectural receiver calibration | Directly execute or do not execute the target line under the same patch operations | Verify the instruction-cache measurement discriminates hot and cold at the required scale. |

Flush the measured target instruction lines after training and patching, before the receiver. Record exact target/dispatch virtual addresses, pre- and post-patch byte hashes, code protections, source and PE hashes, trace-level train labels, scheduling/affinity metadata and per-cell raw timing. Patch both directions with matched work and randomized order. A separate data-cache target-only receiver can check whether any inferred fetch also executes target loads.

**Required gates before interpreting a NOP result:**

1. The ordinary, unpatched same-site indirect fetch receiver is calibrated and train-label sensitive on the physical host, with held-out hot/cold and train-matched no-probe controls.
2. The **branch-retention** patch arm preserves that same directional association after the full patch/flush sequence. If not, the NOP arm is inconclusive.
3. Disassembly and runtime byte audits show one site, equal instruction footprint, no architectural path to the target in the NOP arm, and no target-line access from the patch/flush/measurement machinery.
4. Independent sessions with distinct preselected seeds repeat the pattern, with nulls and control failures retained. A positive NOP association remains a candidate for alternative-path investigation, not an automatic claim of the paper's M1 Phantom result.

No instruction-cache receiver is implemented in this package, so there is no scientifically defensible Phantom assay in the one-click suite. The prerequisite and patch-survival gates make a later version falsifiable without presenting a source-only control as a measured discovery.
