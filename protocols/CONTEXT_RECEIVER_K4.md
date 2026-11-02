# K4: fixed local branch context and interleaved fresh-marker episodes

Version 1.0, 3 November 2026. Prospective Windows engineering pilot informed
by the failed K3 Windows pilot. This protocol does not change K3's criteria
or reclassify any of its samples. Native server runs are implementation checks.

## Question and scope

Can a fixed instruction prefix shared by training and probing, together with
an interleaved condition schedule, produce a usable same-process apparatus?
K3's matched-training negatives failed and its hits were concentrated near
group entry. Different preceding branch paths are a plausible confound, not
an established cause. K4 changes two apparatus features together; comparing
K3 with K4 cannot isolate their individual causal contributions.

This is one ordinary Windows user process. It does not boot Fractal, change
privilege, measure branch-misprediction counters, or test a security boundary.
The OS and Apple M1 findings in the Fractal paper belong to its authors.

## Fixed instruction prefix

Before every invocation of the measured conditional, execute XOR EAX,EAX
followed by 256 distinct unrolled TEST EAX,EAX / JZ sites. Each jump skips
one INT3 and is architecturally taken. Finish with 62 NOP bytes. The resulting
1,344-byte prefix is identical for training and probing. It has no data loads.
The original K3 branch, two exclusive marker bodies, timer, serializer and
HOT helper follow it unchanged, at offsets shifted by 1,344 bytes.

The prefix constrains the recent local instruction path. It is not a verified
global-history scrub, predictor reset, or guarantee of identical predictor
state. Longer history, context changes, aliasing and speculative state remain
possible. Do not infer a particular predictor history length from this study.

The NOP/CPUID comparison patches the same two target-entry bytes in the same
allocation. Prefix, conditional address, body addresses and receiver helpers
remain fixed across modes. The page is RW during patching and RX during use.
Verify both runtime snapshots against the byte contract; verify readable
assembly against the C header with `verify_context_receiver_layout.py`.

K3's fresh tokens, separate banks, page-zero training markers, decoys,
architectural-return checks, 128-call 0011 prelude, 256-call trainer, unrolled
bank flushes, CPUID preparation and CPUID/RDTSCP reload helpers remain in use.
Hyper-V and CPUID behavior remain possible contributors. Record the reported
environment; do not change Windows security settings as part of this task.

## Schedule and data

Choose one nonzero uint32 seed before building. Record it and commit the
source before collection. Run 16 warmup blocks and 512 recorded blocks.
Each block has both NOP and CPUID modes, with their order alternating by
block and seed parity. Each mode contains 16 rounds. Each round shuffles
all 16 cells with Fisher-Yates using the schedule RNG and visits every cell
once. Generate fresh tokens, a distinct decoy and reload order from the
independent token RNG, exactly as specified in the analyzer's replay.

There are 262,144 recorded samples. The trace's episode number now denotes
the interleaved round, not adjacent repetitions of a grouped cell. Repeated
cells may still meet across round boundaries; no exclusion follows from that.
Record every episode and replay both RNG streams including warmup. Do not
exclude initial episodes, failed controls, large timings, nulls or failed runs.

## Frozen analysis

Select p0/p1 thresholds using only HOT/COLD samples from blocks 0..255,
pooled across the two modes. Use only blocks 256..511 for controls and
outcomes. A timing at or below the threshold is a hit. The same 58 gates as
K3 apply: HOT and architectural LOAD >=95%; COLD, NO-PROBE, matched-training
candidates and every decoy <=5%; CPUID mismatched candidates <=5%.

For each held-out block and p, let

```text
A_mode,p = (candidate_mismatch - candidate_match)
           - (no_probe_mismatch - no_probe_match)
I_p = A_nop,p - A_cpuid,p
```

The single primary is I_p0. Resample complete paired 16-block cycles with
replacement for 10,000 draws, keeping every cell and both modes together.
There are 16 held-out cycles. Report point estimates and 95% within-run
percentile intervals. Native shortened traces are development checks only;
their intervals are unsuitable for physical inference.

A numerical signature requires all 58 gates, the entire A_nop,p0 interval
above +5 percentage points, the entire I_p0 interval above +5 points, and
the entire A_cpuid,p0 interval within [-5,+5] points. An eligible null is
a successful scientific outcome. Failed gates mean inconclusive. The p1
mirror, round profiles, warm-condition and reload-order splits are descriptive.
Do not substitute one of them for the primary or alter these rules after
examining the Windows outcome.

## Interpretation and stopping

The first Windows run is an engineering pilot. Retain and review its complete
ZIP once. No automatic retry seeks a positive outcome. A subsequent fixed
replication plan must be written before collecting further sessions and
retain every attempt. A fresh process or seed is a session on this host,
not an independent host or CPU population.

Even a numerical signature requires linked Windows harness inspection,
exclusive-path and alternative-fill analysis, and separately started host
sessions. CPUID sensitivity alone cannot identify the trained predictor
target or prove a transient-execution mechanism. Fractal cross-domain work
requires a separate same-domain-validated physical Fractal experiment.

## Windows command and status

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_context_receiver_windows.ps1
```

VS Code task: **K4 context-prefix diagnostic (Windows)**. Keep the printed
`out\context-receiver-windows-*.zip`, including nulls and failures.

Exit zero means that collection and analysis completed. Inspect
`control_status`, `run_outcome`, and `numerical_signature_detected` separately.
Failed gates still print explicitly and remain false. Add
`-RequireValidControls` when automation should fail on inconclusive controls.
Build, runtime, malformed-evidence and provenance errors always fail.

## Primary references

- Ravichandran and Yan, [Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf): microarchitecture tests depend on instruction path and domain control.
- AMD, [Software Techniques for Managing Speculation](https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/tuning-guides/software-techniques-for-managing-speculation.pdf): distinguish speculative fetch, dispatch and data execution.
- Microsoft, [Hyper-V architecture](https://learn.microsoft.com/windows-server/virtualization/hyper-v/architecture): the Windows root partition can also operate above the hypervisor. A presence bit alone does not identify a guest.
