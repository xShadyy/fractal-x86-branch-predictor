# Research route after the Windows K5 replication

Decision and source inspection: 5 November 2026. This is a research assessment,
not a report of new kernel-mode processor measurements.

## Decision

Publish two clearly separated records now: our completed Ryzen/Windows K5
replication, and a reproducible reanalysis of the Fractal authors' released M1
data. Pursue a bounded conditional-branch privilege-domain experiment as the next
hardware study. The most practical route for reusing published privileged x86
research code is native Linux on the same Ryzen, using a reviewed subset of
uARF or related research infrastructure. Physical Fractal is the closest
methodological match, but must first pass a boot-and-trace-export feasibility
gate on this motherboard. A new Windows driver is an alternative research
project, not an already available continuation of K5.

This recommendation concerns practical experimental control and code reuse.
No route guarantees that this AMD processor will reproduce an M1-specific
positive result. A well-controlled difference is a useful result.

## What can actually be reused from Fractal

The authors publish both an operating-system repository and a separate evaluated
artifact. They are different releases:

- Kernel: <https://github.com/jprx/fractal>, with an MIT license. Our existing
  Fractal work pins `03ad1c5b7c33621e7529ac6403eb9b1de4f8722f`.
- Official artifact: <https://doi.org/10.5281/zenodo.19556693>, linked by the
  authors' website and the IEEE S&P accepted-artifact list.
- Inspected artifact version: Zenodo record `19557478`, archive `fractal.zip`,
  SHA256 `8ee05fcccc9c80769c812bdd9f698226b48155aee2dbb6f491798da668182ac2`.

The artifact contains `experiments/utest.c`, `uarch.s`, `arm_inst.h`, `m1.h`,
`pmc.c`, collection scripts, plotting scripts, `SP_RESULTS.md`, and 48
`precollected_data/*.txt` traces. These cover conditional/indirect branches,
performance/efficiency cores, same-privilege/cross-privilege/different-address-
space configurations, fetch/execution probes and normal/Phantom variants.

The actual experiment backend is Apple/AArch64-specific: its build selects
`aarch64-fractal-elf`, Apple M1, ARM instruction generation and Apple performance
counters. It is not an x86 Windows executable. The existing independent K5/K6
programs are adaptations inspired by the method, not the authors' original M1
experiment ported without changes.

The supplied traces and plotting workflow can be evaluated at home without a
Mac. This checks data processing and the supplied evidence; it is not an
independent physical M1 rerun. The artifact also documents a Figure 8 revision
after a bug fix, so comparisons must identify the exact artifact/manuscript
version. Agreement must not be assumed from figure labels alone.

The inspected archive has no top-level LICENSE/COPYING file; the Zenodo record
reports CC-BY-4.0 while the sibling artifact metadata links GPLv3. The kernel's
MIT license must not be assumed to cover every artifact component. This update
does not vendor or relicense the artifact's experiment or plotting code.
Independent analysis code and provenance retain the original authors' credit.

## Claims and their present status

| Claim | Present status |
|---|---|
| K5's defined user-mode cache response repeats on the reported Windows/Ryzen configuration | Validated in three planned new-boot attempts; all 88 gates pass in each |
| The saved K5 analysis follows from the raw measurements | Replayed exactly, with an additional independent count/PE audit |
| The precise predictor/transient-execution mechanism is identified | Unresolved |
| User-mode training influences a physical kernel-mode receiver in our project | Not collected |
| Our Fractal x86 privilege harness executes correct CPLs and one measured site | Functional evidence in QEMU TCG only |
| The authors' supplied M1 data can be reanalysed without M1 hardware | Yes; kept separate from new measurements |
| Ryzen results confirm the exact M1 hardware behavior | Not a supported inference |
| Fractal is less noisy or offers better experimental control than a comparable Linux/Windows implementation | Requires an explicitly matched comparison |

K5's three primary effects are +99.70703125, +99.609375 and +99.8291015625
percentage points. The 1,179,648 recorded episodes include calibration; 589,824
are held out for estimation. The confidence intervals are within-run intervals.
The recorded host has a hypervisor present and VBS status 2. These are part of
the tested configuration, not grounds for relabelling it as bare metal.

## Practical options

| Route | What it can establish | Readiness and decision |
|---|---|---|
| Reanalysis of the authors' 48 M1 traces | Reproduction/audit of released data processing and configuration comparisons | Immediate, no kernel or Mac required; publish with explicit data provenance |
| Further native Windows user-mode experiments | Causal tests of the K5 signature under the documented Windows configuration | Immediate platform availability; new intervention and frozen plan required |
| Native Linux on the existing Ryzen, with a reviewed kernel research backend | Controlled physical x86 user/supervisor observations under declared research settings | Recommended hardware extension; target-kernel/module/counter and control validation still required |
| Fractal booted directly on the Ryzen | Closest platform/method match to the Fractal x86 research goal | Existing kernel/payload/ISOs, but no verified motherboard boot/export path |
| Native Windows plus a new research driver | Actual Windows user/kernel measurements | Substantial static-code, signing, address/history and validation work |
| Hardware QEMU/WHPX on Windows or native KVM on Linux | Guest-user/guest-kernel observations under that hypervisor | Useful separate secondary study; not validated by TCG smoke or CPU-passthrough settings alone |
| KVM nested inside WSL2/another VM | Behavior under a nested virtualization stack | More layers and feature exposure to validate; poor primary choice for minimizing confounds |
| QEMU TCG or software M1 emulation | Correct program logic, boot and trace handling | Functional checks only; does not reproduce a real Ryzen/M1 predictor |
| A model-based CPU simulator | Behavior of the selected model | Potential separate simulation project; no direct silicon confirmation |
| Another existing physical x86 computer, including the user's Ubuntu laptop if its CPU is suitable | A second-host experiment after identifying its CPU and controls | Useful independent extension; a different CPU is a separate result, not a matched OS comparison |
| Borrowed physical M1 Mac mini or a lab collaborator | Closest route to new measurements of the paper's specific hardware | No purchase necessary, but physical/custom-boot/console access required; not needed for this x86 plan |
| Rented remote bare metal | Native tests only when custom boot, console and recovery are genuinely available | Do not assume a normal cloud VM or a Mac rental supports Fractal |
| A new tiny kernel/UEFI experiment | A custom native measurement environment | Technically possible but recreates infrastructure and distracts from reusing Fractal |

External Linux/Fractal boot is a way to use the existing computer temporarily;
it need not replace the Windows installation. If Windows must remain running
throughout, that excludes these native external-boot routes and leaves the
Windows user/driver or virtualized study with their different scopes.

## Why native Linux is the practical hardware recommendation

Fractal itself cites the published uARF research framework. VMScape releases
`uARF` and `vbti_analysis`; its authors state that their artifact was verified
on Ubuntu 24.04. The inspected repository is pinned at
`dfaf83549f3b6c428635515f912887bb5ee61480`. Its library supplies code placement,
assembly/JIT, cache and counter helpers and supervisor-execution infrastructure.
These are reusable primitives, not an already validated conditional K5 port.

BPRC's separate published artifact contains
`experiments/uarch-research-fw` and `exp-test-setup`, and explicitly lists a
Ryzen 9 9900X/Zen 5 configuration. The inspected revision is
`8c4b03ae809f616d8ea5261f00af0c975a3d0486`. This supports evaluating its
infrastructure on a desktop Zen 5 target; it does not establish that 9800X3D
has the same attack outcome. Its Zen 5 counter path references a Zen 4 header,
so model-specific event semantics must be independently checked.

Both inspected research supervisor backends change SMEP/SMAP handling to execute
controlled callbacks. uARF's domain-analysis instructions also document a
research boot configuration because dynamic handling was unreliable. Such an
experiment must report its actual CR4, mitigation and kernel state. It does not
test an unchanged production OS boundary. Upstream automation can change
packages, kernels and boot configuration; a reviewed minimal setup is required
instead of running every provided deployment script.

The useful adaptation is our own fresh-marker, matched-training, omitted-probe,
decoy and architectural-positive design with held-out calibration, fixed
randomized schedules, actual CPL/PC records and complete raw evidence, using a
reviewed published backend. The goal is a controlled conditional-branch domain
matrix, not an end-to-end secret-leaking demonstration.

## Why the other routes are not shortcuts

The K6 boot kit expects a legacy UART at fixed I/O base `0x3f8`. The inspected
Fractal x86 source initializes it before other boot diagnostics; the transmit
routine can spin waiting for its ready bit. Missing hardware can therefore mean
no output or a stall, depending on port behavior. The published connector lists
for the X870E AORUS ELITE WIFI7 family do not list a COM connector. No confirmed
PCIe/USB serial transport or persistent USB/network export path is implemented
in our kit. Its UEFI patch still uses RSDT-based ACPI and has not been validated
on this motherboard. Launch a small functional trace only after resolving that
output path. A generic serial adapter is not a verified replacement.

Upstream's branchless ultrathreads are AArch64-only. Our x86 syscall-based
transitions have branch history of their own; transition effects must be measured
and controlled rather than represented as an identical port.

Windows K5 changes code bytes within one allocation to retain the measured PC.
Microsoft's HVCI-compatible-driver rules prohibit dynamic kernel code and
writable/executable sections. A Windows driver redesign must account for
different static code sites and user/kernel address relationships. Official
driver samples and libtea are useful references, not verified Windows 11/Zen 5
measurement harnesses. A valid signing/testing path remains necessary.

AMD uProf 5.3 explicitly disables CPU EBP/IBS profiling on Windows with Hyper-V
enabled. The current K5 host records a hypervisor/VBS; usable counters must be
demonstrated on the actual version/configuration before promising this form of
corroboration. Hypervisor presence alone does not prove that HVCI is enabled.

QEMU WHPX documents BTB flushing associated with guest entry/exit. Our CPUID-heavy
preparation/timing paths therefore need actual accelerator validation; a missing
guest cross-privilege signal is uninterpretable if same-domain controls fail.
Guest CPL 0 is the guest kernel, not the Windows host kernel. Hardware acceleration
is scientifically useful when the claim is scoped to that virtualized setting.

AWS's Mac bare-metal instances are excluded from its EC2 Serial Console service.
This illustrates why renting physical hardware does not establish the custom
boot/USB-VDM capture access required by the M1 artifact. Do not budget a cloud
rental as a verified Fractal solution without checking those facilities.

## A bounded experiment and completion rule

1. Preserve the completed K5 study and its original evidence unchanged. Publish
   the current audit and author-data reanalysis as distinct result categories.
2. Specify one conditional-branch question, one CPU, one research configuration
   and one backend. Review its actual privilege-transition and memory-permission
   paths before collection.
3. Establish architectural controls and a causal same-domain signal in that new
   environment. The successful Windows K5 result cannot substitute for controls
   after changing OS or hypervisor. Confirm that sender/receiver splitting itself
   preserves the signal.
4. Record actual CPLs and measured PCs, then compare UU, KK, UK and KU using
   controlled code, relevant mappings, training inputs, ordering and transitions.
   Require valid UU/KK positives before interpreting a missing UK response.
5. Freeze endpoint, intervention contrasts, equivalence margins, attempt count,
   exclusions and reporting rules before a fresh replication series. Retain
   every attempted run. Confirmed nulls and invalid apparatus are different
   outcomes.
6. Audit linked code and runtime records, evaluate targeted causal controls and
   use correctly validated counters where available. A counter alone does not
   establish the exact speculative target or mechanism.
7. Publish the dataset, executable/source provenance, raw traces, analysis,
   distributions, limitations and a claim ledger. A comparison claiming an OS
   advantage additionally needs matched mitigation/hypervisor conditions and
   quantitative noise/control comparisons.

An interpretable, repeatable conditional-branch result completes this bounded
study even if AMD differs from M1. Indirect prediction, address-space tagging and
Phantom fetch/execute separation are separate later experiments. A data-cache
marker alone is not an instruction-fetch sensor.

## Related work changes what we should expect

VMScape's Zen 5 analysis reports user/supervisor tagging of indirect BTB entries
and describes Zen 5 as unaffected by Phantom speculation in its retpoline
discussion. These are model-specific related results, not a measured outcome
for our conditional K5 site or a guarantee for every 9800X3D setup. They are a
reason to measure AMD behavior rather than define success as matching all M1
positive cases. Current mitigations, firmware and microcode can change results.

## Primary sources inspected

1. Fractal paper: <https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf>.
2. Authors' project and artifact link: <https://fractal-os.com/>.
3. Evaluated artifact listing: <https://www.ieee-security.org/TC/SP2026/accepted-artifacts.html>.
4. Artifact DOI: <https://doi.org/10.5281/zenodo.19556693>; inspected version
   <https://zenodo.org/records/19557478> and its `fractal.zip`.
5. Fractal kernel/build/hardware documentation: <https://github.com/jprx/fractal>.
6. VMScape artifact: <https://github.com/comsec-group/vmscape>.
7. VMScape paper: <https://comsec-files.ethz.ch/papers/vmscape_sp26.pdf>.
8. VMScape authors' explanation: <https://comsec.ethz.ch/research/microarch/vmscape-exposing-and-exploiting-incomplete-branch-predictor-isolation-in-cloud-environments/>.
9. BPRC artifact: <https://github.com/comsec-group/bprc>.
10. nanoBench: <https://github.com/andreas-abel/nanoBench>.
11. libtea: <https://github.com/libtea/frameworks>.
12. Memory-integrity-compatible driver rules: <https://learn.microsoft.com/en-us/windows-hardware/drivers/driversecurity/implement-hvci-compatible-code>.
13. Current Windows driver policy: <https://support.microsoft.com/en-us/windows/hardware/drivers/the-windows-driver-policy>.
14. AMD uProf 5.3 CPU limitations: <https://docs.amd.com/r/en-US/63856-uProf-release-notes/6.1.-CPU-Profiling?contentId=C_XgpcccYTf3KpmHdioxfQ>.
15. QEMU WHPX: <https://www.qemu.org/docs/master/system/whpx.html>.
16. Linux VMScape mitigation: <https://docs.kernel.org/admin-guide/hw-vuln/vmscape.html>.
17. Ubuntu live environment: <https://ubuntu.com/desktop/docs/en/26.04/tutorial/try-ubuntu-desktop/>.
18. AWS serial-console exclusions: <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-serial-console-prerequisites.html>.
19. Gigabyte board-family connector specifications:
   <https://www.gigabyte.com/Motherboard/X870E-AORUS-ELITE-WIFI7-rev-10-11/sp>,
   <https://www.gigabyte.com/Motherboard/X870E-AORUS-ELITE-WIFI7-rev-12/sp>,
   <https://www.gigabyte.com/Motherboard/X870E-AORUS-ELITE-WIFI7-rev-13/sp>.

Public frameworks above have their own licenses. They are linked as research
dependencies, not copied into or relicensed as this project's code. No kernel
module, driver, deployment playbook, boot-media writer or new hardware experiment
was executed during this research assessment.
