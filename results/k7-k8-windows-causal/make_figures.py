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
from matplotlib import font_manager
from matplotlib.text import Text
import seaborn as sns

ROOT = Path(__file__).resolve().parent
BLUE, TEAL, ORANGE = '#2457C5', '#007F82', '#C26B19'
INK, MUTED, GRID = '#182A43', '#52647B', '#DDE5EF'
COLORS = {'p0': BLUE, 'p1': TEAL}
FONT_DIR = ROOT.parents[1] / 'docs/assets/fonts'
FONT_PATHS = [FONT_DIR / 'Inter-Regular.ttf', FONT_DIR / 'Inter-SemiBold.ttf']
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
    for path in FONT_PATHS:
        if not path.exists():
            raise ValueError(f'Missing bundled Inter font: {path}')
        font_manager.fontManager.addfont(path)
        if font_manager.FontProperties(fname=path).get_name() != 'Inter':
            raise ValueError('Bundled font is not Inter')
    sns.set_theme(context='notebook', style='ticks', palette=[BLUE, TEAL, ORANGE], rc={
        'font.family': 'Inter', 'font.sans-serif': ['Inter'], 'font.size': 11,
        'axes.labelsize': 11, 'axes.labelcolor': MUTED, 'axes.edgecolor': GRID,
        'axes.linewidth': .8, 'text.color': INK, 'xtick.color': MUTED,
        'ytick.color': INK, 'xtick.labelsize': 10.5, 'ytick.labelsize': 10.5,
        'figure.facecolor': 'white', 'axes.facecolor': 'white', 'savefig.facecolor': 'white',
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'path',
        'svg.hashsalt': 'fractal-k7-k8-inter-matrix-v3'})


def verify_fonts(fig):
    fig.canvas.draw()
    allowed = {p.resolve() for p in FONT_PATHS}
    for text in fig.findobj(match=Text):
        if text.get_visible() and text.get_text():
            resolved = Path(font_manager.findfont(text.get_fontproperties(), fallback_to_default=False)).resolve()
            if resolved not in allowed:
                raise ValueError(f'Font fallback in chart: {resolved}')


def export(fig, stem):
    verify_fonts(fig)
    paths = []
    for extension in ('png', 'pdf', 'svg'):
        path = ROOT / f'{stem}.{extension}'
        metadata = {'CreationDate': None, 'ModDate': None} if extension == 'pdf' else {'Date': None} if extension == 'svg' else None
        fig.savefig(path, dpi=200, metadata=metadata)
        paths.append(path)
    plt.close(fig)
    return paths


def cold_figure(rows):
    import numpy as np
    values = [float(row['adjusted_pp']) for row in rows]
    minimum, maximum = min(values), max(values)
    fig = plt.figure(figsize=(12.2, 4.8))
    grid = fig.add_gridspec(1, 3, width_ratios=[1, 1, .045], left=.155, right=.91,
                           bottom=.145, top=.69, wspace=.57)
    axes = [fig.add_subplot(grid[0, i]) for i in (0, 1)]
    color_axis = fig.add_subplot(grid[0, 2])
    fig.text(.04, .96, 'Cold-condition cache responses', fontsize=20, weight='semibold', va='top')
    color_map = sns.blend_palette(['#F2F6FD', '#89C7D0', BLUE], as_cmap=True)
    specs = [
        ('dependency', ['plain', 'sham_mask', 'true_mask', 'lfence', 'cpuid'],
         ['Plain encoder', 'Matched sham', 'Condition-dependent\nmask', 'LFENCE', 'CPUID'],
         'K7  Matched dependency controls'),
        ('receiver', ['plain', 'ablate_zero', 'ablate_one', 'ablate_both', 'sink_both'],
         ['Plain encoder', 'Bank0 load off', 'Bank1 load off', 'Both loads off', 'Private banks'],
         'K8  Encoder interventions')]
    for index, (axis, (study, modes, labels, title)) in enumerate(zip(axes, specs)):
        lookup = {(row['bank'], row['mode'], int(row['repetition'])): float(row['adjusted_pp'])
                  for row in rows if row['study'] == study}
        matrix = np.array([[lookup[bank, mode, process] for bank in ('p0', 'p1')
                            for process in (1, 2, 3)] for mode in modes])
        sns.heatmap(matrix, ax=axis, cmap=color_map, vmin=minimum, vmax=maximum,
                    annot=True, fmt='.2f', annot_kws={'fontsize': 10.5},
                    linewidths=.9, linecolor='white', cbar=index == 0,
                    cbar_ax=color_axis if index == 0 else None,
                    cbar_kws={'ticks': [minimum, 25, 50, 75, maximum]},
                    xticklabels=['1', '2', '3', '1', '2', '3'], yticklabels=labels)
        for annotation in axis.texts:
            annotation.set_color('white' if float(annotation.get_text()) > 65 else INK)
        axis.axvline(3, color='white', linewidth=3)
        axis.text(.25, 1.055, 'p0: bank1', transform=axis.transAxes, ha='center', fontsize=11)
        axis.text(.75, 1.055, 'p1: bank0', transform=axis.transAxes, ha='center', fontsize=11)
        axis.set_title(title, loc='left', fontsize=12.5, pad=47, weight='semibold')
        axis.set_xlabel('Process', labelpad=8)
        axis.tick_params(axis='both', length=0)
        axis.set_yticklabels(labels, rotation=0)
    color_axis.set_yticklabels([f'{minimum:.2f}', '25', '50', '75', f'{maximum:.2f}'])
    color_axis.set_ylabel('Adjusted contrast (pp)', fontsize=11, labelpad=12)
    color_axis.tick_params(length=0, pad=5)
    return export(fig, 'windows-causal-responses')


def warm_figure(rows):
    fig, ax = plt.subplots(figsize=(8.8, 4.7))
    fig.subplots_adjust(left=.11, right=.965, bottom=.14, top=.71)
    fig.text(.055, .96, 'Exploratory warm-condition p0 responses', fontsize=18, weight='semibold', va='top')
    for mode, color, offset, label in [('plain', BLUE, -.18, 'Plain encoder'), ('sham_mask', ORANGE, .18, 'Matched sham')]:
        selected = sorted((r for r in rows if r['mode'] == mode), key=lambda r: r['repetition'])
        for index, row in enumerate(selected):
            x, rate = row['repetition'] + offset, row['rate_percent']
            ax.bar(x, rate, width=.31, color=color, edgecolor='white', linewidth=.8,
                   label=label if index == 0 else None, zorder=3)
            ax.text(x, rate + 1, f"{row['hits']:,} / {row['n']:,}", ha='center', va='bottom', fontsize=10.5)
    ax.set_xticks([1, 2, 3], ['Process 1', 'Process 2', 'Process 3'])
    ax.set_xlim(.45, 3.55); ax.set_ylim(0, 40); ax.set_yticks([0, 10, 20, 30, 40])
    ax.set_ylabel('Public marker hit rate (%)', labelpad=10)
    ax.grid(axis='y', color=GRID, linewidth=.7); ax.tick_params(axis='x', length=0, pad=10)
    ax.set_axisbelow(True)
    ax.legend(loc='lower left', bbox_to_anchor=(-.02, 1.01), frameon=False, ncol=2,
              fontsize=10.5, handlelength=1.2, columnspacing=2)
    sns.despine(ax=ax, left=True)
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
        theme='Compact quantitative matrix and zero-baseline bars; verified bundled Inter fonts',
        inputs_sha256=hashes, outputs_sha256={p.name: digest(p) for p in outputs},
        fonts={p.relative_to(ROOT.parents[1]).as_posix(): dict(sha256=digest(p), family=font_manager.FontProperties(fname=p).get_name()) for p in FONT_PATHS},
        font_license=dict(path='docs/assets/fonts/Inter-LICENSE.txt', sha256=digest(FONT_DIR / 'Inter-LICENSE.txt'), name='SIL Open Font License 1.1'),
        font_source=dict(path='docs/assets/fonts/Inter-PROVENANCE.json', sha256=digest(FONT_DIR / 'Inter-PROVENANCE.json')),
        font_verification='Every visible Text object resolves to one of the two bundled Inter files; fallback raises an error',
        svg_text='Converted to glyph paths', pdf_fonts='Embedded TrueType subsets (fonttype 42)',
        cold_figure=dict(cells=60, cell_values='Frozen supporting point estimates rounded to 2 decimals for display', intervals='Not encoded; supporting 95% intervals in supporting-mode-table.csv and primary intervals in endpoint-table.csv', color_range_pp=[min(float(r['adjusted_pp']) for r in supporting), max(float(r['adjusted_pp']) for r in supporting)], pooled_estimate=False,
                         primary_intervals='Separate six-contrast Bonferroni family: 99.1667% per endpoint, 95% per scheduled pair'),
        warm_figure=dict(bars=6, observations_per_bar=1024, y_limits_percent=[0, 40], intervals=None, scope='Exploratory descriptive counts'), new_measurements=0)
    (ROOT / 'FIGURE-PROVENANCE.json').write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(outputs=[p.name for p in outputs], packages=versions, analysis_inputs_unchanged=True, new_measurements=0)))


if __name__ == '__main__':
    main()
