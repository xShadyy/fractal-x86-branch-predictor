#!/usr/bin/env python3
"""Reproduce descriptive K2 plots directly from one original evidence ZIP.

The plotted held-out cycles and episodes are dependent observations from a
single host run. The frozen primary endpoint and its cycle-bootstrap interval
remain in the K2 analyzer; these plots do not add an inference test.
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
from analyze_receiver_order import BLOCKS, EARLY, EPISODES, parse_trace, summarize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_zip", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("episode-hit-rates.svg"))
    args = parser.parse_args()
    with ZipFile(args.evidence_zip) as archive:
        traces = [name for name in archive.namelist()
                  if name.endswith(".log") and ".build." not in name and ".strict." not in name]
        if len(traces) != 1:
            parser.error("expected exactly one raw K2 trace")
        trace = parse_trace(archive.read(traces[0]).decode("utf-8-sig"))
    summary = summarize(trace)
    heldout = trace.blocks[BLOCKS // 2:]
    if len(heldout) != 128:
        parser.error("unexpected number of held-out macroblocks")

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.4), layout="constrained")
    colors = {0: "#21618c", 1: "#b35423"}
    for p in (0, 1):
        threshold = summary["thresholds_ticks"][f"p{p}"]
        for mode, ax in (("grouped", axes[0, 0]), ("interleaved", axes[0, 1])):
            cells = [block[mode][f"arch_skip_p{p}"] for block in heldout]
            episode_rates = [100 * sum(row[i] <= threshold for row in cells) / len(cells)
                             for i in range(EPISODES)]
            ax.plot(range(1, EPISODES + 1), episode_rates, color=colors[p],
                    linewidth=1.8, label=f"probe {p} (≤{threshold} ticks)")

        grouped_differences = summary["outcomes"][f"p{p}"][
            "grouped_entry_differences_by_heldout_cycle"]
        interleaved_rates = summary["outcomes"][f"p{p}"][
            "interleaved_skip_full_cell_rates_by_heldout_cycle"]
        axes[1, 0].plot(range(1, len(grouped_differences) + 1),
                        [100 * rate for rate in grouped_differences],
                        color=colors[p], marker="o", linewidth=1.7, label=f"probe {p}")
        axes[1, 1].plot(range(1, len(interleaved_rates) + 1),
                        [100 * rate for rate in interleaved_rates],
                        color=colors[p], marker="o", linewidth=1.7, label=f"probe {p}")

    for mode, ax in (("Grouped", axes[0, 0]), ("Interleaved", axes[0, 1])):
        ax.axvline(EARLY + .5, color="#6f7b86", linewidth=1,
                   linestyle="--", label="first 5 / later 59")
        ax.set_title(f"{mode}: skip hits by occurrence")
        ax.set_xlabel("Occurrence within a cell (of 64)")
        ax.set_ylabel("Architectural-skip hit rate (%)")
        ax.set_xlim(1, EPISODES)
        ax.set_ylim(0, 100)
        ax.set_xticks([1, 5, 16, 32, 48, 64])
        ax.grid(axis="y", color="#e1e5e9", linewidth=.7)
        ax.legend(frameon=False, fontsize=8)

    axes[1, 0].set_title("Grouped: first 5 minus later 59")
    axes[1, 0].set_ylabel("Skip-hit difference (percentage points)")
    axes[1, 0].set_ylim(-10, 90)
    axes[1, 1].set_title("Interleaved: all 64 occurrences")
    axes[1, 1].set_ylabel("Architectural-skip hit rate (%)")
    axes[1, 1].set_ylim(0, 100)
    for ax in axes[1]:
        ax.set_xlabel("16-block cycle within held-out half")
        ax.set_xlim(1, 8)
        ax.set_xticks(range(1, 9))
        ax.grid(axis="y", color="#e1e5e9", linewidth=.7)
        ax.legend(frameon=False, fontsize=8)

    fig.suptitle("K2 first physical run: descriptive receiver-order diagnostics\n"
                 f"seed {trace.run['seed']}; 128 held-out macroblocks; one Windows host/session",
                 fontweight="semibold")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    if args.output.suffix.lower() == ".svg":
        svg = args.output.read_text(encoding="utf-8")
        args.output.write_text("\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
                               encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
