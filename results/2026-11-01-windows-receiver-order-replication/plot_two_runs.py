#!/usr/bin/env python3
"""Plot two complete K2 runs from their original, unmodified evidence ZIPs.

Intervals shown here resample cycles within each run. The two sessions are
the units of replication; this script does not estimate between-run certainty.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_receiver_order import parse_trace, summarize  # noqa: E402


def read_run(path: Path) -> tuple[str, str, dict[str, object]]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        raw = [name for name in names if name.endswith(".log") and
               ".build." not in name and ".strict." not in name]
        analyses = [name for name in names if name.endswith(".analysis.json")]
        if len(raw) != 1 or len(analyses) != 1:
            raise ValueError(f"expected one raw trace and one analysis in {path}")
        trace = parse_trace(archive.read(raw[0]).decode("utf-8-sig"))
        summary = summarize(trace)
        archived = json.loads(archive.read(analyses[0]))
        for key, value in summary.items():
            if json.dumps(value, sort_keys=True) != json.dumps(archived[key], sort_keys=True):
                raise ValueError(f"analysis replay mismatch: {path}: {key}")
    if not summary["apparatus_controls_pass"]:
        raise ValueError(f"apparatus gates failed: {path}")
    return trace.host["run_utc"], trace.run["seed"], summary


def utc_label(value: str) -> str:
    timestamp = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    return timestamp.strftime("%H:%M UTC")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_zip", nargs=2, type=Path,
                        help="original K2 ZIPs in execution order")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).with_name("two-run-contrast.svg"))
    args = parser.parse_args()
    runs = [read_run(path) for path in args.evidence_zip]
    if runs[0][0] >= runs[1][0] or runs[0][1] == runs[1][1]:
        parser.error("provide two distinct K2 sessions in chronological order")

    plt.rcParams.update({"font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    fig, axes = plt.subplots(2, 2, figsize=(12.3, 7.5))
    fig.subplots_adjust(top=.82, bottom=.13, left=.17, right=.98,
                        hspace=.45, wspace=.37)
    y = [0, 1]
    labels = [f"Session {i+1} ({utc_label(run[0])})" for i, run in enumerate(runs)]
    colors = {0: "#21618c", 1: "#b35423"}

    for probe in (0, 1):
        ax = axes[0, probe]
        values = [run[2]["outcomes"][f"p{probe}"]["grouped_arch_skip_early_minus_late"]
                  for run in runs]
        for i, value in enumerate(values):
            point = 100 * value["hit_rate_difference"]
            lower, upper = [100 * x for x in value["within_run_cycle_bootstrap_95"]]
            ax.errorbar(point, y[i], xerr=[[point - lower], [upper - point]],
                        fmt="o", color=colors[probe], markersize=7,
                        capsize=4, linewidth=1.6)
            ax.text(min(upper + 2, 78), y[i] + .11, f"{point:+.1f} pp",
                    color=colors[probe], va="bottom")
        ax.axvline(0, color="#8c98a1", linewidth=1)
        if probe == 0:
            ax.axvline(10, color="#7d858b", linewidth=1, linestyle="--",
                       label="frozen +10 pp margin")
            ax.legend(frameon=False, loc="lower right", fontsize=8)
        ax.set_title(f"Grouped entry effect: probe {probe}" +
                     (" (primary)" if probe == 0 else " (secondary)"))
        ax.set_xlabel("First 5 minus later 59 (percentage points)")
        ax.set_xlim(-5, 82)
        ax.set_ylim(-.45, 1.45)
        ax.set_yticks(y, labels)
        ax.invert_yaxis()
        ax.grid(axis="x", color="#e1e5e9", linewidth=.7)

        ax = axes[1, probe]
        for i, run in enumerate(runs):
            rates = run[2]["heldout_hit_rates"]
            grouped = 100 * rates["grouped"][f"arch_skip_p{probe}"]
            interleaved = 100 * rates["interleaved"][f"arch_skip_p{probe}"]
            ax.plot([grouped, interleaved], [y[i], y[i]], color="#c4cbd0", zorder=1)
            ax.scatter(grouped, y[i], marker="o", s=55, color="#286b8c",
                       label="grouped" if i == 0 else None, zorder=3)
            ax.scatter(interleaved, y[i], marker="s", s=55, color="#c37c30",
                       label="interleaved" if i == 0 else None, zorder=3)
            ax.text(grouped + 1.4, y[i] + .13, f"{grouped:.2f}%", fontsize=8)
            ax.text(interleaved + 1.4, y[i] + .13, f"{interleaved:.2f}%", fontsize=8)
        ax.set_title(f"Architectural skip, all 64: probe {probe}")
        ax.set_xlabel("Held-out opposite-line hit rate (%)")
        ax.set_xlim(-1, 80)
        ax.set_ylim(-.45, 1.45)
        ax.set_yticks(y, labels)
        ax.invert_yaxis()
        ax.grid(axis="x", color="#e1e5e9", linewidth=.7)

    handles, legend_labels = axes[1, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(.56, .88),
               ncol=2, frameon=False, fontsize=9)

    seeds = ", ".join(run[1] for run in runs)
    fig.suptitle("K2 receiver-order diagnostic: two same-day Windows sessions\n"
                 f"Seeds {seeds}; 128 held-out macroblocks per session",
                 fontweight="semibold", y=.97)
    fig.text(.5, .055,
             "Intervals resample 16-block cycles within each run; they do not measure between-session uncertainty."
             "  Both runs passed all 20 apparatus gates.",
             ha="center", color="#404d55", fontsize=8.4)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    if args.output.suffix.lower() == ".svg":
        svg = args.output.read_text(encoding="utf-8")
        args.output.write_text("\n".join(line.rstrip() for line in svg.splitlines()) + "\n",
                               encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
