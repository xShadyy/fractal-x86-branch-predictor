<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <a href="README.zh-CN.md">简体中文</a> · <strong>日本語</strong> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

**Windows x64 を実行する AMD Ryzen 7 9800X3D** 上での分岐予測とキャッシュの実験です。
Joseph Ravichandran と Mengjia Yan による
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf) に着想を得ています。

Windows 上の研究では、再現可能で、訓練に応じて変化するキャッシュ応答を測定しています。
データ依存性の対照とエンコーダーへの介入によって、どの変更が応答を抑制するかを調べます。

[結果とデータ](../../results/k7-k8-windows-causal/README.md) · [再現手順](../../results/k7-k8-windows-causal/REPRODUCE.md)

## 結果

| 研究 | 反復の単位 | 結果 | 記録 |
|---|---|---|---|
| K3 新規マーカーの受信側 | 1 プロセス | 判定不能：56/58 項目に合格、陰性対照は不合格 | [K3](../../results/k3-fresh-windows/README.md) |
| K4 コンテキスト対照 | パイロットと後続の 3 プロセス | 各回で 58/58 項目に合格、応答が再び観測された | [K4](../../results/k4-context-windows/README.md) |
| K5 依存性対照 | Windows の起動 3 回 | 1,179,648 試行、各実験で 88/88 項目に合格 | [K5](../../results/k5-windows-replication/README.md) |
| K7 条件を揃えた依存性対照 | 1 回の起動中に新規プロセスを 3 回実行 | 各回で 140/140 項目に合格、コールド条件の主要基準を満たした | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8 エンコーダーへの介入 | 同じ起動中に新規プロセスを 3 回実行 | 各回で 140/140 項目に合格、公開バンクの応答に対する介入基準を満たした | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6 特権レベルのテスト | QEMU TCG によるソフトウェアのスモークテスト | CPL/PC 検査に合格、実機でのデータ収集は未実施 | [K6](../../results/k5-k6-development/README.md) |

K7/K8 には **983,040 試行**が含まれ、そのうち 491,520 試行は評価用に分離されています。
再現性はプロセス間で評価します。同一プロセス内の試行は、その実行の条件を共有しています。

## 依存性とエンコーダーへの介入の効果

コールド条件の主要評価項目 p0 における sham から true-mask を引いた対比は、
3 回の反復でそれぞれ +99.902、+99.707、+99.414 パーセントポイントです。
plain から sham を引いた対比の区間は、事前に規定した +/-10 pp の同等性マージン内に
収まります。測定対象バンクのエンコーダーロードを除去するか、両方のエンコーダーロードを
別のバンクに向けると、公開バンクの応答は抑制されます。他方のバンクのロードだけを
除去した場合、応答は維持されます。

探索的なウォーム条件の p0 対照では、sham によってヒット率が 14.16–16.31 pp 下がります。
したがって、コールド条件での同等性の結果は、その主要評価項目に限られます。

![3 回の反復における依存性とエンコーダーへの介入の効果](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>ウォーム条件の対照</summary>

![探索的なウォーム条件における plain と sham の件数](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## 再現手順

Python 3.10+ とその標準ライブラリを使い、元のアーカイブから閾値、各セルの件数、
判定項目、主要な点推定値を再確認できます。

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

[再現手順のガイド](../../results/k7-k8-windows-causal/REPRODUCE.md)には、分析の正確な再実行、
グラフ生成、コード検査の方法を記載しています。各結果には元のアーカイブとハッシュが
付属しています。

## Fractal 著者データの再分析

[M1 アーティファクトの再分析](../../results/fractal-author-data-reanalysis/README.md)では、
Ravichandran と Yan が公開した測定値から **48 トレース、240,192 行の公開データ**を
検証しています。JSON、CSV、図は、アーティファクトの来歴とライセンスの記録とともに
公開されています。

## 測定条件

Windows の測定プログラムはユーザーモードで動作します。
K5 は 1 台のワークステーションで 3 回の起動にまたがります。K7/K8 は 1 回の起動中に
各研究で 3 プロセスを使い、ハイパーバイザーの有無と VBS の状態を記録しています。
介入は訓練時とプローブ時の両方に適用します。非公開バンクの対照では、公開バンクの
応答を観測します。

K7/K8 のセンサーの測定時間は 47 TSC ティックの倍数で、校正されたキャッシュ分類に
用います。正確な予測器、トランジェント実行の経路、実機上でのユーザー空間からカーネルへの
影響は、引き続き未解明です。

## 引用

[Tymoteusz Netter](https://github.com/xShadyy) が保守しています。
このソフトウェアを引用する際は [CITATION.cff](../../CITATION.cff) を使用してください。

> Joseph Ravichandran and Mengjia Yan. *Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*. IEEE Symposium on Security and
> Privacy, 2026. [論文](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [研究アーティファクト](https://doi.org/10.5281/zenodo.19556693)

プロジェクトのコードには [MIT ライセンス](../../LICENSE)を適用します。上流コンポーネントと
著者のアーティファクトには、それぞれのライセンスと帰属表示が引き続き適用されます。
