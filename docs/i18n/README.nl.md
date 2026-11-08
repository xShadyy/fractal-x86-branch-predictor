<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal / x86: onafhankelijke experimenten met vertakkingsvoorspellers" width="100%">
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <strong>Nederlands</strong> · <a href="README.de.md">Deutsch</a>
</p>

<p align="center">
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml"><img src="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml/badge.svg?branch=main" alt="Workflow voor softwarevalidatie"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/github/license/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Codelicentie: MIT"></a>
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/commits/main"><img src="https://img.shields.io/github/last-commit/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Meest recente GitHub-commit"></a>
  <a href="#reikwijdte-en-beperkingen"><img src="https://img.shields.io/badge/measurements-user%20mode-53677d?style=flat-square" alt="Meetbereik: gebruikersmodus"></a>
</p>

<h1 align="center">Gecontroleerde experimenten met vertakkingen en caches op x86</h1>

Een onafhankelijk onderzoekspakket voor de **AMD Ryzen 7 9800X3D met Windows
x64**, geïnspireerd door het
[Fractal-artikel](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
van Joseph Ravichandran en Mengjia Yan.
Het combineert lokaal vooraf vastgelegde plannen, ruwe meettraces,
herkomstgegevens van uitvoerbare bestanden, gematchte controles en onafhankelijk
herberekende analyses. De huidige verzameling van Windows-metingen is afgerond.
Het gemeten resultaat is een herhaalbare cacherespons die afhangt van de training.
De gevoeligheid daarvan voor data-afhankelijkheden en ingrepen in het
coderingspad is expliciet onderzocht.

**Het oorspronkelijke Fractal-besturingssysteem en de ontdekkingen op Apple M1
zijn het werk van de oorspronkelijke auteurs.** Deze repository bevat
onafhankelijke x86-experimenten en een afzonderlijk aangeduide heranalyse van
de door hen beschikbaar gestelde gegevens.

[Onderzoeksrapport](../../RESEARCH_REPORT.md) · [K7/K8-bewijsstukken](../../results/k7-k8-windows-causal/README.md) · [Reproductiehandleiding](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Onderzoeksroutes](../../RESEARCH_ROUTE.md)

## Overzicht van het bewijs

| Studie | Replicatie-eenheid | Vastgelegd resultaat | Bewijsstukken |
|---|---|---|---|
| Eerste K3-pilot | Eén Windows-proces | **Onbeslist:** 56/58 controlevoorwaarden; mislukte negatieve controles zijn behouden | [Pilot-audit](../../results/k3-fresh-windows/README.md) |
| K4-contextcontrole | Pilot en drie vervolgprocessen op één host | In elk proces 58/58 controlevoorwaarden; de gedefinieerde respons keert terug | [K4-dossier](../../results/k4-context-windows/README.md) |
| K5-afhankelijkheidscontrole | Drie afzonderlijke starts van Windows | **1,179,648 episodes**; bij elke poging 88/88 controlevoorwaarden | [Vastgelegde replicatie](../../results/k5-windows-replication/README.md) |
| K7-gematchte afhankelijkheid | Drie nieuw gestarte processen binnen één Windows-start | In elk proces 140/140 controlevoorwaarden; primaire criteria voor de koude conditie gehaald | [Geauditeerde K7/K8-resultaten](../../results/k7-k8-windows-causal/README.md) |
| K8-ingrepen in het coderingspad | Drie nieuw gestarte processen binnen diezelfde Windows-start | In elk proces 140/140 controlevoorwaarden; interventiecriteria voor de publieke respons gehaald | [Geauditeerde K7/K8-resultaten](../../results/k7-k8-windows-causal/README.md) |
| K6-testopstelling voor privilegeniveaus | Alleen een functionele basistest met QEMU TCG | Softwarecontroles van werkelijke CPL/PC-waarden; fysieke metingen moeten nog worden uitgevoerd | [Ontwikkelingsdossier](../../results/k5-k6-development/README.md) |

K7 en K8 bevatten samen **983,040 vastgelegde episodes**, waarvan 491,520
apart zijn gehouden voor toetsing. Episodes zijn waarnemingen binnen een proces,
geen onafhankelijke replicaties. Een geslaagde controle toont aan dat aan de
bijbehorende vastgelegde voorwaarde voor de meetopstelling is voldaan.
Daarmee is geen specifiek hardwaremechanisme aangetoond. Eerdere studies en
onbesliste resultaten blijven beschikbaar in het
[geconsolideerde dossier](../../RESEARCH_REPORT.md).

## Wat de interventies laten zien

Voor de vastgelegde **primaire p0-uitkomst bij een koude conditiecachelijn**
herhaalt het contrast `sham_mask` minus `true_mask` zich met +99.902, +99.707
en +99.414 procentpunten. De intervallen voor plain minus sham liggen binnen
de vooraf vastgelegde equivalentiemarge van +/-10 pp. Het verwijderen van de
encoder-load voor de opgevraagde bank of het wijzigen van de bankverwijzingen
van de encoder onderdrukt de publieke respons. Alleen de load van de andere
bank verwijderen laat een grote respons bestaan. Dit versterkt de toeschrijving
aan het geteste coderingspad, terwijl de precieze voorspeller en het transiënte
uitvoeringspad onbepaald blijven.

![Ondersteunende K7- en K8-resultaten bij een koude conditiecachelijn](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Elk punt is een schatting uit één proces. De foutbalken zijn ondersteunende
95% clusterbootstrapintervallen binnen één run. De
[18 bevestigende contrastintervallen](../../results/k7-k8-windows-causal/endpoint-table.csv)
gebruiken de afzonderlijk vastgelegde Bonferroni-regel, met ongeveer 99.17% per
uitkomstmaat. De familie van zes contrasten betreft één gepland herhalingspaar,
niet alle 18 intervallen tegelijk. Er wordt geen gepoold interval of interval over meerdere hosts
getoond. Gecorrigeerde contrasten kunnen groter zijn dan 100 pp.*

**Een belangrijke kanttekening:** in de verkennende p0-controle met een warme
conditiecachelijn verlaagt de sham het percentage cachetreffers met 14.16–16.31 pp.
De equivalentie geldt specifiek voor de vastgelegde primaire uitkomst met een
koude conditiecachelijn, niet voor alle timingcondities.

<details>
<summary>Bekijk het verkennende resultaat met een warme conditiecachelijn</summary>

![Verkennende tellingen voor plain en sham bij een warme conditiecachelijn](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Dit zijn beschrijvende tellingen uit een ondersteunende conditie, buiten de zes
bevestigende contrasten. Ze geven geen eenduidige verklaring voor de verandering
in respons.

</details>

## De gegevens opnieuw controleren

De tellingenaudit gebruikt Python 3.10+ en de standaardbibliotheek.
Voer vanuit de hoofdmap van de repository het volgende uit om drempels,
celtellingen, controlevoorwaarden en primaire puntschattingen te reproduceren:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

Dit leest gearchiveerde gegevens zonder het meetprogramma uit te voeren.
Instructies voor de exacte herhaling van de vastgelegde analyse en de code-audit
staan in de [reproductiehandleiding](../../results/k7-k8-windows-causal/REPRODUCE.md).
De oorspronkelijke bewijs-ZIP's en hashes zijn behouden. Software-CI controleert
parsers, analyses, brongeneratie en documentatie. Die voert de fysieke
Windows-experimenten niet opnieuw uit en certificeert hun mechanisme niet.

De afgeronde studies hebben vastgelegde bronrevisies. Nieuwe metingen vereisen
een eigen plan; breid bestaande pogingen niet uit en vervang ze niet stilzwijgend.
Voor Windows-metingen zijn MSVC x64 Build Tools en een Windows SDK nodig,
maar niet voor de bovenstaande tellingenaudit die alleen gegevens leest.

## Afzonderlijke referentie: de M1-gegevens van de auteurs

De [draagbare heranalyse van de auteursgegevens](../../results/fractal-author-data-reanalysis/README.md)
valideert **48 aangeleverde traces en 240,192 gepubliceerde rijen**. Deze levert
JSON, CSV en figuren zonder dat een Mac nodig is. Deze rijen zijn metingen
van Ravichandran en Yan. Ze staan los van de nieuwe Windows-metingen van dit
project. Het leesprogramma, de herkomstgegevens en het onderscheid in licenties voor het
onderzoekspakket zijn bij het resultaat gedocumenteerd.

## Reikwijdte en beperkingen

- Eén gerapporteerd Ryzen-werkstation. K5 omvat drie starts van Windows;
  K7/K8 gebruiken drie processen per studie binnen één Windows-start, waarbij
  de aanwezigheid van een hypervisor en de VBS-status zijn vastgelegd.
- De K7/K8-modi beïnvloeden zowel training als probing. De controle met private
  banken meet de publieke respons, zonder een sensor voor cachetreffers in de
  private banken. Alle nieuwe K7/K8-metingen blijven in gebruikersmodus (CPL3).
- Alle vastgelegde K7/K8-sensortijden zijn veelvouden van 47 TSC-ticks. Dit zijn
  gekalibreerde metingen van cacheklassen, geen nauwkeurige schattingen van het
  aantal instructiecycli.
- Het precieze voorspellingsmechanisme, een uitsluitend transiënt uitvoeringspad
  en fysieke invloed van gebruikersmodus op kernelmodus zijn nog niet aangetoond.
  Er worden geen nieuwe M1-metingen of vergelijkend ruisvoordeel voor Fractal
  geclaimd.

De [beoordeling van onderzoeksroutes](../../RESEARCH_ROUTE.md) beschrijft de
volgende afgebakende studie op native Linux en de afzonderlijke voorwaarde
van werkend opstarten en exporteren voor fysieke Fractal-metingen.

## Indeling van de repository

| Pad | Doel |
|---|---|
| [`programs/`](../../programs/) | C-programma's en meetlocaties in leesbare assembler |
| [`protocols/`](../../protocols/) | Vastgelegde beslissingen over metingen en analyse |
| [`scripts/`](../../scripts/) | Meetprogramma's, analysetools, herkomstregistratie en audittools |
| [`tests/`](../../tests/) | Softwaretestgegevens en regressiecontroles |
| [`results/`](../../results/) | Oorspronkelijke bewijsstukken, numerieke dossiers en figuren |
| [`RESEARCH_REPORT.md`](../../RESEARCH_REPORT.md) | Geconsolideerde meetresultaten en grenzen aan de conclusies |
| [`RESEARCH_ROUTE.md`](../../RESEARCH_ROUTE.md) | Haalbaarheid op beschikbare hardware en beoordeling van de volgende studie |

## Naamsvermelding en citatie

Onderhouden door [Tymoteusz Netter](https://github.com/xShadyy).
Gebruik [CITATION.cff](../../CITATION.cff) om naar dit onderzoekspakket te
verwijzen. Citeer het oorspronkelijke artikel afzonderlijk bij bespreking
van het Fractal-besturingssysteem of de M1-resultaten:

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Artikel](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Upstream-besturingssysteem](https://github.com/jprx/fractal)
> · [Geëvalueerd onderzoekspakket](https://doi.org/10.5281/zenodo.19556693)

Projectcode: [MIT](../../LICENSE). Upstream-onderdelen en het afzonderlijke
onderzoekspakket van de auteurs behouden hun eigen naamsvermelding en
licentievoorwaarden. Zie het
[dossier met auteursgegevens](../../results/fractal-author-data-reanalysis/README.md).
