# K3: fresh target markers with a same-address serialization intervention

Version 1.0, frozen before the first Windows collection. This is a new
engineering pilot informed by K1/K2 and local development checks. It does not
change either earlier study's gates, data or conclusions. It runs entirely
inside one ordinary Windows user process on the documented AMD workstation.

## Why the earlier result is insufficient

K2's primary concerned an early-versus-late scheduling association. Every
trained-label candidate contrast included zero. Its high interleaved skip
rates leave the cache-fill mechanism unresolved. A line being hot does not
identify the selected predictor target or establish transient execution.
K2's RET/NOP layout also leaves a possible post-return path toward another
body. That is an audit concern, not a demonstrated explanation of K2.

## Apparatus and causal checks

Use one conditional instruction address and two exclusive bodies. Each body
reads its own token byte, shifts it by 12, then loads the corresponding page
in its own 64-page marker bank. All data regions are disjoint and page aligned.
Both bodies return their bank's fixed 1/2 value and have INT3 immediately
after RET. The readable layout, C template and analysis contract must agree
byte for byte. Record both actual runtime code images, not just source code.

For each episode:

1. Set both tokens to zero. Run a 128-call `0011` prelude and a 256-call
   constant trainer through one shared indirect-transfer site. Verify returns.
2. Write fresh tokens in 1..63, after training. Training's architectural
   marker is page zero. Fresh means unused by this episode's training, not
   globally unique or secret. Choose a distinct decoy page and reload order
   from a separate deterministic RNG.
3. Set the probe condition. Flush every marker page in both banks using
   unrolled instructions, then flush the condition except in `warm_mismatch`.
   Execute MFENCE and a serializing CPUID. Tokens remain warm for encoding.
4. Invoke the conditional site once, omit it, or execute the HOT control,
   depending on the cell. The normal probe selects p; measure bank 1-p.
5. Reload the fresh opposite marker and the distinct decoy in randomized order.
   Each helper executes CPUID before its timed interval, then uses RDTSCP,
   LFENCE, the load, RDTSCP, LFENCE. The contract requires AMD and RDTSCP.
   Timestamps are TSC ticks, not assumed core cycles.

Two modes use the same allocation, conditional address, target addresses and
timed helper. `nop` has two NOP bytes at each target entry. `cpuid` replaces
exactly those bytes with CPUID before the token load. All relevant pointers
are held in registers CPUID preserves; RBX is saved and restored. The code
page is RW while patched, RX while executing, never RWX. Instruction-cache
synchronization and byte verification occur before each mode's training.
Patching and CPUID may change other microarchitectural state; this is a
serialization intervention, not a measurement of a predictor table entry.

The HOT helper itself serializes before its only marker load. Each reload
helper serializes before timing, so the collector cannot speculatively run
its own marker load across the unresolved probe. The actual linked C harness
still requires inspection for unexpected memory references or control paths.

## Cells and schedule

For each p=0/1 and mode, collect these eight cells:

| Member | Training | Post-flush work |
| --- | --- | --- |
| candidate_t0 / candidate_t1 | Constant 0 / 1 | Probe selects p. |
| no_probe_t0 / no_probe_t1 | Matched constant 0 / 1 | Omit probe. |
| hot / cold | Constant p | Omit probe; HOT serially touches the fresh receiver. |
| arch_load | Constant p | Probe selects 1-p, architecturally loading the measured bank. |
| warm_mismatch | Constant 1-p | Probe selects p with condition left warm. Descriptive only. |

Choose a nonzero uint32 seed before compilation/execution. After 16 warmup
blocks, collect 256 complete blocks, both modes, all 16 cells, 16 episodes
per cell: 131,072 recorded episodes. Shuffle the 16-cell base permutation
once per 16-block cycle and rotate it each block. Alternate mode order using
block parity and seed parity. Cells remain grouped. Replay both RNG streams,
including warmup; archive every episode and its tags, decoy, reload order,
architectural returns, checksum and event hash. No outcome-based exclusions,
threshold changes or replacement of failed runs are permitted.

## Frozen analysis and decisions

Use only blocks 0..127 HOT/COLD samples, pooled across modes separately for
p0/p1, to select reload thresholds. Use only blocks 128..255 for gates and
outcomes. A time at or below the threshold is a hit. All 58 gates must pass:

- For each mode and p, HOT and same-site architectural LOAD >=95%; COLD,
  both NO-PROBE cells, and the training-matched candidate <=5%.
- For each p, the CPUID training-mismatched candidate must also be <=5%.
- Every mode/cell's decoy hit rate must be <=5%.

For each held-out block and p, define the training contrast in each mode:

```text
A_mode,p = (candidate_mismatch - candidate_match)
           - (no_probe_mismatch - no_probe_match)
I_p = A_nop,p - A_cpuid,p
```

The single primary is I_p0. Resample whole paired 16-block cycles for 10,000
bootstrap draws, retaining both modes and every cell together. Report the
point and 95% within-run interval; episodes are not independent replicates.
A numerical fresh-marker signature requires all apparatus gates, the entire
A_nop,p0 interval >+5 percentage points, the entire I_p0 interval >+5 points,
and the entire A_cpuid,p0 interval inside [-5,+5] points. An eligible null is
a valid outcome and strict analysis succeeds. Failed gates withhold the
signature even if a contrast is large. The p1 mirror, warm-condition cell,
receiver-order split and episode-position summaries are descriptive and
cannot replace the primary. No multiple-testing claim is made for them.

A numerical signature is evidence to investigate, not an automatic claim
of a proven mechanism. Inspect the linked executable, runtime snapshots,
address mapping and exclusive memory paths; inspect prefetch, prior-episode,
patching and context explanations; then repeat unchanged code in separately
started sessions with independently chosen seeds. Do not stop only when a
positive appears. The first Windows run remains an engineering pilot.
Neither a positive nor a null establishes Fractal's cross-privilege or M1
claims. A virtual server's development timings do not establish a result on
the Ryzen workstation. A CPUID hypervisor bit alone does not distinguish a
physical Windows Hyper-V host from a guest.

## Run and retain evidence

Select **K3 fresh target markers (Windows)** in VS Code, or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_fresh_receiver_windows.ps1
```

Retain the full `out\fresh-receiver-windows-*.zip`, including nulls and
partial failures. It contains raw trace, EXE, RX snapshots, linked disassembly,
source snapshot, source and binary hashes, host inventory and analysis.
Source must be committed before collection. The runner never pushes commits.
Share the first ZIP for byte, trace, control and linked-path review before
interpreting a numerical signature. Repeat sessions are a later evidence
stage, not something this unexecuted Windows implementation can supply.

## Primary technical references

- AMD, [Architecture Programmer's Manual, Volume 2, section 7.6.4](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content): CPUID serialization and dispatch-ordering definitions.
- AMD, [Software Techniques for Managing Speculation, G-2](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/programmer-references/software-techniques-for-managing-speculation.pdf): RDTSCP dispatch serialization and LFENCE configuration. CPUID remains outside the timed interval.
- Ravichandran and Yan, [Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf): distinguish target fetch from target data execution and same-domain controls from security-domain experiments. The OS and M1 findings are theirs.
