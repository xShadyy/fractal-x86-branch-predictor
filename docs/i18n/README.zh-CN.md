<p align="center">
  <img src="../assets/research-banner.png" alt="Fractal x86" width="100%">
</p>

<p align="center">
  <a href="../../README.md#reproduce"><img src="https://img.shields.io/badge/Python-3.10%2B-3156f3?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/License-MIT-263a63?style=flat-square" alt="License: MIT"></a>
</p>

<p align="center">
  <a href="../../README.md">English</a> · <a href="README.pl.md">Polski</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pt-BR.md">Português (Brasil)</a><br>
  <strong>简体中文</strong> · <a href="README.ja.md">日本語</a> · <a href="README.ko.md">한국어</a> · <a href="README.ru.md">Русский</a> · <a href="README.ar.md">العربية</a> · <a href="README.nl.md">Nederlands</a>
</p>

# Fractal x86

在运行 **Windows x64 的 AMD Ryzen 7 9800X3D** 上开展的分支预测与缓存实验，
研究灵感来自 Joseph Ravichandran 和 Mengjia Yan 的
[Fractal](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)。

Windows 实验测得了可重复、对训练敏感的缓存响应。
数据依赖对照与编码器干预用于检验哪些改变会抑制这一响应。

[结果与数据](../../results/k7-k8-windows-causal/README.md) · [复现指南](../../results/k7-k8-windows-causal/REPRODUCE.md)

## 结果

| 研究 | 重复实验单元 | 结果 | 记录 |
|---|---|---|---|
| K3 新标记接收器 | 一个进程 | 结论不确定：56/58 项检查通过；阴性对照未通过 | [K3](../../results/k3-fresh-windows/README.md) |
| K4 上下文对照 | 预实验及三个后续进程 | 每次均通过 58/58 项检查；响应再次出现 | [K4](../../results/k4-context-windows/README.md) |
| K5 依赖关系对照 | 三次 Windows 启动 | 1,179,648 个试次；每次尝试均通过 88/88 项检查 | [K5](../../results/k5-windows-replication/README.md) |
| K7 匹配依赖关系对照 | 同一次系统启动中的三个新进程 | 每次均通过 140/140 项检查；满足冷条件下的主要判据 | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K8 编码器干预 | 同一次系统启动中的三个新进程 | 每次均通过 140/140 项检查；满足公开数据区响应的干预判据 | [K7/K8](../../results/k7-k8-windows-causal/README.md) |
| K6 特权级测试 | QEMU TCG 软件冒烟测试 | CPL/PC 检查通过；尚待收集物理硬件上的测量数据 | [K6](../../results/k5-k6-development/README.md) |

K7/K8 包含 **983,040 个试次**，其中 491,520 个为留出评估试次。
重复性在进程之间评估；同一进程内的各试次共享该次运行的条件。

## 依赖关系与编码器干预的效应

在冷条件下的 p0 主要终点，三次重复实验中 sham 减 true-mask 的对比分别为
+99.902、+99.707 和 +99.414 个百分点。plain 减 sham 的区间均落在预先规定的
+/-10 pp 等效性界限内。移除被查询数据区（bank）的编码器加载指令，或重定向两条
编码器加载指令，都会抑制公开数据区的响应。仅移除另一数据区的加载指令则会保留该响应。

在探索性的暖条件 p0 对照中，sham 使命中率降低了 14.16–16.31 pp。
因此，冷条件下的等效性结论仅适用于该主要终点。

![三次重复实验中的依赖关系与编码器干预效应](../../results/k7-k8-windows-causal/windows-causal-responses.png)

<details>
<summary>暖条件对照</summary>

![探索性暖条件下 plain 与 sham 的计数](../../results/k7-k8-windows-causal/warm-sham-exploratory.png)

</details>

## 复现

使用 Python 3.10+ 及其标准库，从原始归档中重新核查阈值、各实验单元的计数、
检查项和主要点估计值：

```sh
python results/k7-k8-windows-causal/independent-counts/audit_counts.py results/k7-k8-windows-causal/inputs/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip --output out/k7-k8-count-recheck
```

[复现指南](../../results/k7-k8-windows-causal/REPRODUCE.md)说明了如何精确重放分析、
生成图表和检查代码。每项结果均附有原始归档及哈希。

## Fractal 作者数据的再分析

[M1 研究产物再分析](../../results/fractal-author-data-reanalysis/README.md)
核查了 Ravichandran 和 Yan 发布的测量数据中的 **48 份跟踪记录和 240,192 行
已公布数据**。JSON、CSV 和图表与研究产物的来源及许可记录一并提供。

## 测量背景

Windows 采集程序在用户态运行。
K5 在同一台工作站上跨三次系统启动进行。K7/K8 在同一次系统启动中，每项研究
使用三个进程，并记录了 hypervisor 的存在情况和 VBS 状态。干预同时作用于训练
和探测阶段；私有数据区对照观测的是公开数据区的响应。

K7/K8 传感器记录的时间均为 47 个 TSC 时钟滴答的整数倍，用于经过校准的缓存
分类。具体的预测器、瞬态执行路径，以及物理硬件上用户态对内核态的影响，
仍有待查明。

## 引用

由 [Tymoteusz Netter](https://github.com/xShadyy) 维护。
引用本软件时请使用 [CITATION.cff](../../CITATION.cff)。

> Joseph Ravichandran 和 Mengjia Yan。*Fractal: An Operating System Designed
> for Microarchitecture Reverse Engineering*。IEEE Symposium on Security and
> Privacy，2026。[论文](https://people.csail.mit.edu/mengjia/data/2026.SP.fractal.pdf)
> · [Fractal OS](https://github.com/jprx/fractal)
> · [研究产物](https://doi.org/10.5281/zenodo.19556693)

项目代码采用 [MIT 许可证](../../LICENSE)。上游组件和作者发布的研究产物保留
各自的许可证与署名要求。
