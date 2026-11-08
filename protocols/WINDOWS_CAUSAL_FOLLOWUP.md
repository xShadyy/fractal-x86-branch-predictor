# Windows causal follow-up: matched dependency and receiver interventions

Protocol version 1, prepared 8 November 2026 before collecting this study.
The machine of interest is the reported AMD Ryzen 7 9800X3D Windows workstation.
This is an owned-code, user-mode microbenchmark. There are no secrets, kernel
components, cross-process targets or changes to security/system settings.
All outcomes are unknown until the user collects and supplies evidence.

## Questions and finite scope

K5's frozen three-boot numerical-signature series is complete and unchanged.
It motivates two new questions, not a new interpretation of the old data:

1. Does a dependency on the resolved condition change the public marker
   response differently from matched TEST/CMOV instructions driven by independent
   constants, while preserving the defined architectural operation?
2. How does the response change when specific encoder loads are removed, or
   their bank addresses are changed to private, separately allocated banks?

These interventions constrain explanations for this harness. They do not
uniquely identify a predictor structure, prove an exclusively transient path,
establish instruction fetching, or test user-to-kernel influence. Combining
known control methods here is not a claim of a newly discovered vulnerability.

## Two studies

Every mode uses the same runtime allocation, branch offset, target layout,
256-branch history prefix and calling convention within one process. It is not
the older K5 site: the common prologue now preserves RSI/RDI and prepares ESI=0,
EDI=1 before loading the condition. Exact bytes and actual addresses are saved.
The prefix constrains local history; it is not a verified predictor reset.

Dependency study:

| Mode | Intervention |
|---|---|
| plain | Original marker loads with padding in intervention slots |
| true_mask | TEST of the resolved condition EDX, then CMOV from zero ESI |
| sham_mask | Same TEST/CMOV topology, using independent EDI=1 or ESI=0 flags; preserves the fresh index |
| lfence | LFENCE before each target's token/index/load chain |
| cpuid | CPUID before each target's token/index/load chain |

True/sham variants have identical sizes, instruction topology and architectural
results; their TEST source registers differ. They are a stronger matched
comparison than plain versus a mask alone. Register dependencies and scheduling
still differ, which is precisely the intervention under study. LFENCE and CPUID
are additional observed interventions, not exclusive mechanism diagnoses.
CPUID's LFenceAlwaysSerializing feature bit and hypervisor exposure are recorded.
An absent feature bit does not prove that the operating system left LFENCE
nonserializing. No privileged MSR is read or written.

Receiver study:

| Mode | Intervention |
|---|---|
| plain | Both public encoder loads present |
| ablate_zero | Replace bank0's five-byte encoder load with five-byte MOV EAX,1 |
| ablate_one | Replace bank1's five-byte encoder load with five-byte MOV EAX,2 |
| ablate_both | Apply both replacements |
| sink_both | Keep plain code bytes; bind both encoder base pointers to private banks |

The replacements preserve return values and code length, while changing work
and dependencies. Sink banks are allocated/prefaulted in every mode and all
public/private marker lines are flushed in every episode. The sink comparison
preserves the load instruction but changes its address. Only public wanted and
decoy latencies are measured. It cannot establish measured private-bank heat.

Crucially, each mode applies during both training and probing. Effects are
effects of the entire mode, including changes to training work/cache state.
They are not isolated effects of removing only the final probe's load. No
post-training code patch or pointer remap is introduced to hide that limitation.

## Collection and retained controls

The local plan freezes the clean Git revision, source hashes, policy, compiler
and executable provenance, loaded Python image, host configuration, six seeds
and attempt order before any collector is launched. A separate plan-only ZIP is
written first. This is a local prospective plan, not external preregistration.

There are three preselected repetitions. Each pair contains one dependency and
one receiver attempt in randomized order, with distinct nonzero uint32 seeds.
All six are fresh processes on one unchanged boot/configuration. This is
within-boot process replication, not independent boot/host replication.

Each attempt records 512 blocks, five modes, 16 conditions and four rounds:
163,840 recorded episodes. Eight warmup blocks are unrecorded but included in
the reproducible PRNG state. Total planned recorded episodes: 983,040.

Mode order is randomized within each block, and each round includes all
conditions once in randomized order. Independent reproducible streams select
the schedule and fresh tags/reload order. Each observed row must match the
entire replayed schedule, not merely a cell count.

Both p0 and p1 retain candidate training-match/mismatch, omitted-probe
training-match/mismatch, direct HOT, COLD, architectural load and warm-condition
mismatch cells. Training uses token index zero. Fresh token indices 1..63 are
written after training. All potential marker lines are flushed before probing.
Each wanted reload has a distinct-page decoy and counterbalanced reload order.

p0's probe condition is zero and its queried wrong-path marker is in bank1;
p1 queries bank0. Thus ablate_one targets the p0 response, ablate_zero p1.
The architectural-load cell deliberately takes the opposite branch so it
architecturally reads the queried bank when that encoder is present.

The thread is pinned to one allowed processor. Both RDTSCP AUX values of each
of the two reloads are recorded and must remain one stable observed identity.
AUX is not assumed to equal the Windows processor index. Architectural returns,
observed CPL=3, measured PCs, buffer alignment/disjointness, context bindings,
runtime code, end counts/checksums and event hashes are validated. These local
records are not independent hardware attestation.

## Calibration, gates and analysis

Blocks 0..255 calibrate two thresholds using only direct HOT and COLD data,
pooled over modes separately for p0/p1. The existing deterministic balanced-
accuracy threshold rule is frozen; candidate and intervention outcomes never
fit a threshold. Blocks 256..511 provide all endpoint estimates and gates.

Held-out gates require HOT hits >=95%, COLD/omitted-probe/training-matched
candidate hits <=5%, and every decoy cell <=5%. Architectural-load hits must be
>=95% when its public encoder is present and <=5% when that encoder is removed
or pointed at private banks. Reusing K5's architectural-positive requirement
unchanged would incorrectly reject intended ablations. Warm-mismatch results
are descriptive. Suppression of the candidate effect is never an apparatus gate.

For each mode m and bank p, define the adjusted response:

`A(p,m) = [candidate_mismatch - candidate_match] - [omitted_mismatch - omitted_match]`.

Six confirmatory contrasts are frozen:

| Study | Endpoint | Purpose |
|---|---|---|
| dependency | p0 A(sham_mask)-A(true_mask) | Matched dependency contrast |
| dependency | p0 A(plain)-A(sham_mask) | Equivalence of sham and plain |
| receiver | p0 A(plain)-A(ablate_one) | Bank1 encoder intervention |
| receiver | p1 A(plain)-A(ablate_zero) | Bank0 encoder intervention |
| receiver | p0 A(plain)-A(sink_both) | Public bank1 address intervention |
| receiver | p1 A(plain)-A(sink_both) | Public bank0 address intervention |

Prespecified practical/equivalence margin: 0.10 hit-rate difference, or ten
percentage points. A positive response requires the whole interval above +.10;
an opposite response requires it below -.10; equivalence requires the whole
interval inside [-.10,+.10]. Otherwise the contrast remains unresolved.
Difference from zero alone does not establish a practically relevant result.

The paired bootstrap resamples 16 contiguous held-out blocks as clusters,
preserving all mode/cell pairings, with 2,048 draws and fixed analysis seed
20261108. There are 16 held-out clusters. Each primary interval uses
alpha=.05/6 (approximately 99.1667% nominal confidence), for a Bonferroni
six-contrast family within one scheduled repetition pair. Supporting outcomes
use 95% intervals. No simultaneous 95% coverage is claimed across all three
repetitions. Percentile-bootstrap coverage is approximate; serial dependence
can extend beyond a cluster. No across-host or pooled-episode interval is used.

Per-mode adjusted responses, both banks, ablate_both, untargeted-bank effects,
LFENCE/CPUID responses, warm-condition cells, reload-order strata and episode-
position strata are retained as supporting results. Absence of significance
is not equivalence. A vanished baseline is different from an eligible negative
intervention test and must be identified explicitly. Mixed endpoint patterns
are retained rather than compressed into a blanket success/failure claim.

## Attempts, failures and completion

An attempt receives a unique started record before capture/launch. It consumes
its fixed slot even if collection, analysis or a control fails. Every trace,
stderr, host record and snapshot is retained. There are no replacement seeds,
result-dependent reruns, optional stopping or dropped outliers. An interrupted
unfinished attempt blocks automatic continuation and is packaged for review.

The runner builds once, collects all six planned slots, and packages even a
failure. A repeat invocation validates/packages a completed plan; it does not
start another series. Existing failed builds are retained rather than silently
overwritten. Host/source/runtime changes are recorded as failures, not repaired
by changing this plan. Do not change firmware, VBS, power policy or clock
settings within the series. No restart is required between its processes.

Completion means that the six planned slots and all evidence have been
reviewed. It does not require a positive response. Do not expand the matrix
until these questions have been interpreted and documented. Windows-only
conclusions remain separate from future Ubuntu or physical Fractal results.

## Run and replay

From a clean repository with MSVC x64 Build Tools, Windows SDK and Python 3.10+:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_causal_receiver_windows.ps1
```

The final `READY TO SHARE:` ZIP contains the frozen plan/source, binary and
disassembly, tool/build metadata, six attempt folders, raw traces/snapshots,
host inventories, per-attempt analyses and a replayed summary/manifest. Retain
the plan-only ZIP too. No driver, administrator session or security-setting
change is required by this suite.

Without collecting measurements:

```powershell
py -3 scripts/causal_receiver_study.py package --repo . --folder out/causal-windows-study
```

Per-attempt analyzer:

```powershell
py -3 scripts/analyze_causal_receiver.py out/causal-windows-study/attempt-01/trace.log --binary out/causal-windows-study/build/collector.exe --code-prefix out/causal-windows-study/attempt-01/runtime --json
```

Use the recorded Git revision for exact replay. The Linux development mode
requires an explicit `--development` flag; its traces cannot enter a Windows
study ledger. Software smoke data and synthetic tests are not physical results.
The linked C harness still needs review against the actual user's MSVC build;
matching generated runtime bytes does not automatically attest every C path.

## Sources and relationship to prior work

- Joseph Ravichandran and Mengjia Yan, [Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf).
- [Original K5 protocol](DEPENDENCY_RECEIVER_K5.md) and its completed evidence.
- [AMD64 architecture manuals](https://www.amd.com/en/search/documentation/hub.html), CPUID/CLFLUSH/RDTSCP/LFENCE instruction contracts.
- [AMD software techniques for managing speculation](https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/tuning-guides/software-techniques-for-managing-speculation.pdf).
- [Microsoft generated-code cache synchronization](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-flushinstructioncache).

These are independent methodological follow-ups. Fractal's OS abstractions and
the authors' original M1 results remain credited to their authors.
