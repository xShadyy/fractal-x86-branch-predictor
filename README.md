# x86 Branch Predictor Experiments

Controlled branch and cache measurements on an AMD Ryzen 7 9800X3D running Windows x64. This is independent work inspired by Joseph Ravichandran and Mengjia Yan's [Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf). Their [Fractal operating system](https://github.com/jprx/fractal) and Apple M1 findings are credited to the authors. The upstream revision used for development is pinned in [`UPSTREAM_FRACTAL_REVISION`](UPSTREAM_FRACTAL_REVISION).

The Windows studies in this repository run in one ordinary user-mode process. They do not boot Fractal, cross a user/kernel boundary, or reproduce the paper's M1 results. Timing and cache-hit differences alone do not identify mispredictions or transient execution.

## Current evidence

The K2 conditional-receiver diagnostic has three physical runs with different seeds on one Windows host, spanning two UTC dates. All 20 apparatus gates passed in each run. Its prespecified grouped condition-entry contrast recurred, while the candidate comparisons did not establish which target had been trained. The unexpectedly high interleaved architectural-skip hit rate remains unexplained. The earlier K1 receiver failed its separate skip-control gate and remains inconclusive.

The [research report](RESEARCH_REPORT.md) gives the measured results, links to raw evidence and analysis code, instruction audits, limits and a claim ledger. Frozen protocols for [K1](protocols/CONDITIONAL_RECEIVER_V1.md), [K2](protocols/RECEIVER_ORDER_K2.md), and the [B2 outcome](protocols/B2_OUTCOME_V4.md) and [replication](protocols/B2_REPLICATION_V1.md) studies retain the decisions made before their respective measurements. Original evidence ZIPs should be kept unchanged.

## K3 Windows pilot and K4 diagnostic

The first [K3 Windows pilot](results/k3-fresh-windows/README.md) completed 131,072 samples. Its original ZIP, source snapshot and frozen analysis verify, but two matched-training negatives failed: 8.94% and 9.52% hits against a 5% maximum. The primary interval includes zero. K3 remains inconclusive. Cache hits cluster near grouped-cell entry, including with matched training; the linked harness also reaches training and probing through different preceding branch paths.

The separate [K4 protocol](protocols/CONTEXT_RECEIVER_K4.md) adds an identical 256-branch prefix to every training and probe call and interleaves the conditions. It tests a revised apparatus; it does not establish a predictor reset or a mechanism. A full native development check replayed all 262,144 samples but still failed the two matched-candidate gates. K4 is an experimental diagnostic, not a verified apparatus fix. Windows collection and linked-binary review are still required.

Run **K4 context-prefix diagnostic (Windows)** in VS Code and retain its complete ZIP, including failed controls or a null. It runs one pilot with 262,144 recorded samples. K3 can still be reproduced without changing its collector or decision rules.

Both runners report collection status separately from scientific validity. An inconclusive completed run prints its failed gates and returns zero by default; add `-RequireValidControls` to make it a failing automation gate. Build, runtime and invalid-evidence errors remain failures. No exit code establishes transient execution.

## Run on Windows in VS Code

1. Install [VS Code](https://code.visualstudio.com/), Visual Studio Build Tools with **Desktop development with C++** and a Windows SDK, and Python 3.
2. Open this repository in VS Code. Select **Terminal → Run Task → K4 context-prefix diagnostic (Windows)** for the current apparatus follow-up.
3. At completion, retain the full `out\context-receiver-windows-*.zip` printed after `READY TO SHARE:`. It contains the executable, raw trace, linked disassembly, build provenance and analysis. A failed control also produces an evidence ZIP and must be kept.

For the broader baseline and exploratory suite, select **Complete Windows research pilot (all studies)**. That task writes a single `out\suite-evidence-*.zip`. Other named tasks in `.vscode/tasks.json` run individual studies. The `out/` directory is ignored by Git; review host inventory files before sharing them.

The K4 task selects a fresh seed, builds with MSVC, pins the measurement thread to an allowed logical CPU, validates a complete trace, calibrates on the first half and evaluates outcomes on the held-out half. Review the first pilot before writing a fixed subsequent session plan; retain failed controls and null results. Its within-run bootstrap interval does not describe variability across days or hosts.

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
