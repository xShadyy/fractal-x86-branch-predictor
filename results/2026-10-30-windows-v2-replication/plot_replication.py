"""Plot run-level estimates for the six archived Windows v2 replications.

Requires matplotlib. The manifest and paired logs/EXEs are validated by the
same series analyzer used for the numerical report. The earlier pilot is not
part of this figure.
"""

from pathlib import Path
import sys

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from summarize_branch_batch_series import summarize_series  # noqa: E402


def main() -> None:
    directory = Path(__file__).resolve().parent
    series = summarize_series(directory / "manifest.json")
    sessions = series["sessions"]
    if len(sessions) != 2 or any(len(session["runs"]) != 3 for session in sessions):
        raise ValueError("this frozen figure requires three runs in each of two sessions")

    x_positions = [1, 2, 3, 5, 6, 7]
    labels = [f"S{session_index} / R{run_index}"
              for session_index in (1, 2) for run_index in (1, 2, 3)]
    runs = [run for session in sessions for run in session["runs"]]
    styles = (
        ("branch", "Target read", "#0072B2", "o", -0.13),
        ("branch_no_load", "No target read", "#D55E00", "s", 0.00),
        ("adjusted", "Target read, adjusted", "#009E73", "D", 0.13),
    )

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "svg.hashsalt": "fractal-x86-v2-replication-20261030",
    })
    figure, (branches, control) = plt.subplots(
        1, 2, figsize=(11.6, 4.6), sharex=True,
        gridspec_kw={"width_ratios": [1.55, 1]},
    )

    for key, label, color, marker, offset in styles:
        values = [run["contrasts"][key]["paired_trimmed_mean_ticks_per_iteration"]
                  for run in runs]
        branches.scatter([x + offset for x in x_positions], values,
                         s=54, c=color, marker=marker, label=label,
                         linewidths=0.6, edgecolors="#222222", zorder=3)

    baseline = [run["contrasts"]["branchless"][
        "paired_trimmed_mean_ticks_per_iteration"] for run in runs]
    control.scatter(x_positions, baseline, s=54, c="#7354A6", marker="o",
                    linewidths=0.6, edgecolors="#222222", zorder=3)
    control.axhline(0, color="#555555", lw=0.9, ls="--", zorder=1)

    for axis in (branches, control):
        axis.axvline(4, color="#999999", lw=1, ls=":", zorder=1)
        axis.set_xlim(0.55, 7.45)
        axis.set_xticks(x_positions, labels)
        axis.grid(axis="y", color="#dddddd", linewidth=0.7, zorder=0)
        axis.set_xlabel("Session / run")

    branches.set_title("Conditional branch contrasts (zoomed scale)")
    branches.set_ylabel("Shuffled − periodic (TSC ticks / iteration)")
    branches.set_ylim(16.2, 16.85)
    branches.set_yticks([16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8])
    handles, legend_labels = branches.get_legend_handles_labels()
    figure.legend(handles, legend_labels, loc="upper center",
                  bbox_to_anchor=(0.36, 0.925), ncol=3, frameon=False,
                  fontsize=9)

    control.set_title("Branchless comparator (small scale)")
    control.set_ylabel("Shuffled − periodic (TSC ticks / iteration)")
    control.set_ylim(-0.004, 0.001)
    control.set_yticks([-0.004, -0.003, -0.002, -0.001, 0.0, 0.001])

    figure.suptitle("Windows branch-pattern replication: six runs across two sessions",
                     fontsize=13, weight="bold")
    figure.text(
        0.5, 0.008,
        "Points are paired-block 10% trimmed means for complete runs. No across-session uncertainty interval is estimated; pilot excluded.",
        ha="center", fontsize=8.5, color="#444444",
    )
    figure.tight_layout(rect=(0, 0.065, 1, 0.86))
    figure.savefig(directory / "branch-batch-replication.svg",
                   metadata={"Date": None})
    figure.savefig(directory / "branch-batch-replication.png", dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
