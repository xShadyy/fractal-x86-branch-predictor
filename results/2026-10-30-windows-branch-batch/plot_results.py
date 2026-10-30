"""Regenerate the archived two-run figure (requires matplotlib)."""

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_branch_batch import parse_trace, summarize  # noqa: E402


def main() -> None:
    directory = Path(__file__).resolve().parent
    names = ("20261030T000304Z", "20261030T000321Z")
    colors = ("#187db8", "#bc5b22")
    records = []
    for name in names:
        trace = parse_trace((directory / f"branch-batch-windows-{name}.log").read_text())
        records.append((trace, summarize(trace)))

    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans",
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, (estimates, blocks) = plt.subplots(1, 2, figsize=(11.4, 4.4),
                                            gridspec_kw={"width_ratios": [1, 1.5]})
    labels = ("Branch", "Branchless\ncontrol", "Adjusted")
    for run, ((trace, result), color, name) in enumerate(zip(records, colors, names)):
        for category, key in enumerate(("branch", "branchless", "adjusted")):
            contrast = result["contrasts"][key]
            point = contrast["paired_trimmed_mean_ticks_per_iteration"]
            low, high = contrast["within_run_cycle_bootstrap_95_ticks_per_iteration"]
            estimates.errorbar(category + (run - 0.5) * 0.17, point,
                               yerr=[[point - low], [high - point]], fmt="o",
                               markersize=5.5, capsize=3, lw=1.4, color=color,
                               label=name if category == 0 else None)
        values = [(block["branch_random"] - block["branch_periodic"]
                   - block["branchless_random"] + block["branchless_periodic"])
                  / int(trace.run["iterations"]) for block in trace.blocks]
        blocks.scatter(np.arange(len(values)), values, s=10, alpha=0.55,
                       color=color, label=name)
        blocks.axhline(result["contrasts"]["adjusted"]["paired_trimmed_mean_ticks_per_iteration"],
                       lw=1.1, color=color)

    estimates.axhline(0, lw=0.8, color="#444444")
    estimates.set_xticks(range(3), labels)
    estimates.set_ylabel("Random − periodic (TSC ticks / iteration)")
    estimates.set_title("Paired contrasts and within-run intervals")
    estimates.set_ylim(-1.2, 18.4)
    estimates.grid(axis="y", alpha=0.2)
    estimates.legend(frameon=False, loc="upper center", fontsize=8)
    blocks.set(xlabel="Block index", ylabel="Adjusted contrast (TSC ticks / iteration)",
               title="Complete blocks, including outliers", xlim=(-2, 145), ylim=(7, 24))
    blocks.grid(axis="y", alpha=0.2)
    blocks.legend(frameon=False, loc="upper right", fontsize=8)
    fig.suptitle("Windows user-mode branch patterns · two runs with the same fixed seed",
                 fontsize=12, weight="bold")
    fig.text(0.5, 0.005,
             "Error bars resample six-block cycles within each run; they do not quantify between-seed or between-session uncertainty.",
             ha="center", fontsize=8.5, color="#444444")
    fig.tight_layout(rect=(0, 0.045, 1, 0.93))
    fig.savefig(directory / "branch-batch-summary.svg", metadata={"Date": None})
    fig.savefig(directory / "branch-batch-summary.png", dpi=180)


if __name__ == "__main__":
    main()
