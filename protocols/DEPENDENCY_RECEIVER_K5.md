# K5: resolved-condition marker-address dependency

Version 1.0, 3 November 2026. Prospective Windows engineering pilot, specified
after the K4 series and before any K5 Windows measurements. Earlier protocols,
measurements and thresholds remain frozen. Native Linux execution is development.

## Intervention

K5 retains the K4 256-branch prefix, one measured conditional site, page-zero
training markers, fresh nonzero page indices, two banks, decoys and randomized
reload order. It adds three modes in the same allocation: plain NOP slots,
resolved-condition register masking, and the earlier target-entry CPUID control.

The mask is distinct from a target serialization instruction. After loading the
fresh token and shifting its page index left by 12, the target-one body executes
`TEST EDX,EDX; CMOVZ EAX,EDX`. EDX is the actual condition loaded before the
measured conditional. When condition zero makes this the wrong body, its index
becomes zero. The target-zero body executes `TEST EDX,EDX; MOV ECX,0;
CMOVNZ EAX,ECX`: a nonzero condition similarly forces training page zero.
MOV preserves the TEST flags. CMOV uses registers, not a memory source. Correct
architectural bodies retain their fresh index. Six and one NOP bytes respectively
pad the two slots to 11 bytes. Plain and CPUID leave these slots as NOPs. The
mask mode leaves both target CPUID slots as NOPs.

This creates an address dependency on the resolved condition. It does not establish
a universal speculation barrier or rule out every alternative cache mechanism.
The ARCH_LOAD positive control must remain hot with masking. The code also records
CS.RPL and the measured conditional PC inside every training/probe invocation.
K5 requires CPL 3 and one exact branch address. Actual runtime images of all three
modes must match the readable assembly, frozen C template and analyzer contract.

## Collection and frozen analysis

512 blocks, 16 interleaved rounds of all 16 conditions, three modes, 393,216
recorded episodes; 16 warmup blocks are discarded by design before collection.
The 128-call 0011 prelude and 256 training calls remain fixed. A fresh nonzero
uint32 seed is selected and recorded before compilation/execution. Mode order is
shuffled in every block, and the 16 conditions are shuffled in every round.
Both RNG streams, including warmup draws, must replay exactly. No retry or early
sample deletion is permitted after looking at the result.

The first 256 blocks select the hot/cold threshold for each bank across modes.
The held-out half estimates hit rates and within-block training differences.
For each probe condition p and mode m:

`A_m = (candidate_mismatch - candidate_match) - (no_probe_mismatch - no_probe_match)`.

The primary is p0 `A_plain - A_mask`; p1 is secondary. Bootstrap 16-block cycle
means 10,000 times, fixed analyzer seed 20261102, and report the 95% within-run
percentile interval. These intervals do not measure between-host variability.

88 gates are required: for each mode/bank HOT and ARCH_LOAD >=95%; COLD, both
NO_PROBE cells and matched-training candidate <=5%; every cell's decoy <=5%.
Mask and CPUID additionally require each mismatched candidate <=5%. A numerical
signature requires all gates, p0 plain and primary interval lower bounds >5
percentage points, and both mask and CPUID adjusted whole intervals inside
[-5,+5] percentage points. Nulls and failed controls are retained unchanged.

## Execution and limits

Run `scripts/check_dependency_receiver_windows.ps1`. It records source, binary,
disassembly, host inventory, raw trace, runtime images and JSON analysis in one
evidence ZIP. MSVC and Python 3 are prerequisites. A completed inconclusive run
returns zero by default, with explicit failed gates; `-RequireValidControls`
requests a nonzero automation gate. Software and malformed-evidence errors fail.

K5 is an ordinary user-mode process. It cannot measure a user-to-kernel influence.
That separate question is K6. A successful K5 pilot remains a numerical signature
pending linked-harness review and independent sessions; it does not prove the
specific predictor or reproduce the Fractal authors' Apple M1 findings.
