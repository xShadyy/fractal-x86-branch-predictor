"""Render frozen K7/K8 summaries with Matplotlib and Seaborn, without new inference."""
from __future__ import annotations
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import seaborn as sns

ROOT = Path(__file__).resolve().parent
BLUE, TEAL, ORANGE = '#2457C5', '#007F82', '#C26B19'
INK, MUTED, GRID = '#182A43', '#52647B', '#DDE5EF'
COLORS = {'p0': BLUE, 'p1': TEAL}
MARKERS = {1: 'o', 2: 's', 3: '^'}
INPUTS = ['supporting-mode-table.csv', 'endpoint-table.csv', 'warm-sham-counts.json',
          *[f'attempt-{n:02d}-replayed-analysis.json' for n in range(1, 7)]]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(name):
    with (ROOT / name).open(newline='', encoding='utf-8') as source:
        return list(csv.DictReader(source))


def validate_inputs():
    supporting, endpoints = read_csv('supporting-mode-table.csv'), read_csv('endpoint-table.csv')
    analyses = {n: json.loads((ROOT / f'attempt-{n:02d}-replayed-analysis.json').read_text()) for n in range(1, 7)}
    if len(supporting) != 60 or len(endpoints) != 18:
        raise ValueError('Expected all 60 supporting outcomes and 18 primary contrasts')
    for row in supporting:
        metric = analyses[int(row['attempt'])]['outcomes'][row['bank']][row['mode']]['adjusted']
        actual = [float(row[k]) for k in ('adjusted_pp', 'lower95_pp', 'upper95_pp')]
        if actual != [100 * metric['hit_rate_difference'], *[100 * v for v in metric['ci']]] or metric['nominal_confidence'] != .95:
            raise ValueError('Supporting CSV differs from frozen 95% analysis')
    for row in endpoints:
        metric = analyses[int(row['attempt'])]['primary_endpoints'][row['endpoint']]
        actual = [float(row[k]) for k in ('estimate_pp', 'lower_family_pp', 'upper_family_pp')]
        if actual != [100 * metric['hit_rate_difference'], *[100 * v for v in metric['ci']]] or metric['nominal_confidence'] != 1 - .05 / 6:
            raise ValueError('Primary CSV differs from frozen six-contrast analysis')
    warm = json.loads((ROOT / 'warm-sham-counts.json').read_text())['rows']
    if len(warm) != 6:
        raise ValueError('Expected six recorded warm-condition counts')
    for row in warm:
        rate = analyses[2 * row['repetition']]['heldout_hit_rates'][row['mode']]['warm_mismatch_p0']
        if row['n'] != 1024 or row['hits'] != round(rate * 1024) or row['rate_percent'] != 100 * rate:
            raise ValueError('Warm-condition counts differ from frozen analysis')
    return supporting, warm


def style():
    sns.set_theme(context='notebook', style='ticks', palette=[BLUE, TEAL, ORANGE], rc={
        'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.labelsize': 11,
        'axes.labelcolor': MUTED, 'axes.edgecolor': GRID, 'axes.linewidth': .8,
        'text.color': INK, 'xtick.color': MUTED, 'ytick.color': INK,
        'xtick.labelsize': 10, 'ytick.labelsize': 11, 'figure.facecolor': 'white',
        'axes.facecolor': 'white', 'savefig.facecolor': 'white', 'pdf.fonttype': 42,
        'ps.fonttype': 42, 'svg.fonttype': 'none', 'svg.hashsalt': 'fractal-k7-k8-render-v2'})


def export(fig, stem):
    paths = []
    for extension in ('png', 'pdf', 'svg'):
        path = ROOT / f'{stem}.{extension}'
        metadata = {'CreationDate': None, 'ModDate': None} if extension == 'pdf' else {'Date': None} if extension == 'svg' else None
        fig.savefig(path, dpi=200, metadata=metadata)
        paths.append(path)
    plt.close(fig)
    return paths


def cold_figure(rows):
    fig, axes = plt.subplots(2, 1, figsize=(10.6, 10.8), sharex=True)
    fig.subplots_adjust(left=.255, right=.965, bottom=.145, top=.815, hspace=.38)
    fig.text(.065, .963, 'Cold-condition cache responses', fontsize=21, weight='semibold', va='top')
    fig.text(.065, .923, 'Ryzen 7 9800X3D / Windows x64  |  Three processes per study, one boot', color=MUTED, fontsize=10.5, va='top')
    handles = [Line2D([0], [0], marker='o', linestyle='', color=COLORS[b], markeredgecolor='white', markersize=7, label=label)
               for b, label in [('p0', 'p0: queried bank1'), ('p1', 'p1: queried bank0')]]
    handles += [Line2D([0], [0], marker=MARKERS[n], linestyle='', color=MUTED, markeredgecolor='white', markersize=6.5, label=f'Process {n}') for n in (1, 2, 3)]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(.057, .888), ncol=5, frameon=False, columnspacing=1.3, handletextpad=.4, fontsize=9.5)
    specs = [
        ('dependency', ['plain', 'sham_mask', 'true_mask', 'lfence', 'cpuid'],
         ['Plain encoder', 'Matched register sham', 'Condition-dependent\nmask', 'LFENCE', 'CPUID'], 'A   K7: matched dependency controls'),
        ('receiver', ['plain', 'ablate_zero', 'ablate_one', 'ablate_both', 'sink_both'],
         ['Plain encoder', 'Remove bank0 load', 'Remove bank1 load', 'Remove both loads', 'Private-bank bindings'], 'B   K8: encoder interventions')]
    for ax, (study, modes, labels, title) in zip(axes, specs):
        for pos in range(5):
            if pos % 2 == 0:
                ax.axhspan(pos - .45, pos + .45, color='#F4F7FB', linewidth=0, zorder=0)
        ax.axvline(0, color='#8798AD', linewidth=.9, zorder=1)
        for row in rows:
            if row['study'] != study:
                continue
            bank, process = row['bank'], int(row['repetition'])
            y = modes.index(row['mode']) + (-.21 if bank == 'p0' else .21) + (process - 2) * .09
            point, lower, upper = [float(row[k]) for k in ('adjusted_pp', 'lower95_pp', 'upper95_pp')]
            if not -5 <= lower <= point <= upper <= 105:
                raise ValueError('Figure axis would clip a frozen interval')
            ax.errorbar(point, y, xerr=[[point - lower], [upper - point]], fmt=MARKERS[process], color=COLORS[bank], markersize=6,
                        markeredgecolor='white', markeredgewidth=.7, elinewidth=1.1, capsize=2.4, capthick=1, zorder=4)
        ax.set_yticks(range(5), labels); ax.set_ylim(4.55, -.55); ax.set_xlim(-5, 105)
        ax.set_xticks([0, 25, 50, 75, 100]); ax.grid(axis='x', color=GRID, linewidth=.7, zorder=0)
        ax.tick_params(axis='y', length=0, pad=12); ax.tick_params(axis='x', length=3, pad=6)
        ax.set_title(title, loc='left', fontsize=13, color=INK, pad=17, weight='semibold')
        sns.despine(ax=ax, left=True)
    axes[-1].set_xlabel('Adjusted training contrast (percentage points)', labelpad=11)
    axes[0].tick_params(labelbottom=True)
    fig.text(.065, .054, 'Points: individual processes. Whiskers: supporting 95% within-run cluster-bootstrap intervals; no pooled estimate.', fontsize=8.7, color=MUTED)
    fig.text(.065, .031, 'Primary intervals are separate: 99.1667% per endpoint; six contrasts per scheduled repetition pair.', fontsize=8.7, color=MUTED)
    return export(fig, 'windows-causal-responses')


def warm_figure(rows):
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    fig.subplots_adjust(left=.11, right=.965, bottom=.19, top=.72)
    fig.text(.075, .952, 'The sham differs under warm conditions', fontsize=19, weight='semibold', va='top')
    fig.text(.075, .893, 'Exploratory p0 cell  |  1,024 observations per mode in each process', fontsize=10.5, color=MUTED, va='top')
    for mode, color, offset, label in [('plain', BLUE, -.18, 'Plain encoder'), ('sham_mask', ORANGE, .18, 'Matched register sham')]:
        selected = sorted((r for r in rows if r['mode'] == mode), key=lambda r: r['repetition'])
        for index, row in enumerate(selected):
            x, rate = row['repetition'] + offset, row['rate_percent']
            ax.bar(x, rate, width=.31, color=color, edgecolor='white', linewidth=.8, label=label if index == 0 else None, zorder=3)
            ax.text(x, rate + 1, f"{row['hits']:,} / {row['n']:,}", ha='center', va='bottom', fontsize=10, color=INK)
    ax.set_xticks([1, 2, 3], ['Process 1', 'Process 2', 'Process 3']); ax.set_xlim(.45, 3.55)
    ax.set_ylim(0, 40); ax.set_yticks([0, 10, 20, 30, 40]); ax.set_ylabel('Public marker hit rate (%)', labelpad=10)
    ax.grid(axis='y', color=GRID, linewidth=.7); ax.tick_params(axis='x', length=0, pad=10); ax.set_axisbelow(True)
    ax.legend(loc='lower left', bbox_to_anchor=(-.02, 1.01), frameon=False, ncol=2, fontsize=10, handlelength=1.2, columnspacing=2)
    sns.despine(ax=ax, left=True)
    fig.text(.075, .079, 'Observed counts only; no confidence interval or new confirmatory test.', fontsize=9, color=MUTED)
    fig.text(.075, .042, 'Cold-condition sham equivalence does not extend to this warm-condition cell.', fontsize=9, color=MUTED)
    return export(fig, 'warm-sham-exploratory')


def main():
    hashes = {name: digest(ROOT / name) for name in INPUTS}
    supporting, warm = validate_inputs(); style()
    outputs = cold_figure(supporting) + warm_figure(warm)
    if hashes != {name: digest(ROOT / name) for name in INPUTS}:
        raise ValueError('Rendering changed an analysis input')
    versions = {name: importlib.metadata.version(name) for name in ('matplotlib', 'seaborn', 'numpy', 'pandas')}
    provenance = dict(purpose='Rendering only; frozen numerical inputs and uncertainty scopes unchanged',
        command='python results/k7-k8-windows-causal/make_figures.py',
        script_sha256=digest(Path(__file__)), python=platform.python_version(), packages=versions,
        theme='Light background; DejaVu Sans; royal blue, teal and orange; shapes supplement color',
        inputs_sha256=hashes, outputs_sha256={p.name: digest(p) for p in outputs},
        cold_figure=dict(points=60, intervals='Frozen supporting 95% within-run paired-cluster intervals', x_limits_pp=[-5, 105], pooled_estimate=False,
                         primary_intervals='Separate six-contrast Bonferroni family: 99.1667% per endpoint, 95% per scheduled pair'),
        warm_figure=dict(bars=6, observations_per_bar=1024, y_limits_percent=[0, 40], intervals=None, scope='Exploratory descriptive counts'), new_measurements=0)
    (ROOT / 'FIGURE-PROVENANCE.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(outputs=[p.name for p in outputs], packages=versions, analysis_inputs_unchanged=True, new_measurements=0)))


if __name__ == '__main__':
    main()
