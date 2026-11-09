<p align="center">
  <img src="docs/assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="License: MIT"></a>
</p>

<p align="center">
  <strong>English</strong> · <a href="docs/i18n/README.pl.md">Polski</a> · <a href="docs/i18n/README.de.md">Deutsch</a> · <a href="docs/i18n/README.fr.md">Français</a> · <a href="docs/i18n/README.es.md">Español</a> · <a href="docs/i18n/README.pt-BR.md">Português (Brasil)</a><br>
  <a href="docs/i18n/README.zh-CN.md">简体中文</a> · <a href="docs/i18n/README.ja.md">日本語</a> · <a href="docs/i18n/README.ko.md">한국어</a> · <a href="docs/i18n/README.ru.md">Русский</a> · <a href="docs/i18n/README.ar.md">العربية</a> · <a href="docs/i18n/README.nl.md">Nederlands</a>
</p>

# Fractal x86

Branch-prediction and cache experiments on an **AMD Ryzen 7 9800X3D running
Windows x64**, inspired by Joseph Ravichandran and Mengjia Yan's
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf).
The research record includes prespecified protocols, raw traces, matched
controls, executable hashes and replayable analyses.

The Windows studies measure a repeatable, training-sensitive cache response.
Dependency controls and encoder interventions test which changes suppress it.

[Research report](RESEARCH_REPORT.md) · [Results and data](results/k7-k8-windows-causal/README.md) · [Reproduction guide](results/k7-k8-windows-causal/REPRODUCE.md) · [Next studies](RESEARCH_ROUTE.md)

## Results

| Study | Replication | Result | Record |
|---|---|---|---|
| K3 fresh receiver | One process | Inconclusive: 56/58 gates; negative controls failed | [K3](results/k3-fresh-windows/README.md) |
| K4 context control | Pilot and three follow-up processes | 58/58 gates in each; response recurs | [K4](results/k4-context-windows/README.md) |
| K5 dependency control | Three Windows boots | 1,179,648 episodes; 88/88 gates in each attempt | [K5](results/k5-windows-replication/README.md) |
| K7 matched dependency | Three fresh processes in one boot | 140/140 gates in each; cold-condition primary criteria met | [K7/K8](results/k7-k8-windows-causal/README.md) |
| K8 encoder interventions | Three fresh processes in the same boot | 140/140 gates in each; public-response intervention criteria met | [K7/K8](results/k7-k8-windows-causal/README.md) |
| K6 privilege test | QEMU TCG software smoke test | CPL/PC checks pass; physical collection pending | [K6](results/k5-k6-development/README.md) |

K7/K8 contain **983,040 episodes**, including 491,520 held-out episodes.
Replication is assessed across processes; episodes within a process share
the same run conditions.

## Dependency and encoder effects

At the cold-condition p0 primary endpoint, the sham-minus-true-mask contrast
is +99.902, +99.707 and +99.414 percentage points across the three repetitions.
The plain-minus-sham intervals fit within the prespecified +/-10 pp equivalence
margin. Removing the queried bank's encoder load or redirecting both encoder
loads suppresses the public response. Removing only the other bank's load
preserves it.

![Dependency and encoder effects across three repetitions](results/k7-k8-windows-causal/windows-causal-responses.png)

*Points show process estimates; whiskers show supporting 95% within-run
cluster-bootstrap intervals. The [18 primary contrast intervals](results/k7-k8-windows-causal/endpoint-table.csv)
use the frozen Bonferroni rule, approximately 99.17% per endpoint. Each
six-contrast family covers one scheduled repetition pair. Adjusted contrasts
can exceed 100 pp.*

In the exploratory warm-condition p0 control, the sham lowers hits by
14.16–16.31 pp. The cold-condition equivalence result is therefore specific
to that primary endpoint.

<details>
<summary>Warm-condition control</summary>

![Exploratory warm-condition plain and sham counts](results/k7-k8-windows-causal/warm-sham-exploratory.png)

Descriptive counts from the supporting warm condition, outside the six
primary contrasts.

</details>

## Reproduce

Use Python 3.10+ and its standard library to recheck thresholds, cell counts,
gates and primary point estimates from the original archive:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

The [reproduction guide](results/k7-k8-windows-causal/REPRODUCE.md) covers exact
analysis replay, chart generation and code inspection. Original archives and
hashes accompany each result. [Software validation](https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml)
checks analysis fixtures, generated source and documentation.

Completed studies retain their frozen plans and source revisions. New
collection starts with a new plan. Windows collection requires MSVC x64 Build
Tools and a Windows SDK.

## Fractal author-data reanalysis

The [M1 artifact reanalysis](results/fractal-author-data-reanalysis/README.md)
checks **48 traces and 240,192 published rows** from Ravichandran and Yan's
released measurements. JSON, CSV and figures are available alongside the
artifact provenance and licensing record.

## Measurement context

The Windows collectors run in user mode. K5 spans three boots on one workstation.
K7/K8 use three processes per study
within one boot, with hypervisor presence and VBS recorded. Their interventions
apply during both training and probing; the private-bank control observes
the public response.

K7/K8 sensor timings occur in multiples of 47 TSC ticks and support calibrated
cache classifications. The exact predictor, the transient execution path and
physical user-to-kernel influence remain open questions.
[Next studies](RESEARCH_ROUTE.md) describes the native Linux and physical
Fractal collection routes.

## Project files

| Path | Contents |
|---|---|
| [`programs/`](programs/) | C collectors and assembly measurement sites |
| [`protocols/`](protocols/) | Collection plans and analysis rules |
| [`scripts/`](scripts/) | Collection, analysis and provenance tools |
| [`tests/`](tests/) | Software fixtures and regression checks |
| [`results/`](results/) | Raw evidence, numerical tables and figures |

## Citation

Maintained by [Tymoteusz Netter](https://github.com/xShadyy).
Cite this software with [CITATION.cff](CITATION.cff).

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Research artifact](https://doi.org/10.5281/zenodo.19556693)

Project code uses the [MIT license](LICENSE). Upstream components and the
authors' artifact retain their respective licenses and attribution.
