# K5 Windows replication, version 1

Prospective plan prepared 4 November 2026 after review of the exploratory K5
pilot, before any of the three new measurements. This is an independent x86
study informed by Fractal, not an exact replication of the Fractal paper.

## Research target

On the reported Ryzen 7 9800X3D running Windows 11 with a hypervisor present,
does the frozen K5 user-mode marker response repeat across three new Windows
boots, and remain suppressed by both resolved-condition masking and CPUID?
The exploratory pilot (seed 1143445439, evidence SHA256
`d059e2a7b588dc328e5d08599061d4b845129801823ed217521ba60d438bf36f`)
does not count toward this prospective set.

This is a fixed three-attempt engineering replication on one host/configuration.
Three boots are not evidence of between-host generality, and the sample count
does not turn a single run into independent host replications. Boot identities
come from Windows inventory and are not independently attested.

## Choices frozen before collection

The first invocation creates `out/k5-replication/plan.json`, its SHA256, an exact
source snapshot, and all three distinct nonzero seeds using the OS random source.
The pilot seed is excluded. No measurement starts during plan creation. The plan
is a local prospective record, not an independently timestamped preregistration.

Each attempt requires a different recorded Windows boot after plan creation,
the same clean Git revision and source hashes, the same recorded host identity,
and the same recorded CPU/Windows/firmware/microcode/hypervisor configuration.
Compiler, linker and disassembler versions and hashes are recorded before and
after collection; Python's version/executable hash is fixed for the series.
Inherited CL/_CL_ compiler-option overrides are rejected. Address layouts may
vary across boots, while each run must retain its single measured branch PC.
Use Windows Restart between attempts; sleep or hibernation does not create a
new boot. The runner does not reboot the computer or change security settings.

The original C collector, runtime code, K5 protocol and analyzer stay byte-for-
byte unchanged after LF newline normalization. Each run retains 393216 episodes,
512 blocks and 16 rounds. Its first 256 blocks calibrate thresholds and its last
256 blocks provide the held-out estimates. All 88 gates, 5 percentage-point
margins, primary p0 plain-minus-mask endpoint, CPUID equivalence requirement,
bootstrap settings and secondary p1 designation remain as in K5 version 1.

## Attempt and stopping rules

Run exactly one attempt on each of three new boots. An attempt consumes its
ordinal and planned seed when `started.json` is written, before launching K5.
Its files are retained even if compilation, collection, controls or packaging
fail. Interrupted attempts consume their slots and are marked inconclusive.
There are no automatic retries, replacement seeds, extra attempts after seeing
the result, or early stopping after a desirable result. Finish the fixed plan
even if a prior completed attempt is null or fails a scientific control.

Repeated invocations on the same boot do not launch another measurement. After
three slots have been used, the same task validates/packages existing evidence.
The separate audit task always validates/packages without collecting.

## Validation and decision rules

For every complete archive, independently check the artifact manifest, source
snapshot, Git revision, planned seed, executable hash, all three runtime byte
snapshots, schedule replay, actual CPL/PC records, end checksum and event hash.
Replay the frozen analysis from the raw trace and require equality with the
saved analysis. Missing, extra, ambiguous, altered or emulated evidence cannot
count as a successful replication. Source snapshots are never counted as a
second complete evidence ZIP. All runs must report Windows and the expected
CPU signature/hypervisor state. Every attempt remains in the aggregate.

| Three-attempt outcome | Aggregate classification |
|---|---|
| All three validated, all controls pass, all frozen numerical signatures positive | Replicated K5 numerical signature on this host/configuration |
| All validated and controls pass, none has a signature | No K5 numerical signature in three valid runs |
| All validated and controls pass, signatures differ across runs | Not consistently replicated |
| Any scientific control fails | Inconclusive due to failed controls |
| Any software failure, interruption, invalid or missing archive | Inconclusive due to invalid/missing evidence |
| Boot, source, identity or configuration rules violated | Inconclusive due to protocol deviation |
| Fewer than three recorded attempts | Pending sessions |

Report per-run effect sizes and within-run intervals. A mean and range across
validated runs are descriptive only; no pooled confidence interval is used to
make the result look more precise or to rescue a failed run. A null result does
not establish absence of speculation. Scientific inconclusiveness does not
permit replacing a run. A later experiment needs a separately declared plan.

## Relation to the scientific paper

Joseph Ravichandran and Mengjia Yan, *Fractal: An Operating System Designed for
Microarchitecture Reverse Engineering*, IEEE S&P 2026:
https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf
Upstream: https://github.com/jprx/fractal

The paper evaluates Apple M1 under Fractal, including cross-privilege and ASID
experiments and Phantom speculative fetches. K5 uses a conditional instruction,
stays at CPL 3, runs on Ryzen/Windows, and observes data-cache markers. Therefore
even three positive K5 sessions do not reproduce the paper's M1, Phantom,
cross-privilege, ASID-isolation or OS-comparison claims. They support only the
specified Windows K5 repeatability result. The exact predictor structure and
mechanism still need separate evidence; K6 physical collection remains pending.

No output label ever marks the paper, a security-boundary break, or a complete
physical mechanism as proven. Software fixture tests validate the workflow;
they are not new processor measurements.
