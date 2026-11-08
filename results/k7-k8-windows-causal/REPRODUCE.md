# K7/K8 audit reproduction and file guide

Read [README.md](README.md) for the measured conclusion, all primary intervals, figures,
warm-condition qualification and limits. `SUMMARY.json` is the short record.
The bounded six-attempt Windows plan is complete. No additional Windows
collection is needed to finish it.

## Contents

- `inputs/`: both original user-uploaded evidence ZIPs, copied byte for byte.
- `integrity.json`: both manifests, frozen plan/build/source continuity,
  source-to-Git comparison, ledger, chronological and host-inventory checks.
- `replay.json` and `attempt-*-replayed-analysis.json`: exact frozen-analysis
  replay results. Every saved analysis matched.
- `endpoint-table.csv`: all 18 primary effects and frozen adjusted intervals.
- `supporting-mode-table.csv`: all 60 per-mode/bank supporting responses.
- `independent-counts/`: separate histogram/count implementation and full cell
  counts, gate comparisons, strata and timing-quantization findings.
- `static/`: MSVC PE/disassembly/runtime-code review and its mechanical script.
- `*.png`, `*.pdf`, `*.svg`, `make_figures.py`: supporting figures and their
  source. Figure intervals are labeled separately from primary intervals.

The review ran trusted analysis code and read evidence binaries as bytes.
No uploaded executable, object file or runtime machine code was executed.
This package is an audit record, not an installer or another collection task.

## Recheck the original archives

Run from this result directory with Python 3 and Git. The repository is two
directories above it, and the recorded Git commit must exist locally. If this
record is copied outside the checkout, replace `../..` with the actual repository
path. Recheck outputs go to `out/` so the published audit files stay unchanged.

```text
python audit_integrity.py --repo ../.. --final inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --prior inputs/causal-plan-20261108T173628840158Z-ddcc9de4.zip --output ../../out/k7-k8-integrity-recheck
python independent-counts/audit_counts.py inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output ../../out/k7-k8-counts-recheck
```

These checks do not execute the collector. The independent count script uses
Python's standard library and does not import the project's analyzer. It checks
point estimates/counts, not confidence intervals. Frozen-analysis replay checks
the saved confidence intervals separately.

For frozen-analysis replay, use revision
`8080faed480a9eef086f1fc0396e38dba7de31c7`, extract the final evidence ZIP to a
fresh folder, and run that revision's `scripts/analyze_causal_receiver.py`
on each `attempt-XX/trace.log`, supplying `--binary build/collector.exe` and
`--code-prefix attempt-XX/runtime` with the appropriate full paths. Do not
use a modified later analyzer to silently reinterpret the frozen study.

The static script additionally needs GNU binutils for independent decoding and
the same frozen repository plus extracted evidence. Its `--repo`, `--evidence`
and `--output` arguments replace the recorded review-environment paths.

Keep the two input archives unchanged. `FILES-SHA256.json` inventories this
audit package. Local hashes/metadata support consistency, not independent
hardware attestation or an external preregistration timestamp.
