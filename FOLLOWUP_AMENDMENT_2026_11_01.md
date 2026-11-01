# Focus follow-up schedule amendment, 1 November 2026

This amendment is recorded after reviewing the first Focus session and before
using further sessions for the planned six-session summary. It changes the
collection dates and automatic evidence packaging only. The A/C endpoints,
controls, study executables, analyzers, compiler flags and interpretation
limits in [the original protocol](FOLLOWUP_2026_10_31.md) remain frozen.

## Attempt already observed

The 31 October session began at `2026-10-31T23:16:01Z`, with Git HEAD
`ede57625d329a367738c16d67f5f712a5276f74e`. Its complete 49-file
evidence archive, `suite-evidence-suite-20261031T231601Z-90e68294.zip`,
has SHA-256 `bf9466c5c852f3aed2e4460a63b8ed24a190c0cb90cdcee4a72a9da7af17b737`.
The evidence auditor verified 47 distinct recorded files. Nine studies were
attempted: seven passed strict software checks; F and B2 were retained with
inconclusive controls. A and C passed their gates. The new C contrast was
`+18.286888` ticks per iteration, with a within-run interval
`[+18.203697, +18.590517]`. This is an eligible observed run, but it cannot
complete the original requirement of three sessions on 31 October UTC.

Keep this session as **additional attempt 0** in the full ledger. It is never
silently discarded, relabeled as a pilot, or substituted for a failing run.
It does not enter the following six-session primary summary because the
planned two-date schedule could not be completed with 31 October as one date.
The change is logistical and was made after seeing its result, so report that
timing and the result when describing the amendment.

## Six planned sessions

Collect three independent one-round Focus invocations on **1 November 2026
UTC**, and three on **2 November 2026 UTC**, for six new sessions. These are
sessions 1–6. Record the actual UTC start and end of each; a date labels a
cluster, not an independent observation for every block. If this schedule
becomes impossible, preserve all attempts and document a new prospective
change before collecting more, without retrospectively assigning convenient
dates or dropping results.

After importing this orchestration-only revision, run the VS Code task
**Focused Windows follow-up session** once per session. It saves the final
session record and automatically packages the exact session's original traces,
executables, host snapshot, sidecars, transcripts and available disassemblies
into one `out/suite-evidence-suite-*.zip`. The console prints `READY TO SHARE:`
with the full path. Upload that one ZIP. A nonzero task exit caused by failed
control gates does not invalidate the archive; retain the failure and ZIP.
If automatic packaging fails, the console explains why and the original
`out/suite-*/session.json` remains available for a manual packaging attempt.

The new Git revision changes runner packaging and documentation, not the
measurement or analysis routines. Compare each run's recorded source hashes,
binary `.text` hashes, physical instruction paths and toolchain before
aggregating across revisions. Do not assume an unchanged estimate solely
because an executable name matches.

## Reporting

Run the follow-up summarizer on the six planned ZIPs only for the primary
run-level and date-level descriptive summary. Run it separately on all seven
ZIPs, including attempt 0, for a complete attempt ledger and sensitivity
description. State which input archives went into each analysis. Do not treat
within-run bootstrap intervals as confidence intervals over days or hosts.
The original pilot remains excluded from both follow-up summaries.
