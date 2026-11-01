# Classify failed Focus suite runs

`scripts/classify_suite_failures.py` reads an existing canonical
`suite-evidence-suite-*.zip`. It calls `audit_suite_evidence.audit` first, then
replays the archived failed traces with the repository's **non-strict** Python
analyzers. The ZIP and archived executables are never changed or executed.

From the repository directory in VS Code PowerShell:

```powershell
py -3 .\scripts\classify_suite_failures.py .\out\suite-evidence-suite-YYYYMMDDTHHMMSSZ-ID.zip
```

Replace the ZIP path with the actual archive path. Add `--json` for a
machine-readable report. The command exits `0` for an audited archive (even
when it contains failed runs), or `2` if archive integrity fails. If integrity
fails, it reports the auditor's problems and **does not replay traces**. Run
the command on each ZIP separately; it does not pool observations across runs.

| Category | Meaning |
| --- | --- |
| `completed_control_inconclusive` | The archive is internally consistent, there is exactly one matching trace and executable, the non-strict analyzer parsed the trace, and an explicitly declared control gate failed. The trace is retained as an exploratory observation; it is not a passing controlled result. |
| `invalid_trace` | The non-strict analyzer rejected the trace's syntax or protocol. No result can be inferred from its gate values. |
| `missing_build_or_run_pair` | The failed run did not record a unique, matched `.log` and `.exe` pair. This includes a build or run failure with no output. |
| `inconsistent_record_requires_review` | The failed record has a parseable trace and all declared control gates pass; the failure may have happened in a later step. Inspect the original transcript and recorded error. |
| `unsupported_study` | The study has no registered replay/gate mapping in this classifier. Its original status and error remain available. |
| `analyzer_replay_requires_review` | The analyzer crashed, timed out, or exited for a reason other than an explicit invalid-trace parse error. |
| `analyzer_result_requires_review` | The analyzer returned malformed JSON, missing gates, or contradictory overall and detailed gate flags. |

An archive with a missing or tampered **declared** artifact fails the integrity
audit and does not enter the run classification above. This prevents a forged
or mismatched trace from being called a completed experiment. A failed record
that simply never declared a trace/EXE pair can still pass the archive audit
and be classified as `missing_build_or_run_pair`.

The supported studies are `history_b2` (timer and fixed-neutral gates),
`address_sensitivity` (timer and fixed-decision gates), and `branch_batch`
(timer positive control). Each JSON entry retains `status`, `error`, study,
stage, round, position, and the failed gate names when present. These are
within-run control checks. Their classification does not establish branch
mispredictions, predictor aliasing, cross-privilege behavior, or confirmation
or refutation of the Fractal paper. Analyzer behavior is tied to the current
checkout; retain its Git commit alongside the original archive for replay.
