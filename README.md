<p align="center">
  <img src="docs/assets/research-banner.png" alt="Fractal / x86: independent branch-predictor experiments" width="100%">
</p>

<p align="center">
  <strong>English</strong> · <a href="docs/i18n/README.pl.md">Polski</a> · <a href="docs/i18n/README.nl.md">Nederlands</a> · <a href="docs/i18n/README.de.md">Deutsch</a>
</p>

<p align="center">
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml"><img src="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml/badge.svg?branch=main" alt="Software validation workflow"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Code license: MIT"></a>
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/commits/main"><img src="https://img.shields.io/github/last-commit/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Latest GitHub commit"></a>
  <a href="#scope-and-limits"><img src="https://img.shields.io/badge/measurements-user%20mode-53677d?style=flat-square" alt="Measurement scope: user mode"></a>
</p>

<h1 align="center">Controlled x86 branch and cache experiments</h1>

An independent research artifact on the **AMD Ryzen 7 9800X3D running Windows
x64**, inspired by Joseph Ravichandran and Mengjia Yan's
[Fractal paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf).
It combines locally prespecified plans, raw traces, executable provenance,
matched controls and independently replayed analyses. The current Windows
collection phase is complete. The measured result is a repeatable,
training-sensitive cache response whose sensitivity to data dependencies and
encoder interventions is explicitly tested.

**The original Fractal OS and Apple M1 discoveries belong to their authors.**
This repository contains independent x86 experiments and a separately labeled
reanalysis of their supplied data.

[Research report](RESEARCH_REPORT.md) · [K7/K8 evidence](results/k7-k8-windows-causal/README.md) · [Reproduction guide](results/k7-k8-windows-causal/REPRODUCE.md) · [Research routes](RESEARCH_ROUTE.md)

## Evidence at a glance

| Study | Replication unit | Recorded result | Evidence |
|---|---|---|---|
| First K3 pilot | One Windows process | **Inconclusive:** 56/58 gates; failed negative controls retained | [Pilot audit](results/k3-fresh-windows/README.md) |
| K4 context control | Pilot and three follow-up processes on one host | 58/58 gates in each; defined response recurs | [K4 record](results/k4-context-windows/README.md) |
| K5 dependency control | Three distinct Windows boots | **1,179,648 episodes**; 88/88 gates in each attempt | [Frozen replication](results/k5-windows-replication/README.md) |
| K7 matched dependency | Three fresh processes within one boot | 140/140 gates in each; cold-condition primary criteria met | [Audited K7/K8 results](results/k7-k8-windows-causal/README.md) |
| K8 encoder interventions | Three fresh processes in that same boot | 140/140 gates in each; public-response intervention criteria met | [Audited K7/K8 results](results/k7-k8-windows-causal/README.md) |
| K6 privilege harness | QEMU TCG functional smoke only | Actual CPL/PC software checks; physical collection pending | [Development record](results/k5-k6-development/README.md) |

K7 and K8 together contain **983,040 recorded episodes**, including 491,520
held-out episodes. Episodes are observations within a process, not independent
replications. Passing a gate establishes its declared apparatus condition.
It does not establish a specific hardware mechanism. Earlier studies and
inconclusive results remain in the [consolidated record](RESEARCH_REPORT.md).

## What the interventions show

For the declared **cold-condition p0 primary endpoint**, the sham-minus-true-mask
contrast repeats at +99.902, +99.707 and +99.414 percentage points.
Plain-minus-sham intervals lie inside the prespecified +/-10 pp equivalence
margin. Removing the queried bank's encoder load or changing the encoder's bank
bindings suppresses the public response; removing only the other bank's load
leaves a large response. This strengthens attribution to the tested encoding
path while leaving the exact predictor and transient path unresolved.

![K7 and K8 supporting cold-condition results](results/k7-k8-windows-causal/windows-causal-responses.png)

*Each point is a process estimate. Whiskers are supporting 95% within-run
cluster-bootstrap intervals. The [18 confirmatory contrast intervals](results/k7-k8-windows-causal/endpoint-table.csv)
use the separate frozen Bonferroni rule, approximately 99.17% per endpoint.
The six-contrast family covers one scheduled repetition pair, not all 18
intervals simultaneously. No pooled or across-host interval is shown.
Adjusted contrasts can exceed 100 pp.*

**A qualification worth retaining:** the sham lowers hits by 14.16–16.31 pp in
the exploratory warm-condition p0 control. Its equivalence is specific to the
declared cold primary endpoint, not universal across timing conditions.

<details>
<summary>Inspect the exploratory warm-condition result</summary>

![Exploratory warm-condition plain and sham counts](results/k7-k8-windows-causal/warm-sham-exploratory.png)

These are descriptive counts from a supporting condition, outside the six
confirmatory contrasts. They do not uniquely identify why the response changes.

</details>

## Recheck the data

The count audit uses Python 3.10+ and its standard library. From the repository
root, reproduce thresholds, cell counts, gates and primary point estimates:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

This reads archived data without executing the collector. Exact frozen-analysis
and code-audit instructions are in the [reproduction guide](results/k7-k8-windows-causal/REPRODUCE.md).
Original evidence ZIPs and hashes are retained. Software CI checks parsers,
analysis, source generation and documentation; it does not rerun the physical
Windows experiments or certify their mechanism.

The completed studies have frozen source revisions. New collection requires
its own plan; do not extend or silently replace the existing attempts.
MSVC x64 Build Tools and a Windows SDK are needed for Windows collection,
but not for the read-only count audit above.

## Separate reference: the authors' M1 data

The [portable author-data reanalysis](results/fractal-author-data-reanalysis/README.md)
validates **48 supplied traces and 240,192 published rows**. It provides JSON,
CSV and figures without requiring a Mac. Those rows are Ravichandran and Yan's
measurements. They are separate from this project's newly collected Windows
data. The reader, provenance and artifact licensing distinction are documented
with the result.

## Scope and limits

- One reported Ryzen workstation. K5 spans three boots; K7/K8 use three
  processes per study within one boot, with hypervisor presence and VBS recorded.
- K7/K8 modes affect both training and probing. The private-bank control measures
  the public response, without a private-bank heat sensor.
- All recorded K7/K8 sensor timings are multiples of 47 TSC ticks. These are
  calibrated cache-class measurements, not precise instruction-cycle estimates.
- The exact predictor mechanism, exclusively transient path and physical
  user-to-kernel influence remain unestablished. No new M1 measurement or
  comparative Fractal noise advantage is claimed.

The [route assessment](RESEARCH_ROUTE.md) describes the next bounded native
Linux study and the separate boot/export gate for physical Fractal.

## Repository map

| Path | Purpose |
|---|---|
| [`programs/`](programs/) | C programs and readable assembly measurement sites |
| [`protocols/`](protocols/) | Frozen collection and analysis decisions |
| [`scripts/`](scripts/) | Collectors, analyzers, provenance and audit tools |
| [`tests/`](tests/) | Software fixtures and regression checks |
| [`results/`](results/) | Original evidence, numerical records and figures |
| [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md) | Consolidated measured findings and claim boundaries |
| [`RESEARCH_ROUTE.md`](RESEARCH_ROUTE.md) | Hardware feasibility and next-study assessment |

## Attribution and citation

Maintained by [Tymoteusz Netter](https://github.com/xShadyy).
Use [CITATION.cff](CITATION.cff) to cite this artifact. Cite the original paper
separately when discussing Fractal's OS or M1 findings:

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Upstream OS](https://github.com/jprx/fractal)
> · [Evaluated artifact](https://doi.org/10.5281/zenodo.19556693)

Project code: [MIT](LICENSE). Upstream components and the separate author
artifact retain their own attribution and licensing terms. See the
[author-data record](results/fractal-author-data-reanalysis/README.md).
