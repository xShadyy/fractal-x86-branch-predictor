# x86 Branch Predictor Experiments

Controlled branch and cache measurements on an AMD Ryzen 7 9800X3D running Windows x64. This is independent work inspired by Joseph Ravichandran and Mengjia Yan's [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf). Their [Fractal operating system](https://github.com/jprx/fractal) and Apple M1 findings are credited to the authors. The upstream revision used for development is pinned in [`UPSTREAM_FRACTAL_REVISION`](UPSTREAM_FRACTAL_REVISION).

The Windows studies in this repository run in one ordinary user-mode process. They do not boot Fractal, cross a user/kernel boundary, or reproduce the paper's M1 results. Timing and cache-hit differences alone do not identify mispredictions or transient execution.

## Current evidence

[K5](protocols/DEPENDENCY_RECEIVER_K5.md) adds a distinct resolved-condition
marker-address dependency alongside plain and CPUID modes. Its Windows pilot is
pending. [K6](protocols/FRACTAL_PRIVILEGE_K6.md) supplies a pinned Fractal x86
payload for user/user, kernel/kernel, user/kernel and kernel/user pairs. The
recorded [QEMU smoke](results/k5-k6-development/README.md) verifies actual CPLs
and a common measured instruction address across all four pairs. Physical K6
collection and user-to-kernel influence remain untested; emulation is not
branch-predictor evidence. The new runners preserve all nulls and failures.

[K4](results/k4-context-windows/README.md) now has one Windows pilot and three preselected follow-up process sessions. All four pass 58/58 controls and detect the frozen training-specific fresh-marker signature. Follow-up primary effects are +99.878, +99.512 and +99.731 percentage points. They establish recurrence on one reported host within minutes; mechanism attribution and the Fractal privilege-boundary question remain open.

The K2 conditional-receiver diagnostic has three physical runs with different seeds on one Windows host, spanning two UTC dates. All 20 apparatus gates passed in each run. Its prespecified grouped condition-entry contrast recurred, while the candidate comparisons did not establish which target had been trained. The unexpectedly high interleaved architectural-skip hit rate remains unexplained. The earlier K1 receiver failed its separate skip-control gate and remains inconclusive.

The [research report](RESEARCH_REPORT.md) gives the measured results, links to raw evidence and analysis code, instruction audits, limits and a claim ledger. Frozen protocols for [K1](protocols/CONDITIONAL_RECEIVER_V1.md), [K2](protocols/RECEIVER_ORDER_K2.md), and the [B2 outcome](protocols/B2_OUTCOME_V4.md) and [replication](protocols/B2_REPLICATION_V1.md) studies retain the decisions made before their respective measurements. Original evidence ZIPs should be kept unchanged.

## K3 Windows pilot and K4 results

The first [K3 Windows pilot](results/k3-fresh-windows/README.md) completed 131,072 samples. Its original ZIP, source snapshot and frozen analysis verify, but two matched-training negatives failed: 8.94% and 9.52% hits against a 5% maximum. The primary interval includes zero. K3 remains inconclusive. Cache hits cluster near grouped-cell entry, including with matched training; the linked harness also reaches training and probing through different preceding branch paths.

The separate [K4 protocol](protocols/CONTEXT_RECEIVER_K4.md) adds an identical 256-branch prefix to every training and probe call and interleaves conditions. Its [Windows series](results/k4-context-windows/README.md) passes the frozen gates in every run, with identical source hashes, linked code and RX snapshots. K4 constrains local context; it does not establish a predictor reset. Earlier native server development checks still failed their matched-candidate gates and remain in the record.

The [series auditor](scripts/audit_context_receiver_series.py) reproduces every original analysis and independently recomputes the primary from raw rows. The recorded count and seeds were specified in chat after the pilot and before the follow-ups; all intervals remain within-run. The supported observation is a repeated same-process signature, with further mechanism controls required. Existing measurement code and criteria are unchanged.

Both runners report collection status separately from scientific validity. An inconclusive completed run prints its failed gates and returns zero by default; add `-RequireValidControls` to make it a failing automation gate. Build, runtime and invalid-evidence errors remain failures. No exit code establishes transient execution.

## Run on Windows in VS Code

1. Install [VS Code](https://code.visualstudio.com/), Visual Studio Build Tools with **Desktop development with C++** and a Windows SDK, and Python 3.
2. Open this repository in VS Code. Select **Terminal → Run Task → K4 context-prefix diagnostic (Windows)** for the current apparatus follow-up.
3. At completion, retain the full `out\context-receiver-windows-*.zip` printed after `READY TO SHARE:`. It contains the executable, raw trace, linked disassembly, build provenance and analysis. A failed control also produces an evidence ZIP and must be kept.

For the broader baseline and exploratory suite, select **Complete Windows research pilot (all studies)**. That task writes a single `out\suite-evidence-*.zip`. Other named tasks in `.vscode/tasks.json` run individual studies. The `out/` directory is ignored by Git; review host inventory files before sharing them.

The K4 task selects a fresh seed, builds with MSVC, pins the measurement thread to an allowed logical CPU, validates a complete trace, calibrates on the first half and evaluates outcomes on the held-out half. The pilot and three-session follow-up are complete; future collection needs its own stated purpose and plan. Retain failed controls and null results. Its within-run bootstrap interval does not describe variability across days or hosts.

## Repository layout

| Path | Contents |
| --- | --- |
| `programs/` | C and x64 assembly measurement sites |
| `scripts/` | Windows runners, trace analyzers and evidence checks |
| `tests/` | Analyzer and trace-format tests |
| `protocols/` | Frozen measurement decisions for active standalone studies |
| `results/` | Original traces, paired binaries, manifests, figures and reproduction scripts |
| `RESEARCH_REPORT.md` | Consolidated measurements, paper boundary and limitations |

For a Linux development calibration check, run `./scripts/check_native.sh`. QEMU is useful for build and boot debugging; its timings are not evidence about the physical processor's branch predictor.
