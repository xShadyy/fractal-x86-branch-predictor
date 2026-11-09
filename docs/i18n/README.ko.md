<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a> · <strong>한국어</strong> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

**Windows x64를 실행하는 AMD Ryzen 7 9800X3D**에서 수행한 분기 예측 및 캐시 실험입니다.
Joseph Ravichandran과 Mengjia Yan의
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)에서 착안했습니다.

Windows 연구에서는 반복해서 관측되며 훈련에 민감하게 반응하는 캐시 응답을 측정합니다.
데이터 의존성 대조군과 인코더 개입을 통해 어떤 변경이 이 응답을 억제하는지 확인합니다.

[결과 및 데이터](../../results/k7-k8-windows-causal/README.md) · [재현 안내](../../results/k7-k8-windows-causal/REPRODUCE.md)

## 결과

| 연구 | 반복 단위 | 결과 | 기록 |
|---|---|---|---|
| K3 새 마커 수신부 | 프로세스 하나 | 결론 불확정: 56/58개 검사 통과, 음성 대조군 실패 | [K3](../../results/k3-fresh-windows/README.md) |
| K4 문맥 대조군 | 예비 실험 및 후속 프로세스 세 개 | 각각 58/58개 검사 통과, 응답 재관측 | [K4](../../results/k4-context-windows/README.md) |
| K5 의존성 대조군 | Windows 부팅 세 번 | 1,179,648개 에피소드, 각 시도에서 88/88개 검사 통과 | [K5](../../results/k5-windows-replication/README.md) |
| K7 조건을 맞춘 의존성 대조군 | 한 번의 부팅에서 새 프로세스 세 개 | 각각 140/140개 검사 통과, 콜드 조건의 주 평가 기준 충족 | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8 인코더 개입 | 같은 부팅에서 새 프로세스 세 개 | 각각 140/140개 검사 통과, 공개 캐시 응답에 대한 개입 기준 충족 | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6 권한 수준 시험 | QEMU TCG 소프트웨어 스모크 테스트 | CPL/PC 검사 통과, 실물 하드웨어 데이터 수집 대기 중 | [K6](../../results/k5-k6-development/README.md) |

K7/K8에는 **983,040개 에피소드**가 있으며, 이 중 491,520개는 평가용으로 분리해 두었습니다.
반복 재현성은 프로세스 간에 평가합니다. 한 프로세스 안의 에피소드는 같은 실행 조건을 공유합니다.

## 의존성 및 인코더 개입의 효과

콜드 조건의 p0 주 평가변수에서 sham에서 true-mask를 뺀 대비는 세 번의 반복에서 각각
+99.902, +99.707, +99.414 퍼센트포인트입니다. plain에서 sham을 뺀 대비의 구간은
사전에 정한 +/-10 pp 동등성 한계 안에 들어갑니다. 조회 대상 뱅크의 인코더 로드를
제거하거나 두 인코더 로드를 모두 다른 뱅크로 돌리면 공개 캐시 응답이 억제됩니다.
다른 뱅크의 로드만 제거하면 응답은 유지됩니다.

탐색적 웜 조건의 p0 대조군에서는 sham이 적중률을 14.16–16.31 pp 낮춥니다.
따라서 콜드 조건의 동등성 결과는 해당 주 평가변수에 한정됩니다.

![세 번의 반복에서 나타난 의존성 및 인코더 개입의 효과](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>웜 조건 대조군</summary>

![탐색적 웜 조건에서 plain과 sham의 집계 건수](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## 재현

Python 3.10+와 표준 라이브러리로 원본 아카이브의 임계값, 셀별 건수, 검사 항목,
주요 점추정값을 다시 확인할 수 있습니다.

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

[재현 안내](../../results/k7-k8-windows-causal/REPRODUCE.md)에는 분석의 정확한 재실행,
차트 생성, 코드 검토 방법이 나와 있습니다. 각 결과에는 원본 아카이브와 해시가 함께 제공됩니다.

## Fractal 저자 데이터 재분석

[M1 연구 아티팩트 재분석](../../results/fractal-author-data-reanalysis/README.md)은
Ravichandran과 Yan이 공개한 측정 데이터의 **트레이스 48개와 공개 데이터 240,192행**을
확인합니다. JSON, CSV, 그림은 아티팩트의 출처 및 라이선스 기록과 함께 제공됩니다.

## 측정 환경

Windows 수집 프로그램은 사용자 모드에서 실행됩니다.
K5는 한 워크스테이션에서 세 번의 부팅에 걸쳐 수행했습니다. K7/K8은 한 번의 부팅에서
연구마다 프로세스 세 개를 사용하며, 하이퍼바이저 유무와 VBS 상태를 기록했습니다.
개입은 훈련과 탐색 단계 모두에 적용됩니다. 비공개 뱅크 대조군이 관측하는 것은
공개 캐시 응답입니다.

K7/K8 센서의 측정 시간은 47 TSC 틱의 배수이며, 보정된 캐시 분류에 사용됩니다.
정확한 예측기, 트랜지언트 실행 경로, 실물 하드웨어에서 사용자 영역이 커널에 미치는
영향은 아직 밝혀지지 않았습니다.

## 인용

[Tymoteusz Netter](https://github.com/xShadyy)가 관리합니다.
이 소프트웨어를 인용할 때는 [CITATION.cff](../../CITATION.cff)를 사용하세요.

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [논문](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [연구 아티팩트](https://doi.org/10.5281/zenodo.19556693)

프로젝트 코드는 [MIT 라이선스](../../LICENSE)를 사용합니다. 업스트림 구성 요소와
저자의 아티팩트에는 각각의 라이선스와 출처 표시 조건이 적용됩니다.
