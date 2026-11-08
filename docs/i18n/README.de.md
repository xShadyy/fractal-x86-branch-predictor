<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal / x86: unabhängige Experimente zur Sprungvorhersage" width="100%">
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.nl.md">Nederlands</a> · <strong>Deutsch</strong>
</p>

<p align="center">
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml"><img src="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml/badge.svg?branch=main" alt="Workflow zur Softwarevalidierung"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/github/license/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Codelizenz: MIT"></a>
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/commits/main"><img src="https://img.shields.io/github/last-commit/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Neuester GitHub-Commit"></a>
  <a href="#geltungsbereich-und-grenzen"><img src="https://img.shields.io/badge/measurements-user%20mode-53677d?style=flat-square" alt="Messbereich: Benutzermodus"></a>
</p>

<h1 align="center">Kontrollierte x86-Experimente zu Sprüngen und Caches</h1>

Ein unabhängiges Forschungsartefakt für den **AMD Ryzen 7 9800X3D unter Windows
x64**, inspiriert vom
[Fractal-Paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
von Joseph Ravichandran und Mengjia Yan.
Es verbindet lokal vorab festgelegte Versuchspläne, Rohdatenprotokolle,
Herkunftsnachweise der ausführbaren Dateien, abgestimmte Kontrollen und unabhängig
nachgerechnete Analysen. Die aktuelle Datenerhebung unter Windows ist
abgeschlossen. Das gemessene Ergebnis ist eine wiederholbare, vom Training
abhängige Cache-Reaktion. Ihr Verhalten bei Datenabhängigkeiten und Eingriffen
in die Kodierung wird ausdrücklich untersucht.

**Das ursprüngliche Fractal-Betriebssystem und die Entdeckungen zum Apple M1 sind
die Arbeit ihrer Autoren.** Dieses Repository enthält unabhängige
x86-Experimente sowie eine gesondert gekennzeichnete Neuanalyse der von den
Autoren bereitgestellten Daten.

[Forschungsbericht](../../RESEARCH_REPORT.md) · [K7/K8-Nachweise](../../results/k7-k8-windows-causal/README.md) · [Reproduktionsanleitung](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Forschungswege](../../RESEARCH_ROUTE.md)

## Nachweise im Überblick

| Studie | Replikationseinheit | Aufgezeichnetes Ergebnis | Nachweise |
|---|---|---|---|
| Erster K3-Pilotversuch | Ein Windows-Prozess | **Nicht schlüssig:** 56/58 Kontrollkriterien; fehlgeschlagene Negativkontrollen bleiben erhalten | [Pilotaudit](../../results/k3-fresh-windows/README.md) |
| K4-Kontextkontrolle | Pilotversuch und drei Folgeprozesse auf einem Rechner | Jeweils 58/58 Kontrollkriterien; die definierte Reaktion tritt wiederholt auf | [K4-Dokumentation](../../results/k4-context-windows/README.md) |
| K5-Abhängigkeitskontrolle | Drei getrennte Windows-Systemstarts | **1,179,648 Episoden**; 88/88 Kontrollkriterien in jedem Versuch | [Festgeschriebene Replikation](../../results/k5-windows-replication/README.md) |
| K7 mit abgestimmter Abhängigkeitskontrolle | Drei neu gestartete Prozesse innerhalb eines Systemstarts | Jeweils 140/140 Kontrollkriterien; Primärkriterien unter kalter Bedingung erfüllt | [Auditierte K7/K8-Ergebnisse](../../results/k7-k8-windows-causal/README.md) |
| K8 mit Eingriffen in die Kodierung | Drei neu gestartete Prozesse innerhalb desselben Systemstarts | Jeweils 140/140 Kontrollkriterien; Interventionskriterien für die öffentliche Reaktion erfüllt | [Auditierte K7/K8-Ergebnisse](../../results/k7-k8-windows-causal/README.md) |
| K6-Testumgebung für Privilegstufen | Nur funktionaler Kurztest mit QEMU TCG | Softwareprüfungen der tatsächlichen CPL/PC-Werte; Datenerhebung auf physischer Hardware steht aus | [Entwicklungsdokumentation](../../results/k5-k6-development/README.md) |

K7 und K8 umfassen zusammen **983,040 aufgezeichnete Episoden**, darunter 491,520
Episoden im zurückgehaltenen Auswertungsteil. Episoden sind Beobachtungen
innerhalb eines Prozesses, keine unabhängigen Replikationen. Ein erfülltes
Kontrollkriterium bestätigt die dafür festgelegte Apparaturbedingung.
Es weist keinen bestimmten Hardwaremechanismus nach. Frühere Studien und
nicht schlüssige Ergebnisse bleiben in der
[Gesamtdokumentation](../../RESEARCH_REPORT.md) erhalten.

## Was die Eingriffe zeigen

Für den festgelegten **p0-Primärendpunkt unter kalter Bedingung** beträgt der
Kontrast Sham-Maske minus echte Maske wiederholt +99.902, +99.707 und +99.414
Prozentpunkte. Die Plain-minus-Sham-Intervalle liegen innerhalb der vorab
festgelegten Äquivalenzgrenze von +/-10 pp. Wird der Kodierungs-Ladezugriff der
abgefragten Bank entfernt oder werden die Bankzuordnungen der Kodierung geändert,
nimmt die öffentliche Reaktion ab. Wird nur der Ladezugriff der jeweils anderen
Bank entfernt, bleibt eine große Reaktion bestehen. Dies stärkt die Zuordnung
zum untersuchten Kodierpfad. Der genaue Sprungprädiktor und der transiente
Ausführungspfad bleiben jedoch ungeklärt.

![Unterstützende K7- und K8-Ergebnisse unter kalter Bedingung](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Jeder Punkt ist eine Schätzung aus einem Prozess. Die Fehlerbalken zeigen
unterstützende 95%-Cluster-Bootstrap-Intervalle innerhalb eines Laufs.
Für die [18 konfirmatorischen Kontrastintervalle](../../results/k7-k8-windows-causal/endpoint-table.csv)
gilt die gesonderte, festgeschriebene Bonferroni-Regel mit ungefähr 99.17% je
Endpunkt. Die Familie aus sechs Kontrasten umfasst jeweils ein planmäßig
zusammengehöriges Wiederholungspaar, nicht alle 18 Intervalle gleichzeitig.
Es wird kein zusammengefasstes oder rechnerübergreifendes Intervall gezeigt.
Bereinigte Kontraste können 100 pp überschreiten.*

**Eine wichtige Einschränkung:** Die Sham-Maske senkt die Trefferquote in der
explorativen p0-Kontrolle unter warmer Bedingung um 14.16–16.31 pp. Ihre
Äquivalenz gilt für den festgelegten kalten Primärendpunkt, nicht allgemein für
alle Zeitbedingungen.

<details>
<summary>Das explorative Ergebnis unter warmer Bedingung ansehen</summary>

![Explorative Plain- und Sham-Zählwerte unter warmer Bedingung](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Dies sind deskriptive Zählwerte aus einer unterstützenden Bedingung außerhalb
der sechs konfirmatorischen Kontraste. Sie erklären nicht eindeutig, warum sich
die Reaktion ändert.

</details>

## Daten erneut prüfen

Das Zählaudit benötigt Python 3.10+ und dessen Standardbibliothek. Vom
Stammverzeichnis des Repositorys aus lassen sich Schwellenwerte, Zellzählwerte,
Kontrollkriterien und primäre Punktschätzungen reproduzieren:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

Dabei werden archivierte Daten gelesen, ohne das Messprogramm auszuführen.
Die genaue Anleitung zur Wiederholung der festgeschriebenen Analyse und zum
Codeaudit steht in der
[Reproduktionsanleitung](../../results/k7-k8-windows-causal/REPRODUCE.md).
Die ursprünglichen Nachweis-ZIPs und Hashwerte bleiben erhalten. Die
Software-CI prüft Parser, Analysen, Quellcodegenerierung und Dokumentation. Sie
wiederholt weder die physischen Windows-Experimente noch bestätigt sie deren
Mechanismus.

Die abgeschlossenen Studien besitzen festgeschriebene Quellcodestände. Eine
neue Datenerhebung benötigt einen eigenen Plan; bestehende Versuche dürfen
nicht erweitert oder stillschweigend ersetzt werden.
Für die Windows-Datenerhebung werden MSVC x64 Build Tools und ein Windows SDK
benötigt, nicht jedoch für das obige Zählaudit mit reinem Lesezugriff.

## Gesonderte Referenz: die M1-Daten der Autoren

Die [portable Neuanalyse der Autorendaten](../../results/fractal-author-data-reanalysis/README.md)
validiert **48 bereitgestellte Rohdatenprotokolle und 240,192 veröffentlichte
Zeilen**. Sie liefert JSON, CSV und Abbildungen, ohne einen Mac zu benötigen.
Diese Zeilen sind Messungen von Ravichandran und Yan. Sie sind von den neu
erhobenen Windows-Daten dieses Projekts getrennt. Das Einlesen, die Herkunft
und die unterschiedlichen Lizenzbedingungen der Artefakte sind zusammen mit
dem Ergebnis dokumentiert.

## Geltungsbereich und Grenzen

- Ein angegebener Ryzen-Rechner. K5 umfasst drei Systemstarts; K7/K8 verwenden
  je drei Prozesse pro Studie innerhalb eines Systemstarts. Die Anwesenheit
  eines Hypervisors und VBS wurden dokumentiert. Alle neu erhobenen
  Windows-Messungen erfolgen im Benutzermodus (CPL 3), nicht im Kernelmodus.
- Die K7/K8-Modi beeinflussen sowohl Training als auch Prüfung. Die Kontrolle
  mit privater Bank misst die öffentliche Reaktion, ohne einen Sensor für die
  Cache-Belegung der privaten Bank.
- Alle aufgezeichneten K7/K8-Sensorzeiten sind Vielfache von 47 TSC-Ticks. Es
  handelt sich um kalibrierte Messungen von Cache-Klassen, nicht um genaue
  Schätzungen der Zyklenzahl einzelner Instruktionen.
- Der genaue Prädiktormechanismus, ein ausschließlich transienter
  Ausführungspfad und ein physischer Einfluss vom Benutzer- auf den Kernelmodus
  sind weiterhin nicht nachgewiesen. Es werden weder neue M1-Messungen noch ein
  vergleichender Vorteil von Fractal hinsichtlich des Messrauschens behauptet.

Die [Bewertung der Forschungswege](../../RESEARCH_ROUTE.md) beschreibt die nächste
klar eingegrenzte native Linux-Studie sowie die gesonderte Prüfung der
Bootfähigkeit und Datenexportmöglichkeit für physisches Fractal.

## Aufbau des Repositorys

| Pfad | Zweck |
|---|---|
| [`programs/`](../../programs/) | C-Programme und lesbare Messstellen in Assembler |
| [`protocols/`](../../protocols/) | Festgeschriebene Entscheidungen zur Erhebung und Analyse |
| [`scripts/`](../../scripts/) | Messprogramme, Analyseprogramme sowie Herkunfts- und Auditwerkzeuge |
| [`tests/`](../../tests/) | Software-Testdaten und Regressionstests |
| [`results/`](../../results/) | Ursprüngliche Nachweise, numerische Aufzeichnungen und Abbildungen |
| [`RESEARCH_REPORT.md`](../../RESEARCH_REPORT.md) | Zusammengefasste Messergebnisse und Grenzen der Aussagen |
| [`RESEARCH_ROUTE.md`](../../RESEARCH_ROUTE.md) | Hardwaretauglichkeit und Bewertung der nächsten Studie |

## Urheberschaft und Zitierung

Gepflegt von [Tymoteusz Netter](https://github.com/xShadyy).
Dieses Artefakt lässt sich mit [CITATION.cff](../../CITATION.cff) zitieren. Bei
Ausführungen zum Fractal-Betriebssystem oder zu den M1-Ergebnissen ist das
Originalpaper gesondert zu zitieren:

> Joseph Ravichandran und Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Paper](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Ursprüngliches Betriebssystem](https://github.com/jprx/fractal)
> · [Evaluiertes Artefakt](https://doi.org/10.5281/zenodo.19556693)

Projektcode: [MIT](../../LICENSE). Komponenten des ursprünglichen Projekts und
das gesonderte Autorenartefakt behalten ihre eigenen Urheberschafts- und
Lizenzbedingungen. Siehe die
[Dokumentation der Autorendaten](../../results/fractal-author-data-reanalysis/README.md).
