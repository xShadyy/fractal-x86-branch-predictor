# B2 v4 fixed-code, three-run replication session

**Status:** frozen follow-up protocol specified after the first B2 v4
physical outcome, before this session's three new host runs. The original
[v4 result](../results/RESULTS_LEDGER.json) was +0.136
[+0.003,+0.272] TSC ticks per complete probe episode and did not cross its
prespecified ±1 practical-association boundary. It is not included as one
of these three replications. The earlier failed B2 v2 pilot and v3 apparatus
diagnostic retain their separate status.

## Question, unit and scope

Does the same B2 v4 executable protocol produce a stable run-level primary
`F(p0,n1)` under three independently seeded attempts in one Windows session?
The run, not the block, is the unit of replication. This tests one day's
same-process x86 timing stability. It cannot establish day-to-day, machine,
ASID or user/kernel behavior, misprediction counts or transient execution.
The study does not alter B2 v4's estimator, controls, probe, branch site,
margin or physical interpretation after viewing its first result.

## Fixed acquisition plan

1. The runner chooses three distinct nonzero uint32 seeds with the operating
   system random generator, or takes exactly three distinct caller-supplied
   seeds. It writes all three and a clean Git revision into a session ledger
   **before** the first build. Neither outcome nor a failed gate can change
   the seeds or number of attempts.
2. Run `check_b2_outcome_windows.ps1 -Seed <seed>` exactly once for each seed,
   in listed order, even if an earlier attempt failed. This rebuilds the same
   frozen source, records its own EXE, trace, disassembly, source/tool hashes,
   control verdict, manifest and ZIP. An unsuccessful build or failed control
   is retained rather than silently retried or replaced.
3. Record all runner outputs, exit codes and original per-run ZIP hashes in a
   session JSON. Package those ZIPs, transcripts, the run-level summary,
   session ledger and a manifest in **one** outer evidence ZIP. A diagnostic
   outer ZIP is produced if the summary or a run fails. The uploader sends
   the single outer ZIP, including unsuccessful attempts.

All attempted binaries require a physical linked-instruction audit before
assigning a mechanism. The aggregator checks nested manifests, EXE and PE
`.text` hashes, source revision, clean Git state, seeds, raw schedule and
architectural checks, and recomputes each complete run's v4 analysis. Its
`same_text_section`, `same_source_hashes`, and `same_host_configuration`
fields must be reviewed; the archive cannot prove the hardware performed
the expected operations merely because software records are consistent.

## Predeclared descriptive readout

Show each run's `F(p0,n1)` 10%-trimmed paired estimate and 95% within-run
40-block-cycle bootstrap interval, each of its 16 apparatus gates, each
run's prespecified ±1 practical verdict, and all three secondary `F`
strata. Count eligible runs whose controls pass. For eligible runs only,
report the median and range of the **three run-level point estimates**.
Keep failed-control estimates visible with an ineligible label, and preserve
failed builds in the attempt ledger. Do not average blocks across runs,
construct a CI from the three within-run intervals, or claim independent
days from one UTC date. If the session crosses UTC midnight, record that
protocol deviation and refrain from calling it a same-day replication.

The informative outcome is whether the run-level estimates agree in sign,
scale and practical status, including recurring near-zero or inconsistent
values. These comparisons are descriptive: selection of this follow-up
after observing the first null run, three runs on one host, and no
between-day uncertainty rule preclude a new confirmatory hardware claim.
Another date would assess day-to-day robustness with a separately logged
session; do not rerun selectively to seek a favorable seed.

## VS Code host procedure

From the clean source revision, choose **Terminal → Run Task → B2 v4
three-run replication (Windows)**. Let all three attempts finish. Upload the
one `out\b2-replication-windows-<UTC timestamp>.zip` after `READY TO SHARE:`
or `Diagnostic evidence ZIP (partial):`; the task may exit nonzero when an
attempt's controls fail. The archive is still the evidence. To check an
archive after extraction on any machine, run
`python scripts/summarize_b2_outcome_replicates.py <outer-zip> --json`.
