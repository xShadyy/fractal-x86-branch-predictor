<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="Lizenz: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <strong>Deutsch</strong> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

Experimente zur Sprungvorhersage und zum Cache auf einem **AMD Ryzen 7
9800X3D mit Windows x64**, inspiriert von Joseph Ravichandrans und Mengjia Yans
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf).
Die Forschungsdokumentation enthält vorab festgelegte Protokolle, Rohdaten,
abgeglichene Kontrollbedingungen, Hashes der ausführbaren Dateien und
Analysen, die sich erneut ausführen lassen.

Die Windows-Studien messen eine wiederholbare Cache-Antwort, die von der
Trainingssequenz abhängt. Abhängigkeitskontrollen und Eingriffe in den Encoder
prüfen, welche Änderungen diese Antwort unterdrücken.

[Forschungsbericht](../../RESEARCH_REPORT.md) · [Ergebnisse und Daten](../../results/k7-k8-windows-causal/README.md) · [Reproduktionsanleitung](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Weitere Studien](../../RESEARCH_ROUTE.md)

## Ergebnisse

| Studie | Replikation | Ergebnis | Dokumentation |
|---|---|---|---|
| K3: neuer Empfänger | Ein Prozess | Nicht eindeutig: 56/58 Kontrollkriterien; Negativkontrollen fehlgeschlagen | [K3](../../results/k3-fresh-windows/README.md) |
| K4: Kontextkontrolle | Pilotversuch und drei Folgeprozesse | Jeweils 58/58 Kontrollkriterien; Antwort tritt erneut auf | [K4](../../results/k4-context-windows/README.md) |
| K5: Abhängigkeitskontrolle | Drei Windows-Systemstarts | 1,179,648 Episoden; 88/88 Kontrollkriterien pro Versuch | [K5](../../results/k5-windows-replication/README.md) |
| K7: Abhängigkeit mit abgeglichener Kontrolle | Drei neue Prozesse ohne Neustart | Jeweils 140/140 Kontrollkriterien; primäre Kriterien bei kalter Bedingung erfüllt | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8: Encoder-Eingriffe | Drei neue Prozesse in derselben Sitzung | Jeweils 140/140 Kontrollkriterien; Eingriffskriterien für die öffentliche Antwort erfüllt | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6: Privilegientest | Software-Funktionstest mit QEMU TCG | CPL/PC-Prüfungen bestanden; physische Messdaten stehen aus | [K6](../../results/k5-k6-development/README.md) |

K7/K8 enthalten **983,040 Episoden**, darunter 491,520 zurückgehaltene
Validierungsepisoden. Die Replikation wird über Prozesse hinweg beurteilt;
Episoden innerhalb eines Prozesses teilen dieselben Laufbedingungen.

## Wirkung von Abhängigkeiten und Encoder-Eingriffen

Beim primären p0-Endpunkt mit kalter Cachezeile für die Bedingung beträgt der
Kontrast sham-minus-true-mask in den drei Wiederholungen +99.902, +99.707 und
+99.414 Prozentpunkte. Die plain-minus-sham-Intervalle liegen innerhalb der
vorab festgelegten Äquivalenzgrenze von +/-10 pp. Das Entfernen des
Encoder-Ladezugriffs auf die abgefragte Bank oder das Umleiten beider
Encoder-Ladezugriffe unterdrückt die öffentliche Antwort. Wird nur der
Ladezugriff auf die andere Bank entfernt, bleibt die Antwort erhalten.

![Wirkung von Abhängigkeiten und Encoder-Eingriffen über drei Wiederholungen](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Punkte zeigen Prozessschätzungen, Fehlerbalken die ergänzenden
95%-Cluster-Bootstrap-Intervalle innerhalb eines Laufs.
Die [18 primären Kontrastintervalle](../../results/k7-k8-windows-causal/endpoint-table.csv)
verwenden die festgelegte Bonferroni-Regel mit ungefähr 99.17% pro Endpunkt.
Jede Familie aus sechs Kontrasten umfasst ein geplantes Wiederholungspaar.
Bereinigte Kontraste können 100 pp überschreiten.*

In der explorativen p0-Kontrolle mit warmer Cachezeile für die Bedingung
senkt die Sham-Variante die Trefferhäufigkeit um 14.16–16.31 pp. Das
Äquivalenzergebnis bei kalter Bedingung gilt daher nur für diesen primären Endpunkt.

<details>
<summary>Kontrolle bei warmer Bedingung</summary>

![Explorative Zählungen für plain und sham bei warmer Bedingung](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Deskriptive Zählungen aus der ergänzenden warmen Bedingung, außerhalb der
sechs primären Kontraste.

</details>

## Reproduktion

Mit Python 3.10+ und seiner Standardbibliothek lassen sich Schwellenwerte,
Zellzählungen, Kontrollkriterien und primäre Punktschätzungen aus dem
Originalarchiv nachprüfen:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

Die [Reproduktionsanleitung](../../results/k7-k8-windows-causal/REPRODUCE.md)
beschreibt die exakte Wiederholung der Analyse, die Diagrammerstellung und
die Codeprüfung. Originalarchive und Hashes liegen jedem Ergebnis bei.
Die [Softwarevalidierung](https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml)
prüft Analyse-Testdaten, generierten Quellcode und Dokumentation.

Abgeschlossene Studien behalten ihre festgelegten Pläne und Quellcodestände.
Eine neue Datenerhebung beginnt mit einem neuen Plan. Für Windows-Messungen
werden MSVC x64 Build Tools und ein Windows SDK benötigt.

## Neuanalyse der Fractal-Autorendaten

Die [Neuanalyse des M1-Artefakts](../../results/fractal-author-data-reanalysis/README.md)
prüft **48 Traces und 240,192 veröffentlichte Zeilen** aus den freigegebenen
Messdaten von Ravichandran und Yan. JSON, CSV und Abbildungen stehen zusammen
mit der Herkunfts- und Lizenzdokumentation des Artefakts bereit.

## Messkontext

Die Windows-Messprogramme laufen im Benutzermodus. K5 umfasst drei Systemstarts
auf einem Rechner. K7/K8 verwenden drei Prozesse pro Studie innerhalb einer
Sitzung ohne Neustart; Hypervisor-Präsenz und VBS sind dokumentiert. Die
Eingriffe gelten sowohl beim Training als auch bei der Messprobe; die
Kontrolle mit privaten Banken beobachtet die öffentliche Antwort.

Die K7/K8-Sensorzeiten sind Vielfache von 47 TSC-Ticks und ermöglichen
kalibrierte Cache-Klassifikationen. Der genaue Prädiktor, der Pfad der
transienten Ausführung und ein physischer Einfluss vom Benutzer- auf den
Kernelmodus bleiben offene Fragen.
Die Seite [Weitere Studien](../../RESEARCH_ROUTE.md) beschreibt die Messwege mit
nativem Linux und Fractal auf physischer Hardware.

## Projektdateien

| Pfad | Inhalt |
|---|---|
| [`programs/`](../../programs/) | Messprogramme in C und Messstellen in Assembler |
| [`protocols/`](../../protocols/) | Erhebungspläne und Analyseregeln |
| [`scripts/`](../../scripts/) | Werkzeuge für Datenerhebung, Analyse und Herkunftsnachweise |
| [`tests/`](../../tests/) | Software-Testdaten und Regressionstests |
| [`results/`](../../results/) | Rohdaten, numerische Tabellen und Abbildungen |

## Zitieren

Betreut von [Tymoteusz Netter](https://github.com/xShadyy).
Zum Zitieren dieser Software dient [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran und Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Publikation](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Forschungsartefakt](https://doi.org/10.5281/zenodo.19556693)

Der Projektcode steht unter der [MIT-Lizenz](../../LICENSE). Eingebundene
Komponenten und das Artefakt der Autoren behalten ihre jeweiligen Lizenzen
und Urheberangaben.
