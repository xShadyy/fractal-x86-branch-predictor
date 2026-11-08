# K7/K8 static machine-code review

The reviewed evidence matches the intended preparation, shared branch site, timer, and patch controls. No material static implementation defect was found. This is a code and provenance review, not a determination of the physical mechanism. No uploaded executable was run.

| Check | Result |
| --- | --- |
| Archived sources | All 14 are byte-identical to trusted revision `8080faed480a9eef086f1fc0396e38dba7de31c7` and match both build hash inventories. |
| Collector | SHA-256 `f3132ca14a107b1be70ec85c32ede0cef723c3f647d5ef0494cbfd1ec2d446b8` matches the build record. |
| Recorded MSVC disassembly | All 31,674 rows match the PE bytes. All 109,264 bytes of the virtual `.text` section are covered. The omitted 304 bytes are zero file-alignment padding. |
| Generated site | The embedded 1,743-byte template matches the trusted contract. Readable assembly, generated C header, and Python contract also pass the trusted generator's consistency check. |
| Runtime snapshots | All 30 across six attempts match the exact expected mode bytes and the copies recorded in the raw traces. Recorded bank bindings match public or private banks as specified. |
| Recorded execution metadata | All 983,040 samples have the expected training/probe CPL and shared branch PC. Each individual reload's start/end TSC_AUX values agree. |

The emitted preparation routine has separate 128-call prelude and 256-call training loops. Both tokens are zero for training. Fresh nonzero page tags are stored afterward at preferred PE addresses `0x140002815` and `0x140002824`. There are exactly 256 distinct bank `CLFLUSH` instructions covering all 64 pages in each of the four public/private banks, with no loop branch or call inside that block. MSVC schedules the probe-condition store at `0x140002A2D` within this block. It still occurs after training and before the optional condition flush, `MFENCE` at `0x140002F42`, and tail jump into the CPUID serialization helper. The branch probe calls this preparation routine and then the same shared-site wrapper consecutively.

The true masks consume the loaded condition in `EDX`; the sham masks use fixed zero/one registers with the same TEST/CMOV instruction topology. Receiver ablations replace five-byte marker loads with five-byte constant-return instructions. `sink_both` retains the plain instruction bytes and installs private bank pointers before training. The emitted installation path copies 1,743 bytes, changes the allocation to executable/readable, flushes the instruction cache, compares the installed bytes, and serializes.

The runtime site preserves Windows x64 nonvolatile `RBX`, `RSI`, and `RDI`. The timer preserves `RBX` across CPUID, retains the marker pointer in `R10`, AUX pointer in `R9`, starting AUX in `R11D`, and starting timestamp in `R8`. It uses CPUID outside the timed interval, RDTSCP/LFENCE before the marker load, and RDTSCP/LFENCE afterward. Both AUX stores occur after the measured load. Independent GNU objdump listings were retained for the emitted preparation/probe path and the plain runtime site.

All traces report a hypervisor and `lfence_always_serializing=0`. That reported bit does not establish the actual LFENCE configuration. Every recorded AUX value is zero, so equality provides limited independent evidence about physical-core migration when a hypervisor may supply a fixed value. Affinity still requests Windows logical CPU 0.

Snapshots were captured during initial mode installation. The source and emitted code recheck later installations, but the archive has no externally attested instruction trace for every episode. Source hashes and the embedded template also do not constitute a reproducible MSVC build or independent compiler attestation. These checks support interpretation of the measured user-mode apparatus; they cannot establish speculative-path execution, kernel influence, Apple behavior, or independent-boot replication.

The exact mechanical checks are reproducible with `audit_static_code.py`; their machine-readable results are in `static-code-review.json`.
