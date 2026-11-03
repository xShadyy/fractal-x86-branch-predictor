# K5/K6 development record, 3 November 2026

These files are implementation checks, not new physical Windows or Fractal
branch-predictor results. K4's four original Windows runs remain unchanged.

## K5 native smoke

`k5-smoke-fixed.log` contains 3,072 episodes: 32 blocks, two rounds and three
modes, collected with seed 2026110301 on the Linux development host. Replay,
architecture, CPL 3, measured-PC and all three runtime snapshots validate.
The frozen analysis passes 86/88 gates. Both plain matched-training candidates
fail; the p0 primary is +25 percentage points. Its numerical signature is false.
Mask and CPUID adjusted contrasts are zero in this check. None of these values
substitutes for the prospective K5 Windows pilot. `k5-analysis.json` is reproduced
with `python3 scripts/analyze_dependency_receiver.py
results/k5-k6-development/k5-smoke-fixed.log --development --json`.

`initial-pc-failure/` preserves the preceding failed attempt and its source and
runtime bytes. A global assembly label left an unresolved PC-relative relocation
when extracting `.text` as raw code, so the recorded branch PC was wrong. It
failed architecture validation. The final local label resolves within the object;
the verifier now rejects relocations and checks the LEA's exact destination.

## K6 Fractal guest

The three complete `k6-*.log` traces cover direct Multiboot 1 QEMU boot and
Multiboot 2 ISO boot under SeaBIOS and OVMF. Every trace has 384 recorded rows,
96 per actual pair 3->3, 0->0, 3->0 and 0->3. The measured routine records the
conditional PC `0x40b571` in both privileges; runtime bytes, schedule, tags,
architectural returns, checksums and completion marker validate. All analyses
declare functional-only scope, hardware eligibility false and numerical outcomes
null. Run `python3 scripts/analyze_fractal_privilege.py <log> --development`.

The emulated CPU reports hypervisor=1 and invariant_tsc=0. The physical payload
must reject this platform. TCG timings are not analyzed for hardware effects.
The physical 393,216-row payload has not run on a physical machine.

Two preceding guest failures remain visible. `constructor-less-boot-failure.log`
records the host-GCC kernel's early triple fault before collecting `.init_array`
constructors. `uefi-mb1-rsdp-failure.log` records UEFI's failure to supply ACPI in
the legacy BIOS search range. The declared constructor and bounded Multiboot 2
patches fix these development failures. The latter adds boot/module/ACPI handling;
it does not change the measured fthread or syscall implementation. Framebuffer
tags are not normalized in this serial-capture research path. Existing upstream
RSDT-based ACPI and motherboard-specific hardware support remain limitations.

## Validation and packaging

The regression suite covers genuine nulls, distinct masking versus CPUID-only
suppression, residual/no-probe heat, decoy heat, corruption, CPL/PC changes,
missing completion, and same-domain positive gating of UK interpretation. The
first complete suite passed 237 tests; the final suite passes 239, including a
full-size analysis fixture with explicitly synthetic timings. The final binary
and ISO recordings, artifact hashes, source hashes and emulation-rejection check
are preserved in `distribution-validation/` and the distribution build manifest.
The 393,216-row physical ELF loads and rejects emulation before any collection.
PowerShell scripts are parsed and packaging branches exercised
using PowerShell 7 on Linux; MSVC and the Windows measurement path cannot be run
here. The Windows runner is based on the already-used K4 workflow.

The distribution includes both compiled payloads, initrds, both boot ISOs, a
source bundle, upstream source and license, exact patches, tool commands and
SHA256 manifests. GRUB license and corresponding source accompany the ISOs.
QEMU/SeaBIOS/OVMF and the local PowerShell installation are test tools and are
not redistributed. Physical capture must still be performed and reviewed.
