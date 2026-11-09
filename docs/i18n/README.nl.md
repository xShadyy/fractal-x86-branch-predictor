<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <strong>Nederlands</strong>
</p>

# Fractal x86

Experimenten met sprongvoorspelling en caches op een **AMD Ryzen 7 9800X3D met
Windows x64**, geïnspireerd door
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
van Joseph Ravichandran en Mengjia Yan.

De Windows-studies meten een herhaalbare cacherespons die gevoelig is voor
training. Controles op data-afhankelijkheid en ingrepen in de encoder toetsen
welke veranderingen deze respons onderdrukken.

[Resultaten en data](../../results/k7-k8-windows-causal/README.md) · [Reproductiehandleiding](../../results/k7-k8-windows-causal/REPRODUCE.md)

## Resultaten

| Studie | Replicatie | Resultaat | Dossier |
|---|---|---|---|
| K3 ontvanger met nieuwe markers | Eén proces | Onbeslist: 56/58 controles; negatieve controles faalden | [K3](../../results/k3-fresh-windows/README.md) |
| K4 contextcontrole | Pilot en drie vervolgprocessen | Elk 58/58 controles; de respons keert terug | [K4](../../results/k4-context-windows/README.md) |
| K5 afhankelijkheidscontrole | Drie Windows-boots | 1,179,648 episodes; elk experiment 88/88 controles | [K5](../../results/k5-windows-replication/README.md) |
| K7 gematchte afhankelijkheidscontrole | Drie nieuw gestarte processen binnen één boot | Elk 140/140 controles; primaire criteria voor de koude conditie gehaald | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8 ingrepen in de encoder | Drie nieuw gestarte processen binnen dezelfde boot | Elk 140/140 controles; interventiecriteria voor de publieke respons gehaald | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6 privilegetest | Software-smoketest met QEMU TCG | CPL/PC-controles geslaagd; metingen op fysieke hardware nog niet verzameld | [K6](../../results/k5-k6-development/README.md) |

K7/K8 bevatten **983,040 episodes**, waarvan 491,520 apart gehouden voor
evaluatie. Replicatie wordt tussen processen beoordeeld; episodes binnen één
proces delen dezelfde omstandigheden van die run.

## Effecten van afhankelijkheid en encoderingrepen

Voor het primaire p0-eindpunt in de koude conditie bedraagt het contrast sham
minus true-mask +99.902, +99.707 en +99.414 procentpunt in de drie herhalingen.
De intervallen voor plain minus sham vallen binnen de vooraf vastgelegde
equivalentiemarge van +/-10 pp. Het verwijderen van de encoderload voor de
uitgelezen bank of het omleiden van beide encoderloads onderdrukt de publieke
respons. Als alleen de load voor de andere bank wordt verwijderd, blijft de
respons behouden.

In de verkennende p0-controle met warme conditie verlaagt de sham het
hitpercentage met 14.16–16.31 pp. De equivalentie in de koude conditie geldt
daarom specifiek voor dat primaire eindpunt.

![Effecten van afhankelijkheid en encoderingrepen in drie herhalingen](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>Controle met warme conditie</summary>

![Verkennende aantallen voor plain en sham in de warme conditie](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## Reproduceren

Gebruik Python 3.10+ en de standaardbibliotheek om drempels, aantallen per cel,
controles en primaire puntschattingen opnieuw te berekenen uit het originele
archief:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

De [reproductiehandleiding](../../results/k7-k8-windows-causal/REPRODUCE.md)
beschrijft het exact herhalen van analyses, het genereren van grafieken en
code-inspectie. Bij elk resultaat staan de originele archieven en hashes.

## Heranalyse van de Fractal-data van de auteurs

De [heranalyse van het M1-artifact](../../results/fractal-author-data-reanalysis/README.md)
controleert **48 traces en 240,192 gepubliceerde rijen** uit de vrijgegeven
metingen van Ravichandran en Yan. JSON, CSV en figuren zijn beschikbaar,
samen met de herkomstgegevens en licentie-informatie van het artifact.

## Meetcontext

De Windows-meetprogramma's draaien in gebruikersmodus.
K5 omvat drie boots op één werkstation. K7/K8 gebruiken drie processen per
studie binnen één boot; de aanwezigheid van een hypervisor en de VBS-status
zijn vastgelegd. De ingrepen gelden zowel tijdens training als tijdens
probing; de controle met private banken observeert de publieke respons.

De K7/K8-sensortijden zijn veelvouden van 47 TSC-ticks en ondersteunen
gekalibreerde cacheclassificaties. De precieze predictor, het pad van
transient execution en de invloed van gebruikerscode op de kernel op fysieke
hardware blijven open vragen.

## Citeren

Onderhouden door [Tymoteusz Netter](https://github.com/xShadyy).
Citeer deze software met [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran en Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Artikel](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Onderzoeksartifact](https://doi.org/10.5281/zenodo.19556693)

De projectcode valt onder de [MIT-licentie](../../LICENSE). Upstream-componenten
en het artifact van de auteurs behouden hun eigen licenties en
naamsvermeldingen.
