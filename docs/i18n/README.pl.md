<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal / x86: niezależne eksperymenty z predykcją rozgałęzień" width="100%">
</p>

<p align="center">
  <a href="../../README.md">English</a> · <strong>Polski</strong> · <a href="README.nl.md">Nederlands</a> · <a href="README.de.md">Deutsch</a>
</p>

<p align="center">
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml"><img src="https://github.com/xShadyy/fractal-x86-branch-predictor/actions/workflows/validation.yml/badge.svg?branch=main" alt="Automatyczna walidacja oprogramowania"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/github/license/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Licencja kodu: MIT"></a>
  <a href="https://github.com/xShadyy/fractal-x86-branch-predictor/commits/main"><img src="https://img.shields.io/github/last-commit/xShadyy/fractal-x86-branch-predictor?style=flat-square&amp;color=287f91" alt="Najnowszy commit w GitHub"></a>
  <a href="#zakres-i-ograniczenia"><img src="https://img.shields.io/badge/measurements-user%20mode-53677d?style=flat-square" alt="Zakres pomiarów: tryb użytkownika"></a>
</p>

<h1 align="center">Kontrolowane eksperymenty z rozgałęzieniami i pamięcią podręczną x86</h1>

Niezależny artefakt badawczy dla **AMD Ryzen 7 9800X3D z systemem Windows
x64**, inspirowany [publikacją Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
Josepha Ravichandrana i Mengjii Yan. Łączy lokalnie ustalone z góry plany,
surowe ślady pomiarowe, udokumentowane pochodzenie plików wykonywalnych,
dopasowane próby kontrolne i niezależnie odtworzone analizy. Obecny etap
zbierania danych w systemie Windows jest zakończony. Zmierzonym wynikiem jest
powtarzalna odpowiedź pamięci podręcznej zależna od sekwencji treningowej.
Jej wrażliwość na zależności danych i interwencje w ścieżkę kodowania
została bezpośrednio przetestowana.

**Oryginalny system Fractal OS i odkrycia dotyczące Apple M1 należą do ich autorów.**
To repozytorium zawiera niezależne eksperymenty x86 oraz osobno oznaczoną
ponowną analizę danych udostępnionych przez autorów.

[Raport badawczy](../../RESEARCH_REPORT.md) · [Materiał dowodowy K7/K8](../../results/k7-k8-windows-causal/README.md) · [Instrukcja odtworzenia](../../results/k7-k8-windows-causal/REPRODUCE.md) · [Dalsze ścieżki badawcze](../../RESEARCH_ROUTE.md)

## Przegląd materiału dowodowego

| Badanie | Jednostka replikacji | Zarejestrowany wynik | Materiał dowodowy |
|---|---|---|---|
| Pierwszy pilotaż K3 | Jeden proces Windows | **Nierozstrzygający:** 56/58 kryteriów kontrolnych; zachowano wyniki nieudanych kontroli negatywnych | [Audyt pilotażu](../../results/k3-fresh-windows/README.md) |
| K4: kontrola kontekstu | Pilotaż i trzy kolejne procesy na jednym hoście | 58/58 kryteriów w każdym; zdefiniowana odpowiedź pojawia się ponownie | [Zapis K4](../../results/k4-context-windows/README.md) |
| K5: kontrola zależności | Trzy odrębne uruchomienia systemu Windows | **1,179,648 epizodów**; 88/88 kryteriów w każdej próbie | [Zamrożona replikacja](../../results/k5-windows-replication/README.md) |
| K7: dopasowana kontrola zależności | Trzy nowe procesy w ramach jednego uruchomienia systemu | 140/140 kryteriów w każdym; spełniono kryteria główne dla zimnej linii warunku | [Wyniki K7/K8 po audycie](../../results/k7-k8-windows-causal/README.md) |
| K8: interwencje w koderze | Trzy nowe procesy w ramach tego samego uruchomienia systemu | 140/140 kryteriów w każdym; spełniono kryteria wpływu interwencji na odpowiedź publicznego banku | [Wyniki K7/K8 po audycie](../../results/k7-k8-windows-causal/README.md) |
| K6: aparatura do badania poziomów uprzywilejowania | Wyłącznie funkcjonalny test wstępny w QEMU TCG | Programowe sprawdzenie rzeczywistych wartości CPL/PC; pomiary na sprzęcie fizycznym oczekują na zebranie | [Zapis prac rozwojowych](../../results/k5-k6-development/README.md) |

K7 i K8 obejmują łącznie **983,040 zarejestrowanych epizodów**, w tym 491,520
epizodów z części walidacyjnej, niewykorzystywanej do kalibracji. Epizody są
obserwacjami wewnątrz procesu, a nie niezależnymi replikacjami. Spełnienie
kryterium kontrolnego potwierdza zdefiniowany dla niego warunek działania
aparatury. Nie potwierdza konkretnego mechanizmu sprzętowego. Wcześniejsze
badania i wyniki nierozstrzygające pozostają w [zbiorczym zapisie](../../RESEARCH_REPORT.md).

## Co pokazują interwencje

Dla zadeklarowanego **głównego punktu końcowego p0 z zimną linią warunku**
różnica sham-minus-true-mask powtarza się na poziomie +99.902, +99.707 i +99.414
punktu procentowego. Przedziały plain-minus-sham mieszczą się we wcześniej
ustalonym marginesie równoważności +/-10 pp. Usunięcie instrukcji odczytu kodera
w badanym banku lub zmiana przypisania banków w koderze tłumi odpowiedź
publicznego banku; usunięcie odczytu wyłącznie z drugiego banku pozostawia dużą
odpowiedź. Wzmacnia to przypisanie wyniku do testowanej ścieżki kodowania,
lecz dokładny predyktor i ścieżka wykonania przejściowego pozostają nierozstrzygnięte.

![Pomocnicze wyniki K7 i K8 dla zimnej linii warunku](../../results/k7-k8-windows-causal/windows-causal-responses.png)

*Każdy punkt jest oszacowaniem dla jednego procesu. Wąsy oznaczają pomocnicze
przedziały 95% z bootstrapu klastrowego wewnątrz pojedynczego uruchomienia.
[18 przedziałów dla kontrastów potwierdzających](../../results/k7-k8-windows-causal/endpoint-table.csv)
korzysta z odrębnej, zamrożonej reguły Bonferroniego, z poziomem około 99.17%
na punkt końcowy. Rodzina sześciu kontrastów obejmuje jedną zaplanowaną parę
powtórzeń, a nie wszystkie 18 przedziałów jednocześnie.
Nie pokazano przedziału łączącego procesy ani obejmującego
różne hosty. Skorygowane kontrasty mogą przekraczać 100 pp.*

**Istotne zastrzeżenie:** w pomocniczej kontroli p0 z ciepłą linią warunku
sham obniża częstość trafień o 14.16–16.31 pp. Jego równoważność dotyczy
zadeklarowanego głównego punktu końcowego z zimną linią warunku, a nie
wszystkich warunków czasowych.

<details>
<summary>Zobacz pomocniczy wynik dla ciepłej linii warunku</summary>

![Pomocnicze zliczenia plain i sham dla ciepłej linii warunku](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

Są to opisowe zliczenia z warunku pomocniczego, spoza sześciu kontrastów
potwierdzających. Nie wskazują jednoznacznie przyczyny zmiany odpowiedzi.

</details>

## Ponowna weryfikacja danych

Audyt zliczeń wymaga języka Python 3.10+ i jego biblioteki standardowej. Z katalogu
głównego repozytorium odtwórz progi, zliczenia w komórkach, kryteria kontrolne
i oszacowania punktowe głównych punktów końcowych:

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

Polecenie odczytuje dane archiwalne bez uruchamiania kolektora. Dokładne
instrukcje odtworzenia zamrożonej analizy i audytu kodu znajdują się
w [instrukcji odtworzenia](../../results/k7-k8-windows-causal/REPRODUCE.md).
Zachowano oryginalne archiwa ZIP z materiałem dowodowym i ich sumy kontrolne.
Programowe testy CI sprawdzają parsery, analizę, generowanie źródeł i dokumentację;
nie powtarzają eksperymentów na fizycznej stacji z systemem Windows
ani nie poświadczają ich mechanizmu.

Zakończone badania mają zamrożone rewizje kodu źródłowego. Nowe pomiary
wymagają własnego planu; nie należy rozszerzać istniejących prób ani
zastępować ich bez wyraźnego odnotowania. Zbieranie danych w systemie Windows wymaga
MSVC x64 Build Tools i Windows SDK. Narzędzia te nie są potrzebne do powyższego
audytu zliczeń, który jedynie odczytuje dane.

## Osobny punkt odniesienia: dane autorów z M1

[Przenośna ponowna analiza danych autorów](../../results/fractal-author-data-reanalysis/README.md)
waliduje **48 udostępnionych śladów i 240,192 opublikowane wiersze danych**.
Udostępnia JSON, CSV i wykresy bez konieczności posiadania komputera Mac.
Te wiersze pochodzą z pomiarów Ravichandrana i Yan. Są oddzielone od nowych
danych zebranych w systemie Windows w ramach tego projektu. Narzędzie do odczytu,
pochodzenie danych i rozróżnienie licencji artefaktów opisano wraz z wynikiem.

## Zakres i ograniczenia

- Jedna zgłoszona stacja robocza Ryzen. K5 obejmuje trzy uruchomienia systemu;
  K7/K8 wykorzystują trzy procesy na badanie w ramach jednego uruchomienia
  systemu, z zarejestrowaną obecnością hiperwizora i stanem VBS.
- Tryby K7/K8 wpływają zarówno na trening, jak i na sondowanie. Kontrola
  z prywatnymi bankami mierzy odpowiedź publicznego banku, bez czujnika
  trafień w pamięci podręcznej dla prywatnego banku.
- Wszystkie zarejestrowane czasy czujników K7/K8 są wielokrotnościami 47 jednostek
  licznika TSC. Są to skalibrowane pomiary klas trafienia w pamięci podręcznej,
  a nie precyzyjne oszacowania liczby cykli wykonania instrukcji.
- Dokładny mechanizm predyktora, wyłącznie przejściowa ścieżka wykonania
  i fizyczny wpływ z trybu użytkownika na jądro pozostają niepotwierdzone. Nie zgłaszamy
  nowych pomiarów M1 ani porównawczej przewagi Fractal pod względem szumu.

[Ocena ścieżek badawczych](../../RESEARCH_ROUTE.md) opisuje kolejne ograniczone
badanie w natywnym systemie Linux oraz odrębny warunek uruchomienia i eksportu
danych wymagany do pomiarów fizycznego Fractal.

## Mapa repozytorium

| Ścieżka | Przeznaczenie |
|---|---|
| [`programs/`](../../programs/) | Programy C i czytelny asembler definiujący miejsca pomiarowe |
| [`protocols/`](../../protocols/) | Zamrożone decyzje dotyczące zbierania i analizy danych |
| [`scripts/`](../../scripts/) | Kolektory, analizatory oraz narzędzia do dokumentowania pochodzenia i audytu |
| [`tests/`](../../tests/) | Programowe dane testowe i testy regresji |
| [`results/`](../../results/) | Oryginalny materiał dowodowy, zapisy liczbowe i wykresy |
| [`RESEARCH_REPORT.md`](../../RESEARCH_REPORT.md) | Zbiorcze wyniki pomiarów i granice wnioskowania |
| [`RESEARCH_ROUTE.md`](../../RESEARCH_ROUTE.md) | Wykonalność sprzętowa i ocena dalszych badań |

## Autorstwo i cytowanie

Projekt utrzymuje [Tymoteusz Netter](https://github.com/xShadyy).
Do cytowania tego artefaktu użyj [CITATION.cff](../../CITATION.cff).
Omawiając system Fractal lub wyniki dotyczące M1, cytuj osobno oryginalną publikację:

> Joseph Ravichandran i Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [Publikacja](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Oryginalny system operacyjny](https://github.com/jprx/fractal)
> · [Oceniony artefakt](https://doi.org/10.5281/zenodo.19556693)

Kod projektu: [MIT](../../LICENSE). Komponenty pochodzące z projektów źródłowych
i osobny artefakt autorów zachowują własne oznaczenia autorstwa i warunki licencyjne. Zobacz
[zapis ponownej analizy danych autorów](../../results/fractal-author-data-reanalysis/README.md).
