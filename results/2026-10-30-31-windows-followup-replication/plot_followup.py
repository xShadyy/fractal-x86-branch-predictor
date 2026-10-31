#!/usr/bin/env python3
"""Plot individual follow-up runs with their within-run intervals only.

Run from any directory:
  python3 results/2026-10-30-31-windows-followup-replication/plot_followup.py

Requires Matplotlib. Reads the manifest and raw traces, reruns the frozen
analyzers, and checks each EXE hash against its trace. The figure deliberately
has no pooled or across-session confidence interval.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from analyze_decision_source import parse_trace as parse_a, summarize as analyze_a  # noqa: E402
from analyze_history_probe import parse_trace as parse_b, summarize as analyze_b  # noqa: E402


def _runs() -> dict[str, list[dict[str, object]]]:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or len(manifest.get("sessions", [])) != 2:
        raise ValueError("expected two-session manifest")
    groups: dict[str, list[dict[str, object]]] = {
        "decision_source": [], "history_probe": [],
    }
    for session_index, session in enumerate(manifest["sessions"]):
        counts = {key: 0 for key in groups}
        for item in session["runs"]:
            study = item["study"]
            if study not in groups:
                raise ValueError(f"unexpected study {study}")
            trace_path = ROOT / item["trace"]
            exe_path = ROOT / item["exe"]
            if not trace_path.resolve().is_relative_to(ROOT) or not exe_path.resolve().is_relative_to(ROOT):
                raise ValueError("manifest path leaves result directory")
            parse, analyze = ((parse_a, analyze_a) if study == "decision_source"
                              else (parse_b, analyze_b))
            trace = parse(trace_path.read_text(encoding="utf-8-sig"))
            summary = analyze(trace)
            if hashlib.sha256(exe_path.read_bytes()).hexdigest() != trace.binary_sha256:
                raise ValueError(f"EXE SHA-256 differs from {trace_path.name}")
            counts[study] += 1
            groups[study].append({"session": session_index, "number": counts[study],
                                  "summary": summary})
        if any(count != 3 for count in counts.values()):
            raise ValueError("expected three runs of each study per session")
    return groups


def _estimate(run: dict[str, object], contrast: str, study: str) -> tuple[float, float, float]:
    entry = run["summary"]["contrasts"][contrast]
    unit = "iteration" if study == "decision_source" else "probe"
    value = entry[f"paired_trimmed_mean_ticks_per_{unit}"]
    interval = (entry["within_run_eight_block_bootstrap_95_ticks_per_iteration"]
                if study == "decision_source" else
                entry["within_run_cycle_bootstrap_95_ticks_per_probe"])
    return value, interval[0], interval[1]


def main() -> None:
    groups = _runs()
    positions = [6, 5, 4, 3, 2, 1]
    labels = ["30 Oct · 1", "30 Oct · 2", "30 Oct · 3",
              "31 Oct · 1", "31 Oct · 2", "31 Oct · 3"]

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.titlesize": 12, "axes.labelsize": 10,
        "svg.fonttype": "none", "savefig.facecolor": "white",
    })
    figure, (left, right) = plt.subplots(1, 2, figsize=(13.2, 6.0), sharey=True)
    figure.suptitle("Windows branch studies: individual runs on two days",
                     x=0.035, y=0.975, ha="left", fontsize=15, fontweight="semibold")

    for axis in (left, right):
        axis.set_ylim(0.45, 6.55)
        axis.axhspan(0.5, 3.5, color="#F1F5F8", zorder=0)
        axis.axhline(3.5, color="#CBD3DB", linewidth=0.8, zorder=1)
        axis.set_yticks(positions, labels)
        axis.tick_params(axis="y", length=0, pad=8)
        axis.grid(axis="x", color="#DFE4EA", linewidth=0.75, zorder=0)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.spines["bottom"].set_color("#9DA8B4")

    a_values = [_estimate(run, "primary_interaction", "decision_source")
                for run in groups["decision_source"]]
    for y, (value, low, high) in zip(positions, a_values):
        left.errorbar(value, y, xerr=[[value - low], [high - value]],
                      fmt="o", markersize=6.4, color="#1864A0", ecolor="#1864A0",
                      capsize=3.0, elinewidth=1.6, zorder=3)
    a_lo = min(low for _, low, _ in a_values)
    a_hi = max(high for _, _, high in a_values)
    left.set_xlim(a_lo - 0.23, a_hi + 0.23)
    left.set_title("A  Decision-source interaction", loc="left", pad=12,
                   fontweight="semibold")
    left.set_xlabel("TSC ticks per iteration (zoomed scale)", labelpad=12)
    left.set_ylabel("Session and run", labelpad=12)

    b0 = [_estimate(run, "adjusted0", "history_probe")
          for run in groups["history_probe"]]
    b1 = [_estimate(run, "adjusted1", "history_probe")
          for run in groups["history_probe"]]
    for y, (value, low, high) in zip(positions, b0):
        right.errorbar(value, y + 0.13, xerr=[[value - low], [high - value]],
                       fmt="o", markersize=6.1, color="#BA6315", ecolor="#BA6315",
                       capsize=2.8, elinewidth=1.45, zorder=3)
    for y, (value, low, high) in zip(positions, b1):
        right.errorbar(value, y - 0.13, xerr=[[value - low], [high - value]],
                       fmt="s", markersize=5.6, color="#705294", ecolor="#705294",
                       capsize=2.8, elinewidth=1.45, zorder=3)
    right.axvline(0, color="#4A5865", linestyle=(0, (4, 3)), linewidth=1.1)
    b_lo = min(low for _, low, _ in b0 + b1)
    b_hi = max(high for _, _, high in b0 + b1)
    right.set_xlim(min(-0.5, b_lo - 0.4), b_hi + 0.45)
    right.set_title("B  History probe, sham-adjusted", loc="left", pad=12,
                    fontweight="semibold")
    right.set_xlabel("TSC ticks per fixed 16-call probe", labelpad=12)
    right.legend(handles=[
        Line2D([0], [0], color="#BA6315", marker="o", linewidth=1.4,
               label="Probe 0: mismatch − match"),
        Line2D([0], [0], color="#705294", marker="s", linewidth=1.4,
               label="Probe 1: mismatch − match"),
    ], loc="upper center", bbox_to_anchor=(0.5, -0.19),
       ncol=2, columnspacing=1.1, frameon=False, fontsize=8.6)

    figure.text(0.035, 0.035,
                "Points: prespecified 10% trimmed paired-block estimates. Whiskers: 95% cycle bootstrap intervals within each run. No across-run interval.",
                fontsize=8.8, color="#43505A")
    figure.subplots_adjust(left=0.145, right=0.985, top=0.87,
                           bottom=0.25, wspace=0.19)
    base = ROOT / "followup-replication"
    figure.savefig(base.with_suffix(".svg"))
    figure.savefig(base.with_suffix(".png"), dpi=200)
    plt.close(figure)
    print(f"Saved {base.with_suffix('.svg').name} and {base.with_suffix('.png').name}")


if __name__ == "__main__":
    main()
