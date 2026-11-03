# K6: training across actual Fractal x86 privilege levels

Version 1.0, 3 November 2026. Prospective physical engineering pilot. No physical
K6 result existed when this protocol was written. QEMU TCG is functional validation.

## Question and experimental context

Does training the shared measured conditional at CPL 3 affect its fresh-marker
response when probed at CPL 0 in the pinned Fractal x86 OS? This is a cooperative,
shared-address experiment in Fractal, whose intentional design permits kernel
fthreads. It does not test Windows kernel protections, secret extraction, another
process, an unmodified production OS boundary, or the authors' M1 result.

The upstream OS is Joseph Ravichandran and Mengjia Yan's work, pinned at
`03ad1c5b7c33621e7529ac6403eb9b1de4f8722f`. The public fthread API creates user
and kernel cooperative threads. The payload creates separate sender and receiver
threads at each privilege and uses the initial user thread as controller. Each
episode switches directly from sender to receiver, then back to the controller.
Interrupt-enable state is checked clear. This x86 path uses upstream syscalls;
it is not the paper's AArch64 branchless ultrathread path.

Four pairs are shuffled per block: UU (3 -> 3), KK (0 -> 0), UK (3 -> 0), KU
(0 -> 3). Inside each pair the three K5 modes are shuffled, then every round
shuffles all 16 K5 conditions. Both training and probing call an explicit shared
low-address function pointer. Actual CS.RPL and conditional-PC are stored by the
measured machine code itself and validated for every invocation. This rejects a
kernel thread silently measuring an upper-address alias. The receiver's actual
CPL is additionally recorded even in cells with no conditional probe. Condition,
token and marker accesses use the same stored low-address pointers across pairs.
All three runtime code snapshots must match the K5 contract.

## Physical pilot

The physical payload has 256 blocks, eight rounds, four pairs, three modes and
16 conditions, totaling 393,216 recorded episodes. It discards 16 warmup blocks,
uses 128 prelude and 256 training calls, and has preselected seed 2180673261.
Training page zero, fresh tags, decoys, no-probe, matched-training, warm-condition,
architectural-load and direct-HOT controls follow K5. No I/O occurs in collection;
the complete trace is emitted afterwards. Timer/serial helpers remain shared.

The initial platform is the reported Ryzen 7 9800X3D (CPUID signature 0x00b40f40),
64-byte CLFLUSH line, RDTSCP, invariant TSC, with CPUID hypervisor bit clear.
The payload/analyzer reject mismatches. A clear bit is reported inventory, not
independent attestation. Preserve motherboard/firmware, microcode and boot-method
notes with the trace. The guest reports observed CR4; its SMEP/SMAP and isolation
policy differ from Windows. Do not generalize across those policies.

For each pair separately, calibrate thresholds on its first 128 blocks and apply
K5's 88 held-out gates and 5 percentage-point margins to its last 128 blocks.
Bootstrap eight 16-block cycle means, with the frozen K5 procedure. The primary
UK endpoint is p0 plain adjusted training contrast minus mask adjusted contrast;
CPUID equivalence is a second required intervention. p1 and KU are descriptive
secondary checks; no extra claims arise from choosing the better direction.

UK interpretation requires numerical positive signatures in BOTH UU and KK and
all UU, KK and UK apparatus gates. Without same-domain positives a missing UK
response does not establish isolation. A UK numerical signature also requires
its own K5 primary/contrast/equivalence criteria. Even a positive physical pilot
requires linked assembly/C/syscall review and independent sessions/hosts before
mechanism attribution. No physical mechanism is automatically marked proven.

Retain every boot failure, partial trace, null and failed control. No automatic
rerun occurs. A subsequent session or seed needs its own prospective plan.

## Functional smoke and reproducible build

The smoke payload has two blocks, one round, one warmup block, eight prelude and
eight training calls: 384 rows, 96 per actual CPL pair. It always declares
`scope=development_only`. The analyzer requires `--development`, verifies replay,
architectural returns, CPLs, common PC, runtime bytes and end checksums, and emits
NO numerical hardware analysis. TCG cache timings have no physical inference.
Changing just a scope label cannot promote this trace to physical evidence.

`python3 scripts/build_fractal_privilege.py --output out/k6-build` clones the pin
into a new isolated directory, applies the two recorded patches, builds the kernel
using recorded GNU flags, and compiles both freestanding payloads.
The one-line linker change collects host GCC's `.init_array` in the existing
constructor table. Host GCC also requires the recorded large code model and
non-PIE executable link. `patches/fractal-multiboot2-k6.patch` adds a second boot
header, preserves the boot magic, bounds-checks module/ACPI tags and normalizes
the initrd handoff. This fixes the observed UEFI boot's missing legacy BIOS RSDP.
It retains the Multiboot 1 QEMU direct-boot path and existing RSDT-based ACPI use.
The measured fthread/syscall paths are unchanged. These are declared source/build
changes, not an untouched official cross-toolchain binary. Provenance and source accompany
the binaries. The original constructor-less failed developmental boot remains
documented in the development record.

The ext2 images are regular output files populated by mke2fs, not physical disks.
Both `/bin/utest` and `/bin/dash` contain the same payload to accommodate Fractal's
startup selection. Build requirements: GNU gcc/g++, make, binutils, git and e2fsprogs.
`run_fractal_privilege_smoke.py` requires QEMU and explicitly selects TCG, one CPU,
4 GiB RAM and no network adapter. It needs the complete marker AND valid records;
a QEMU exit code alone is insufficient because a triple fault may return zero.

## Physical boot and capture

The boot kit supplies the multiboot kernel, physical and smoke initrds, BIOS and
UEFI GRUB ISOs, and a GRUB menu. The ISOs' smoke entries are tested in QEMU with
SeaBIOS and OVMF; this does not establish compatibility with every motherboard.
They are unsigned research media, requiring firmware that permits their boot.
Boot the physical entry on the intended machine, with a second machine
capturing the entire COM1 serial stream at 115200 baud, 8 data bits, no parity,
one stop bit. The COM1 capture must include K6_CPU, K6_RUN, all three K6_CODE
records, all 393,216 K6_SAMPLE records, K6_END and FRACTAL_K6_OK. At 115200 baud
the post-collection trace transfer can take well over an hour; wait for the marker.
Fractal's serial hardware is the legacy UART; a USB adapter attached only to the
Fractal machine is not a substitute for a supported UART or motherboard header.

The GRUB menu does not auto-start the physical pilot. From Linux with GRUB rescue
tools and xorriso, rebuild both ISOs with `python3 scripts/build_fractal_privilege_iso.py
<boot-kit>`. Their menu uses Multiboot 2 for the ACPI/module handoff on UEFI.
Bootloader/firmware compatibility must be checked for the specific PC.
The package performs no disk writing, firmware changes or reboot from Windows.
After capture, run `scripts/package_fractal_privilege_windows.ps1 -Trace <log>
-Assets <boot-kit> -MachineDescription <notes>` to validate and archive it.
