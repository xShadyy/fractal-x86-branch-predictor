# Native x86 branch studies: consolidated research record

**Measurements through 8 November 2026; publication review 9 November 2026.** These are Windows x86 measurements on one reported AMD Ryzen 7 9800X3D workstation, plus separate Linux/QEMU development checks and an explicitly separate reanalysis of the Fractal authors' published M1 data. K4 repeats a training-specific fresh-marker cache signature with CPUID sensitivity. K5 has an audited pilot and three completed prospective new-boot attempts. K7/K8 add three planned process attempts per study on one later Windows boot: matched dependency, encoder-load removal and bank-relocation interventions all meet their frozen criteria. The cold-condition sham equivalence has an important warm-condition qualification. No branch-misprediction counter, instruction-fetch receiver or physical privilege-boundary influence was measured in our work. Mechanism attribution remains incomplete.

## K7/K8 audited Windows intervention studies

The [complete K7/K8 record](results/k7-k8-windows-causal/README.md) retains both
original uploaded ZIPs, the frozen plan, all six exact analysis replays,
independent raw-count checks, a targeted review of the actual MSVC binary,
figures and reproduction scripts. The
[protocol](protocols/WINDOWS_CAUSAL_FOLLOWUP.md) and source revision
`8080faed480a9eef086f1fc0396e38dba7de31c7` were fixed before the six attempts.
The supplied plan-only ZIP has an empty attempt ledger and the same plan,
sources and build artifacts as the final evidence. Its local chronology is
consistent with collection, but it was supplied alongside the final ZIP and
is not an externally timestamped preregistration.

Each attempt records 163,840 episodes and passes **140/140 held-out apparatus
gates**, with classification `valid_response`. The six attempts contain
**983,040 recorded episodes**, including **491,520 held-out episodes**. All six
saved analysis objects reproduce exactly; a separate count implementation
matches the 12 thresholds, all 840 gates, 60 adjusted outcomes and 18 primary
point estimates. Source, runtime bytes, bindings, architectural returns and
recorded CPL/PC/AUX checks also agree. The binary was inspected as data and was
not executed during the audit.

K7 compares a true resolved-condition marker-address dependency with an
independent-register sham having matched TEST/CMOV instruction topology.
The primary p0 sham-minus-true effects are +99.902 [+99.609,+100.000],
+99.707 [+98.535,+100.000] and +99.414 [+98.535,+100.000] percentage points.
The p0 plain-minus-sham estimates are -0.098, +0.098 and +0.098 pp; all three
adjusted intervals lie inside the predeclared equivalence margin of -10 to
+10 pp. True-mask, LFENCE and CPUID adjusted responses are zero in the recorded
held-out samples of both banks. Resampling all-zero cluster contrasts yields
zero empirical intervals, not proof of an exactly zero population effect or
a universal serialization guarantee.

K8 removes the queried encoder load, removes the other bank's load, removes
both loads, or retains the plain opcodes while binding the encoder to private
banks. All four prespecified queried-bank ablation/relocation contrasts clear
the +10 pp practical margin in every process; point estimates range from
+99.414 to +100.098 pp. Removing only the other bank's load preserves a large
queried-bank response. The private-bank condition measures loss of the public
response, without a private-bank heat sensor. Corrected contrasts can exceed
100 pp because the no-probe training contrast is subtracted; they are not
individual hit probabilities and are not clipped.

The six primary intervals use the frozen six-contrast Bonferroni rule,
approximately 99.1667% nominal coverage per endpoint and 95% per scheduled
dependency/receiver repetition pair. They resample 16 paired clusters of
16 held-out blocks within each run. This is approximate within-run coverage,
not coverage across all 18 intervals or independent processes, boots or hosts.
The [result table](results/k7-k8-windows-causal/README.md#prespecified-primary-results)
retains every interval; the separate figures use supporting 95% intervals.

Sham equivalence applies to the declared **cold-condition primary endpoint**.
With a warm condition line, p0's supporting sham response is lower than plain
by **15.332, 16.309 and 14.160 pp** across the three dependency attempts.
This exploratory 14.16–16.31 pp difference is outside the confirmatory family
and shows that the sham is not universally inert. The data do not uniquely
identify its cause. The
[warm-condition counts and figure](results/k7-k8-windows-causal/README.md#important-exploratory-qualification-the-warm-condition-sham)
remain part of the result.

These studies strengthen attribution to the tested marker-encoding path.
The selected mode acts during **both training and probing**, so the result
does not isolate a probe-only intervention or prove an exclusively transient
path. All training and probing remain at CPL3. Three fresh processes per study
on one reported boot are not independent-boot replication. Receiver ran before
dependency in every randomly drawn pair, so study order and time are not
counterbalanced. All 1,966,080 wanted/decoy timings are multiples of **47 TSC
ticks**, of unresolved cause. No precise instruction-cycle or unique
branch-predictor mechanism is inferred. This bounded Windows collection is
complete; further hardware work should begin with a new question and a validated
native Linux backend, after inventorying the available laptop.

## K5 audited pilot and K6 privilege harness

[K5](protocols/DEPENDENCY_RECEIVER_K5.md) introduces a resolved-condition
marker-address dependency as a distinct intervention alongside CPUID. Its native
development smoke completed with two failed plain matched-training gates and
remains inconclusive. The failed developmental PC-recording build was corrected
before the Windows pilot. The pilot on 4 November used seed 1143445439 and source
revision `7b5208d14b6cecceb024139e6e0a0fe667549eac`. All 393216 rows replay;
all 88 gates pass, source/artifact hashes verify, and the saved analysis is
reproduced exactly. Primary p0 plain-minus-mask is +99.683 percentage points,
95% within-run interval [+99.414,+99.878]. Mask is +0.000 [0.000,0.000] and
CPUID is +0.000 [-0.073,+0.073]. Recorded CPUID hypervisor=1 agrees with
Windows HypervisorPresent=true. A targeted linked-harness consistency review
found no mismatch in the preparation, shared-site, architectural-return or
reload paths. These observations do not establish a specific predictor mechanism.

The original evidence ZIP SHA256 is
`d059e2a7b588dc328e5d08599061d4b845129801823ed217521ba60d438bf36f`;
the original session ZIP SHA256 is
`f149443349c7a6767e59b5ec16278f2ef777434cb895c43aa5626fffa5c873a8`.
The session wrapper reported an archive-counting error after K5 completed:
its wildcard included the separate source ZIP. That packaging bug was repaired
in `25a7f7d0160298895c798b52d663f77b28230d5d` without modifying the measurements.
The [prospective replication](protocols/DEPENDENCY_RECEIVER_K5_REPLICATION.md)
excludes this exploratory pilot and retains three new fixed-seed attempts on
three new Windows boots. Those attempts completed on 5 November using source
`09d6a7f4da1ceda061cfb07cdca344f282dbcedc`, with seeds 1059577839, 3249956994
and 1849279219. All 88 gates pass in each run. The p0 primary effects are
+99.707031 [+99.511719,+99.877930], +99.609375 [+99.438477,+99.780273] and
+99.829102 [+99.707031,+99.926758] percentage points, with original within-run
95% intervals. All raw analysis and independent cell-count checks reproduce.
The [complete replication record](results/k5-windows-replication/README.md)
retains the original evidence and the same byte-identical plan supplied before
the measurements. The series completes the declared repeatability study, not
mechanism attribution or a user-to-kernel finding.

## Separate reanalysis of the authors' released M1 traces

The evaluated Fractal artifact is separate from the public kernel repository.
Its original experiment backend targets Apple M1/AArch64 and is not a native
Windows x86 program. Its 48 precollected traces can nevertheless be inspected
and reanalysed without owning an M1. The
[portable reanalysis](results/fractal-author-data-reanalysis/README.md) validates
all 240,192 published rows and reports descriptive training-label separation,
with explicit handling of the first four rows and attribution to the original
authors. No new M1 measurements were collected. No arbitrary cutoff converts
the descriptive matrix into inferred hardware pass/fail claims.

The [research-route assessment](RESEARCH_ROUTE.md) records reusable source paths,
upstream/version and licensing distinctions, current Windows profiling/kernel
constraints, physical Fractal boot/export obstacles and published native Linux
research backends. It recommends a bounded conditional-branch domain study,
without assuming AMD must match M1 or that a VM reproduces bare-metal behavior.

## Existing Fractal privilege harness

[K6](protocols/FRACTAL_PRIVILEGE_K6.md) uses actual user and kernel fthreads in
the pinned upstream Fractal x86 OS. The [development record](results/k5-k6-development/README.md)
preserves a complete QEMU TCG smoke: 384 rows, 96 per UU/KK/UK/KU pair, recorded
CS.RPL values 3 and 0 inside the measured routine, common conditional address,
matching runtime bytes, replay and architectural checks. These results validate
the software path only. The physical payload has separate dimensions and rejects
the reported emulation platform. A physical UK interpretation additionally requires
positive UU and KK controls and its own masking/CPUID criteria. No physical K6
signature, production-OS security result, or M1 replication is claimed.

## K3 first Windows pilot and K4 same-host recurrence

The [first K3 Windows pilot](results/k3-fresh-windows/README.md), seed 70098319, completed 131,072 samples. Its original ZIP SHA256 is `f163cb4d912ff33a06edd9660fb95a481ec0d89dfe10359ba9a67162b260d8d9`. All archived hashes, source snapshots, trace replay, architectural returns and RX code snapshots verify. Frozen reanalysis reproduces the archived result exactly: **56/58 gates, inconclusive**, with matched-training NOP receiver rates of 8.936% (p0) and 9.521% (p1), above the <=5% negative limits. The p0 adjusted NOP and interaction estimates are +4.541 percentage points, 95% within-run interval [-6.689,+15.625]. CPUID is 0.000 [0.000,0.000]. The frozen numerical signature is false.

Exploratory episode-position profiles show matched as well as mismatched NOP heat concentrated at grouped-cell entry. These profiles do not replace the primary or justify excluding early samples. The linked-path review verifies the intended architectural invocation/reload structure but also finds different preceding paths into training and probing. It cannot identify the transient predictor target or eliminate alternative cache-fill mechanisms. The runner's original exit 1 was its intentional failed-control check after successful collection.

The [K4 protocol](protocols/CONTEXT_RECEIVER_K4.md) fixes a 256-branch local prefix before each conditional invocation, interleaves conditions and specifies 512 blocks. Its first Windows pilot, seed 888890949, passed 58/58 gates with primary +99.731 [+99.609,+99.829] percentage points. Three follow-up process sessions were then specified in chat using unchanged code and seeds 830217184, 4108945320 and 3039835034. All three also pass 58/58 and detect the frozen numerical signature:

| Follow-up seed | Primary interaction, percentage points | 95% within-run interval |
| --- | --- | --- |
| 830217184 | +99.878 | [+99.756,+99.976] |
| 4108945320 | +99.512 | [+99.292,+99.707] |
| 3039835034 | +99.731 | [+99.609,+99.854] |

The [full K4 record](results/k4-context-windows/README.md) preserves all four original ZIPs, hashes, bounded linked-path review and the distinction between a repeated signature and mechanism attribution. Source snapshots, toolchain records, linked `.text` and RX snapshots match across runs. Every frozen analysis and an independent raw-row primary calculation reproduce exactly. The 786,432 follow-up episodes are dependent measurements within three processes on one reported host, not independent host or day replications. The session count and seeds were fixed before those follow-ups; no additional pooled hypothesis test is claimed. No interval is formed by pooling all episodes across runs.

Training now selects the fresh-marker response at both named target banks, and the CPUID intervention suppresses that response. This supports the transient-execution interpretation, while CPUID's wider effects, host behavior and alternative cache-fill explanations still need further controls. A full native server development check previously failed two gates; that observation remains in the record and is not Windows hardware evidence.

## Relationship to Fractal

[Ravichandran and Yan's *Fractal* paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) develops an OS for low-noise microarchitecture reverse engineering and evaluates Apple M1 branch predictors with instruction-fetch and data-execution receivers across security domains. Its Table 1 reports 48 M1 outcomes: conditional/indirect predictor × performance/efficiency core × ordinary/branch-removed receiver × same user and ASID/user-to-kernel/different ASID × fetch/execution. Those are the authors' findings. The [pinned upstream revision](UPSTREAM_FRACTAL_REVISION) identifies the separate upstream project.

This repository runs ordinary user-mode code in one Windows process on AMD x86. Its TSC and data-cache outcomes cannot reproduce or refute an M1 result. A branch-time difference measures neither speculative instruction fetch nor target execution. A hot data line can support target-execution inference only after target specificity, architectural exclusivity and alternative cache-fill paths are validated.

| Paper category | Local measurement status |
| --- | --- |
| Conditional branch present, same-domain data execution | K1/K3 retain failed negative gates and K2 finds schedule-sensitive heat without trained-label specificity. K4 repeats a training-specific fresh-marker signature; K5 repeats masking/CPUID contrasts on three new boots. K7/K8 meet matched dependency and encoder-intervention criteria in three fresh processes per study on one boot, with a retained warm-condition sham qualification. |
| Indirect branch present, same-domain data execution | I calibrates its receiver but shows no convincing opposite-target signal; H's small-work sensitivity fails. |
| Instruction fetch, including proposed J | No target-specific isolated instruction-cache receiver. J is unimplemented; whole-call timing would not isolate fetch. |
| Branch removed / Phantom | No audited same-address branch-to-NOP receiver experiment. Unimplemented. |
| User-to-kernel, different ASID, M1 core classes, Fractal scheduler/gmap | Untested here. The 9800X3D does not supply M1 performance/efficiency core classes. |

## Host, evidence, and statistical rules

Archived snapshots and later traces identify AMD Ryzen 7 9800X3D, `AuthenticAMD` signature `0x00b40f40`, Windows 11 Pro build 26200, reported hypervisor presence, and process affinity to logical CPU 0. K7/K8 record build 26200.9168, BIOS FA9, raw microcode bytes `3540400b`, Balanced power plan, VBS status 2 and one reported boot beginning 8 November at 11:32:04.5000000Z. Before/after inventories match that plan. These records do not establish every security feature's state or independently attest hardware execution. Constant TSC_AUX=0 under the reported hypervisor is a weak independent migration witness. The exposed LFENCE-always-serializing bit is zero; this does not determine the actual LFENCE configuration or turn observed suppression into a universal guarantee.

Earlier batch totals show a 47-TSC-tick GCD. The independent K7/K8 count audit finds that every recorded wanted and decoy timing is also a multiple of 47 ticks; calibration HOT medians are 94 ticks and COLD medians 470 ticks. Held-out class separation passes, while the cause of this quantization remains unknown. TSC differences must not be treated as precise instruction-cycle measurements. SMT-sibling load, thermal/frequency drift and competing work were not independently controlled; the studies do not vary microcode or mitigation settings to establish their effects.

Randomized complete blocks, frozen gates, held-out calibration, raw traces, executable hashes, and linked PE inspection constrain interpretations. Earlier 95% intervals and the K7/K8 adjusted primary intervals resample complete block cycles **within one run**. They are not intervals across runs, dates, hosts, or a processor population. K7/K8's six-endpoint family concerns one scheduled repetition pair; it does not supply simultaneous coverage across all three repetitions. A zero-containing interval is not proof of equivalence; a pilot-informed follow-up is not independent confirmation of the pilot. The [machine-readable results ledger](results/RESULTS_LEDGER.json) preserves archive identifiers, evidence locations, and a digest of historical reports. ZIP SHA/CRC, manifest, strict replay, source tree, and `.text` checks establish internal consistency, not independent attestation of host conditions.

## A and B: two-date timing replication

Each study had one separate pilot, then six complete distinct-seed runs: three on 30 October and three on 31 October. A's primary estimand is the paired shuffled-versus-periodic live-stream interaction under live versus fixed branch decisions, divided by 8,192 iterations. It requires three negative-control **whole intervals** inside ±0.5 TSC ticks/iteration and an added-work timer gate. B subtracts branchless-sham mismatch-minus-match training from same-branch-site training **within each block**, separately for fixed 16-call probe outcomes 0 and 1. B's added-work timer is its formal gate; the original plan had no numerical pass/fail gate for a bidirectional effect.

| Date and study | Three run estimates | Verdict |
| --- | --- | --- |
| 30 Oct, A | +16.850, +17.040, +17.167 ticks/iteration | All negative and timer controls pass. |
| 31 Oct, A | +16.936, +17.047, +17.064 ticks/iteration | All controls pass; descriptive day means +17.019 and +17.016. |
| 30 Oct, B probe 0 | +4.468, +2.781, +2.048 ticks/fixed probe | All within-run intervals above zero, timer passes. |
| 31 Oct, B probe 0 | +2.555, +2.441, +2.048 ticks/fixed probe | All intervals above zero, timer passes; day means +3.099 and +2.348. |
| 30/31 Oct, B probe 1 | −1.256, −0.123, +0.075 / +0.283, +0.832, −0.590 ticks/fixed probe | All six intervals include zero; no bidirectional crossover. |

All 12 traces replay strictly and match their EXE hashes. The six A executable `.text` hashes match the audited pilot's `0f302df7d38b2c1e1eb840104cd4c51da4d0d802a8e540ee74fd8d20a11ec1e9`; B's six match `b7ee4707628ac45f621ffd281066efd0cff3652717324fe3baa7c592c8289e3b`. Static PE inspection locates A's conditional jump at RVA `0x1c05` and B's at `0x1c85`. B's sham uses another address and its 16-call probe can itself change the state sampled. A's controls narrow input-processing explanations; neither study counts branch misses. Day 1 ran A then B, day 2 B then A: day and order effects remain confounded. The [full run summary](results/2026-10-30-31-windows-followup-replication/series-summary.json), [original-file hashes](results/2026-10-30-31-windows-followup-replication/original-file-sha256.json), [raw sessions](results/2026-10-30-31-windows-followup-replication/), and [figure](results/2026-10-30-31-windows-followup-replication/followup-replication.svg) retain details; figure whiskers are within-run intervals.

## Fourteen-study exploratory suite, 31 October

The one-session archive `suite-evidence-suite-20261031T213948Z-8ee83ab7.zip`, SHA-256 `e595d4fb38638961d4c9a2a8eb0ee1f25789b2899cb668a02989d4ec5e2ba40e`, contains 14 paired EXE/traces among 78 members. Manifest and replay checks passed. Ten checks were accepted; four failed declared controls and stay **inconclusive**. These are pilots, not 14 replications. Bracketed ranges below are 95% within-run intervals, in each row's unit.

| Study | Gate | Pilot observation and boundary |
| --- | --- | --- |
| Cache controls | Pass | Held-out hot 100%, cold 0%, architectural load 100%, skip 0%. |
| Conditional cache receiver | Pass controls | Trained-taken/not-taken opposite-line hits 0.2%/0.0%; no convincing target signal. |
| Branch batch | Pass | Adjusted shuffled minus periodic +16.421 [+16.283,+16.879] ticks/iteration; no-load ablation uses another branch address. |
| Single-branch latency | Valid diagnostic | Probe 0 +0.4 [−0.4,+1.4], probe 1 −0.3 [−1.2,+0.6] ticks; few-tick sensitivity unestablished. |
| A decision source | Pass | +17.196 [+16.857,+18.218] ticks/iteration; three practical negatives and timer pass. |
| B1 history | Pass timer | Adjusted probe 0 +2.99 [+1.04,+5.03], probe 1 +0.90 [−1.10,+2.85] ticks/fixed 16-call probe; no crossover. |
| L prelude sweep | **Inconclusive** | Fixed-trainer equivalence fails ±1 gate; prelude contrasts include zero. No path-history length inferred. |
| D intervening activity | Pass | Filler counts 0/16/64/256 yield no resolved difference; no retention depth identified. |
| E training dose | **Inconclusive** | Small-work sensitivity and fixed/zero-dose equivalence fail; no dose threshold inferred. |
| C pattern complexity | Pass | Preselected period-2 versus period-32 −0.0023 ticks/iteration, interval includes zero. Exploratory shuffled versus period-32 +18.261 [+18.107,+18.388] with controls passing. |
| F address sensitivity | Pass controls | Planned same-4K versus offset-128 probe interactions −0.590 [−1.361,+0.148] and +0.447 [−0.748,+1.783] ticks/probe; runtime copies not independently dumped, no index bit inferred. |
| I indirect cache receiver | Pass controls | Opposite-target changes −0.6%/+0.2%, no convincing signal; target 1 shares an instruction line with sham. |
| H indirect target timing | **Inconclusive** | Small-work controls +0.008/+0.143 ticks/probe, intervals include zero; PAUSE alone does not validate fine-scale sensitivity. |
| B2 original probe length | **Inconclusive** | Probe-1 one-call timer +0.318 [+0.036,+0.587], below frozen +1 magnitude gate; probe-0 +1.116 [+0.669,+1.524] is exploratory only. |

Archived linked-PE inspection supports intended branch/timer/target topology, subject to F's runtime copies and I's fetch-line and exclusivity caveats. An RX copy is not Fractal's gmap. Heterogeneous endpoints and failed gates cannot be pooled into a common effect.

## B2: same-site probe outcome

The original B2 pilot's failed gate was retained. [Calibration v2](protocols/B2_CALIBRATION_V2.md) tested apparatus only and failed three 16-call baseline-equivalence intervals despite detectable added work. [Precision v3](protocols/B2_PRECISION_V3.md) changed apparatus under a new frozen protocol and passed 16/16 gates, without collecting a training outcome. [Outcome v4](protocols/B2_OUTCOME_V4.md) then tested one primary real-minus-fixed training interaction at the **same conditional branch site**: probe outcome 0, one probe call, TSC ticks per **complete episode**. Its practical association rule required the whole interval beyond +1 or −1 tick. Fixed-decision training is an ablation, not a predictor-free intervention.

| Stage | Original ZIP SHA-256 | Apparatus | Outcome |
| --- | --- | --- | --- |
| v2 calibration pilot | `9c71dca5d33c1751bfedcf759aa9eb5e5789b53a40ce8b8e437da449c840abce` | Three baseline-equivalence intervals fail | No training endpoint. |
| v3 precision pilot | `d956fc935b24e547154d1979eac1d6a873a7b9d7ce708f3920baf205f1cc88c1` | 16/16 pass | No training endpoint. |
| v4 initial outcome, 1 Nov | `2e52aaffa916e575976fbf81aab7d907173b35945c7985adc8c44d71d3005f35` | 16/16 pass | +0.136 [+0.003,+0.272] ticks/episode. Excludes zero within run, remains below +1 rule. |
| [Three-run v4 replication](protocols/B2_REPLICATION_V1.md), same date | Outer ZIP `805ff9fdb9a02d378e834d1dff0125c58a1c735df5d9c8390a1ecf7196ad5c6d` | 16/16 pass in each | −0.0479 [−0.1919,+0.0937]; +0.0060 [−0.1219,+0.1308]; +0.0397 [−0.0692,+0.1454]. None clears ±1 rule. |

The initial and replication `.text` sections match SHA-256 `1289fa0d276ca798fdf80b0319730d97fc19391e85f78d71c64e96f62c3b947e`; the linked jump is at PE RVA `0x20f5`. All four outcome runs were on one UTC date; replication was chosen after seeing the initial outcome. The tiny first-run exclusion of zero is neither practical association under its frozen gate nor day-level confirmation. PAUSE detects much larger added work; calibrated `dose4` checks a few-tick scale. Pair carryover, host behavior and the observed timing lattice remain unresolved.

## K1: conditional data-cache receiver

[K1's frozen protocol](protocols/CONDITIONAL_RECEIVER_V1.md) aimed to detect a trained but architecturally skipped conditional target by its data-cache line. Two earlier MASM `A2006` attempts stopped at assembly and yielded **no measurement**. One independently checked failed-build ZIP has SHA-256 `81ad2a549331531096356d20d3997a1e1556c6a6582bb595cd26a927328252b2`; the second user-reported failed-build ZIP has SHA-256 `58e2af84ee2d786451d9d555c0b161dbc32683f9b48ada7c56c3ab7ad66d7d92`, without independent ZIP verification. The corrected executable completed 512 blocks, 64 raw episodes per condition. Original ZIP `conditional-receiver-windows-20261101T172116138Z.zip`, SHA-256 `4d5ce4aa5a4c13460abecfec4563e74a400203d452c134072697bfac6acf506f`.

Held-out hot 99.82/99.92%, cold ≤0.006%, architectural load 99.88/99.87%, and no-probe ≤0.006% passed. **Architectural skip was 8.25%/8.06%, above K1's frozen ≤5% gate in both directions.** Adjusted mismatch-minus-match estimates were +0.75 [−1.97,+3.05] and +2.66 [−1.82,+7.47] percentage points. K1 is **inconclusive**, neither an eligible positive nor an eligible null; strict exit code 1 reflects the failed gate. Dropping hot first episodes retrospectively would violate its protocol.

Linked PE inspection maps K1's shared conditional branch to RVA `0x2030`, target bodies to `0x20c2`/`0x203d`, and condition/target data to separate pages. Flush, fence, and fenced reload occur in the path. The optimized collector has a branch into HOT's explicit touch after flush; speculation along that harness branch is one possible contaminant. Target code-fetch layout is asymmetric. A post hoc first-five-episode spike motivated K2, but cannot repair K1's gate or establish its cause.

## K2: receiver order diagnostic

[K2's protocol](protocols/RECEIVER_ORDER_K2.md) compares grouped 64-episode cells with interleaved scheduling at one conditional branch and two target data pages. There are 16 warmup and 256 recorded complete blocks; the first 128 calibrate thresholds and final 128 are held out. Its 20 hot/cold/architectural-load/no-probe apparatus gates differ from K1's: architectural **skip is an outcome, not a gate**. The frozen primary is the within-block grouped probe-0 first-five minus later-59 skip-hit rate. A within-run 16-block-cycle bootstrap interval entirely above +10 percentage points classifies a *condition-entry association for that run*, not trained-target recovery.

| UTC start, seed | Original ZIP SHA-256 | Gates | Primary grouped p0 early minus late, within-run 95% interval | Grouped p1 early minus late | Full-cell skip, grouped p0/p1; interleaved p0/p1 |
| --- | --- | --- | --- | --- | --- |
| 1 Nov 18:31:45, `1992600106` | `7d464c02af3e13e0051ed771756bcf8c220143d0a40226e85d9e598b50260cb5` | 20/20 | **+31.15 [10.99,53.65] pp** | +43.84 [25.25,60.65] pp | 2.69/3.49%; 61.06/46.15% |
| 1 Nov 19:25:10, `1644643828` | `46403c95f5c3754ec41dc729d514ee06ed050950dfe6791f1360ebfe23acb96c` | 20/20 | **+50.37 [34.81,63.63] pp** | +47.39 [33.46,57.71] pp | 4.19/3.81%; 57.68/47.06% |
| 2 Nov 19:05:23, `2013934917` | `16065ccdac9bff43280fc48c1db89e236682f84940b95a42f25913d4e1326b4f` | 20/20 | **+56.51 [42.39,65.93] pp** | +46.61 [21.48,68.67] pp | 4.63/3.75%; 63.83/52.21% |

All three clear K2's **within-run entry rule** on one host across two UTC dates. Grouped p0 early/late rates were 31.41/0.25%, 50.63/0.25%, and 56.72/0.21%. The eight held-out cycles per run vary widely and the interleaved skip line is often hot. The three distinct-seed runs are observations of between-session recurrence; no three-run confidence interval or population estimate is inferred from the many dependent episodes. K2 was designed from K1's exploratory spike, so K1 and K2 are not independent mechanism discovery and confirmation.

Every K2 candidate **trained-label mismatch-minus-match** interval includes zero in grouped and interleaved modes on all dates. Day-two grouped p1, for example, was +1.343 [−0.024,+3.088] pp. The day-two p1 threshold was 258 ticks versus p0 352; an exploratory 188-tick reclassification preserves the main schedule pattern but does not replace frozen calibration. High skip-line heat could involve branch-path activity, prefetch, global history, condition ordering, harness behavior or host state. It does **not** demonstrate which trained target was selected, misprediction, or transient target execution.

The three linked `.text` sections are byte-identical, SHA-256 `54d9af2ea69a7acff3ba2a57e1872550f15b2a3455b1d5046be49dd08fda12c8`; full PE hashes differ in timestamps. Static review maps the shared branch to RVA `0x2680`, targets to `0x2712`/`0x268d`, and condition/target data to distinct pages. HOT uses a separate explicit-touch helper; candidate/skip use flush/fence/branch/fenced reload. Target one shares an instruction line with the branch, whereas target zero has another fetch layout. This verifies intended topology, not the causal source of heat. The [three-run figure](results/2026-11-02-windows-receiver-order-day2/three-run-contrast.svg) and [plot source](results/2026-11-02-windows-receiver-order-day2/plot_three_runs.py) display run-level outcomes without treating episodes as independent replications.

## Provenance, reproduction, and inference

Raw A/B and branch-batch traces/binaries, JSON summaries, plot scripts and original-file ledgers are under [results/](results/). The suite/B2/K1/K2 original ZIPs were supplied separately; their exact hashes appear here and in the [results ledger](results/RESULTS_LEDGER.json). For an original ZIP, verify SHA-256 and manifest, replay the matching `scripts/analyze_*.py` against its `.log` at the recorded source tree, and compare executable and linked `.text` hashes. `scripts/summarize_followup_series.py` recomputes A/B from raw files, and `scripts/summarize_b2_outcome_replicates.py` reads the B2 outer ZIP. Unit tests check parsing and analysis, not physical host execution.

The supported observations include the earlier A/B timing and K2 scheduling associations, the retained B2/K1/K3 limits, K4's repeated training-specific fresh-marker signature, K5's three new-boot masking/CPUID contrasts, and K7/K8's matched dependency and encoder-intervention results. The latter strengthen attribution to the tested encoding path while retaining the warm-condition sham difference and the fact that interventions act during training and probing. Mechanism attribution remains bounded by host, timing and alternative-path questions. No predictor table size, path-history-register length, misprediction count, privilege/ASID transfer, Phantom effect or M1 finding is established. The bounded Windows phase is complete. Native Linux host selection requires the available laptop's CPU inventory; physical Fractal boot/export and privilege-boundary experiments remain separate, unvalidated hardware work.
