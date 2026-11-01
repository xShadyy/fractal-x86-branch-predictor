#!/usr/bin/env python3
"""Reproduce exploratory K1 position plots from one original evidence ZIP.

This diagnostic was chosen after viewing K1; it does not change the frozen
control gate, endpoint, or within-run uncertainty analysis.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from zipfile import ZipFile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_conditional_receiver import BLOCKS, EPISODES, parse_trace, summarize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_zip", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("episode-hit-rates.svg"))
    args = parser.parse_args()
    with ZipFile(args.evidence_zip) as archive:
        traces = [name for name in archive.namelist()
                  if name.endswith(".log") and ".build." not in name and ".strict." not in name]
        if len(traces) != 1:
            parser.error("expected exactly one raw K1 trace")
        trace = parse_trace(archive.read(traces[0]).decode("utf-8-sig"))
    summary = summarize(trace)
    heldout = trace.blocks[BLOCKS // 2:]

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), layout="constrained")
    colors = {0: "#21618c", 1: "#b35423"}
    for p in (0, 1):
        cells = [block[f"arch_skip_p{p}"] for block in heldout]
        threshold = summary["thresholds_ticks"][f"p{p}"]
        episode_rates = [100 * sum(row[i] <= threshold for row in cells) / len(cells)
                         for i in range(EPISODES)]
        cycle_rates = [100 * sum(value <= threshold for row in cells[start:start+16]
                                 for value in row) / (16 * EPISODES)
                       for start in range(0, len(cells), 16)]
        axes[0].plot(range(1, EPISODES + 1), episode_rates, color=colors[p],
                     linewidth=1.8, label=f"probe {p}")
        axes[1].plot(range(1, len(cycle_rates) + 1), cycle_rates, color=colors[p],
                     linewidth=1.8, marker="o", markersize=3.2, label=f"probe {p}")
    for axis in axes:
        axis.axhline(5, color="#7f8c8d", linestyle="--", linewidth=1,
                     label="5% full-cell gate")
        axis.set_ylabel("Architectural-skip hit rate (%)")
        axis.grid(axis="y", color="#e1e5e9", linewidth=.7)
        axis.legend(frameon=False, loc="upper right", fontsize=8)
    axes[0].set_title("Position within a condition cell")
    axes[0].set_xlabel("Episode number (of 64)")
    axes[0].set_xlim(1, EPISODES)
    axes[0].set_xticks([1, 5, 16, 32, 48, 64])
    axes[0].set_ylim(0, 80)
    axes[1].set_title("Held-out time order")
    axes[1].set_xlabel("16-block cycle (of 16)")
    axes[1].set_xlim(1, 16)
    axes[1].set_xticks([1, 4, 8, 12, 16])
    axes[1].set_ylim(0, 55)
    fig.suptitle("K1 first physical run: exploratory skip-control diagnostics\n"
                 f"seed {trace.run['seed']}; 256 held-out blocks; threshold {summary['thresholds_ticks']['p0']} ticks",
                 fontweight="semibold")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output)
    if args.output.suffix.lower() == ".svg":
        svg = args.output.read_text(encoding="utf-8")
        args.output.write_text("\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
                               encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
