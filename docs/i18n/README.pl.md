<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="Licencja: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <strong>Polski</strong> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

Eksperymenty z predykcją rozgałęzień i pamięcią podręczną na **AMD Ryzen 7
9800X3D z systemem Windows x64**, inspirowane pracą
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
Josepha Ravichandrana i Mengjii Yan. Dokumentacja badań obejmuje ustalone
z góry protokoły, surowe ślady pomiarowe, dopasowane próby kontrolne,
sumy kontrolne plików wykonywalnych i analizy, które można odtworzyć.

Badania w systemie Windows mierzą powtarzalną odpowiedź pamięci podręcznej
zależną od sekwencji treningowej. Kontrole zależności i interwencje w koderze
sprawdzają, które zmiany ją tłumią.

[Raport badawczy](../../RESEARCH_REPORT.md) · [Wyniki i dane](../../results/k7-k8-windows-causal/README.md) · [Instrukcja odtworzenia](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Dalsze badania](../../RESEARCH_ROUTE.md)

## Wyniki

| Badanie | Replikacja | Wynik | Zapis |
|---|---|---|---|
| K3: nowy odbiornik | Jeden proces | Nierozstrzygający: 56/58 kryteriów kontrolnych; kontrole negatywne nie powiodły się | [K3](../../results/k3-fresh-windows/README.md) |
| K4: kontrola kontekstu | Pilotaż i trzy kolejne procesy | 58/58 kryteriów w każdym; odpowiedź pojawia się ponownie | [K4](../../results/k4-context-windows/README.md) |
| K5: kontrola zależności | Trzy uruchomienia systemu Windows | 1,179,648 epizodów; 88/88 kryteriów w każdej próbie | [K5](../../results/k5-windows-replication/README.md) |
| K7: dopasowana kontrola zależności | Trzy nowe procesy w ramach jednego uruchomienia systemu | 140/140 kryteriów w każdym; spełniono kryteria główne dla zimnej linii warunku | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8: interwencje w koderze | Trzy nowe procesy w ramach tego samego uruchomienia systemu | 140/140 kryteriów w każdym; spełniono kryteria wpływu interwencji na odpowiedź publicznego banku | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6: test uprzywilejowania | Programowy test wstępny w QEMU TCG | Sprawdzenie CPL/PC zakończone powodzeniem; pomiary na sprzęcie fizycznym oczekują na zebranie | [K6](../../results/k5-k6-development/README.md) |

K7/K8 obejmują **983,040 epizodów**, w tym 491,520 z części walidacyjnej.
Replikację ocenia się między procesami; epizody wewnątrz procesu mają
te same warunki uruchomienia.

## Wpływ zależności i kodera

Dla głównego punktu końcowego p0 z zimną linią warunku różnica
sham-minus-true-mask wynosi +99.902, +99.707 i +99.414 punktu procentowego
w trzech powtórzeniach. Przedziały plain-minus-sham mieszczą się we wcześniej
ustalonym marginesie równoważności +/-10 pp. Usunięcie odczytu kodera
w badanym banku lub przekierowanie obu odczytów kodera tłumi odpowiedź
publicznego banku. Usunięcie odczytu wyłącznie z drugiego banku ją zachowuje.

![Wpływ zależności i kodera w trzech powtórzeniach](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Punkty przedstawiają oszacowania dla procesów, a wąsy pomocnicze przedziały
95% z bootstrapu klastrowego wewnątrz pojedynczego uruchomienia.
[18 przedziałów dla kontrastów głównych](../../results/k7-k8-windows-causal/endpoint-table.csv)
wykorzystuje zamrożoną regułę Bonferroniego, z poziomem około 99.17% na punkt
końcowy. Każda rodzina sześciu kontrastów obejmuje jedną zaplanowaną parę
powtórzeń. Skorygowane kontrasty mogą przekraczać 100 pp.*

W pomocniczej kontroli p0 z ciepłą linią warunku sham obniża częstość trafień
o 14.16–16.31 pp. Równoważność dla zimnej linii warunku dotyczy więc
tego konkretnego głównego punktu końcowego.

<details>
<summary>Kontrola z ciepłą linią warunku</summary>

![Pomocnicze zliczenia plain i sham dla ciepłej linii warunku](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Opisowe zliczenia z pomocniczego warunku z ciepłą linią, spoza sześciu
kontrastów głównych.

</details>

## Odtworzenie wyników

Użyj języka Python 3.10+ i jego biblioteki standardowej, aby ponownie sprawdzić
progi, zliczenia w komórkach, kryteria kontrolne i główne oszacowania punktowe
na podstawie oryginalnego archiwum:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

[Instrukcja odtworzenia](../../results/k7-k8-windows-causal/REPRODUCE.md) opisuje
wierne odtworzenie analizy, generowanie wykresów i inspekcję kodu. Każdemu
wynikowi towarzyszą oryginalne archiwa i sumy kontrolne.
[Walidacja oprogramowania](https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml)
sprawdza dane testowe analiz, wygenerowane źródła i dokumentację.

Zakończone badania zachowują zamrożone plany i rewizje kodu źródłowego.
Nowe pomiary zaczynają się od nowego planu. Zbieranie danych w systemie
Windows wymaga MSVC x64 Build Tools i Windows SDK.

## Ponowna analiza danych autorów Fractal

[Ponowna analiza artefaktu M1](../../results/fractal-author-data-reanalysis/README.md)
sprawdza **48 śladów i 240,192 opublikowane wiersze** z udostępnionych pomiarów
Ravichandrana i Yan. JSON, CSV i wykresy są dostępne wraz z dokumentacją
pochodzenia artefaktu i jego licencji.

## Kontekst pomiarów

Kolektory Windows działają w trybie użytkownika. K5 obejmuje trzy uruchomienia
systemu na jednej stacji roboczej. K7/K8 wykorzystują trzy procesy na badanie
w ramach jednego uruchomienia systemu, z zarejestrowaną obecnością hiperwizora
i stanem VBS. Interwencje obejmują zarówno trening, jak i sondowanie;
kontrola z prywatnymi bankami obserwuje odpowiedź publicznego banku.

Czasy czujników K7/K8 są wielokrotnościami 47 jednostek licznika TSC
i umożliwiają skalibrowaną klasyfikację trafień w pamięci podręcznej.
Dokładny predyktor, ścieżka wykonania przejściowego i fizyczny wpływ
z trybu użytkownika na jądro pozostają otwartymi pytaniami.
Dokument [Dalsze badania](../../RESEARCH_ROUTE.md) opisuje ścieżki zbierania danych
w natywnym systemie Linux i na sprzęcie fizycznym z Fractal.

## Pliki projektu

| Ścieżka | Zawartość |
|---|---|
| [`programs/`](../../programs/) | Kolektory C i asemblerowe miejsca pomiarowe |
| [`protocols/`](../../protocols/) | Plany zbierania danych i reguły analizy |
| [`scripts/`](../../scripts/) | Narzędzia do zbierania i analizy danych oraz dokumentowania pochodzenia |
| [`tests/`](../../tests/) | Programowe dane testowe i testy regresji |
| [`results/`](../../results/) | Surowy materiał dowodowy, tabele liczbowe i wykresy |

## Cytowanie

Projekt utrzymuje [Tymoteusz Netter](https://github.com/xShadyy).
Do cytowania oprogramowania użyj [CITATION.cff](../../CITATION.cff).

> Joseph Ravichandran i Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Publikacja](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [Artefakt badawczy](https://doi.org/10.5281/zenodo.19556693)

Kod projektu jest objęty [licencją MIT](../../LICENSE). Komponenty pochodzące
z projektów źródłowych i artefakt autorów zachowują własne licencje
oraz oznaczenia autorstwa.
