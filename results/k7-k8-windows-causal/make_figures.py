"""Plot recorded supporting results; no new inference or CPU collection."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent
rows=list(csv.DictReader((ROOT/'supporting-mode-table.csv').open(newline='')))
colors={'p0':'#2166ac','p1':'#b35806'}
markers={1:'o',2:'s',3:'^'}
fig,axes=plt.subplots(1,2,figsize=(12.8,5.6),sharex=True)
specs=[('dependency',['plain','sham_mask','true_mask','lfence','cpuid'],
        ['Plain','Independent sham','Condition-dependent mask','LFENCE','CPUID']),
       ('receiver',['plain','ablate_zero','ablate_one','ablate_both','sink_both'],
        ['Plain','Remove bank0 load','Remove bank1 load','Remove both loads','Private-bank bindings'])]
for ax,(study,modes,labels) in zip(axes,specs):
    ax.axvspan(-10,10,color='#f0f0f0',zorder=0)
    ax.axvline(0,color='#999999',linewidth=.8,zorder=0)
    for row in rows:
        if row['study']!=study:continue
        bank=row['bank'];rep=int(row['repetition'])
        y=modes.index(row['mode'])+(-.14 if bank=='p0' else .14)+(rep-2)*.065
        point=float(row['adjusted_pp']);lower=float(row['lower95_pp']);upper=float(row['upper95_pp'])
        ax.errorbar(point,y,xerr=[[max(0,point-lower)],[max(0,upper-point)]],
                    fmt=markers[rep],color=colors[bank],markersize=4.5,linewidth=.8,capsize=2)
    ax.set_yticks(range(5),labels)
    ax.set_ylim(4.55,-.55);ax.set_xlim(-12,105)
    ax.set_xticks([0,25,50,75,100]);ax.grid(axis='x',alpha=.18)
    ax.set_xlabel('Adjusted marker-response contrast (percentage points)')
    ax.set_title('K7: matched dependency controls' if study=='dependency' else 'K8: encoder interventions',fontsize=12)
    ax.spines[['top','right']].set_visible(False)
handles=[Line2D([0],[0],marker='o',linestyle='',color=colors[b],label=label)
         for b,label in [('p0','p0, queried bank1'),('p1','p1, queried bank0')]]
handles += [Line2D([0],[0],marker=markers[r],linestyle='',color='#555555',label=f'Repetition {r}') for r in (1,2,3)]
fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.065),ncol=5,frameon=False,fontsize=9)
fig.suptitle('Windows/Ryzen K7/K8: cold-condition responses across three processes per study',fontsize=13)
fig.text(.5,.015,'Dots: individual processes. Gray: +/-10 pp reference. Whiskers: supporting 95% within-run cluster-bootstrap intervals; no pooled interval.',ha='center',fontsize=8.3)
fig.tight_layout(rect=[0,.16,1,.92])
for extension in ('png','pdf','svg'):fig.savefig(ROOT/f'windows-causal-responses.{extension}',dpi=180)
plt.close(fig)

fig,ax=plt.subplots(figsize=(8,4.8))
warm=[]
for number in (2,4,6):
    data=json.loads((ROOT/f'attempt-{number:02d}-replayed-analysis.json').read_text())
    rep=(number//2)
    for mode,color,offset,label in [('plain','#2166ac',-.17,'Plain'),('sham_mask','#b35806',.17,'Independent sham')]:
        rate=data['heldout_hit_rates'][mode]['warm_mismatch_p0']
        count=round(rate*1024)
        ax.bar(rep+offset,rate*100,width=.30,color=color,label=label if rep==1 else None)
        ax.text(rep+offset,rate*100+.6,f'{count}/1024',ha='center',fontsize=9)
        warm.append({'repetition':rep,'mode':mode,'hits':count,'n':1024,'rate_percent':rate*100})
ax.set_xticks([1,2,3],['Repetition 1','Repetition 2','Repetition 3'])
ax.set_ylim(0,36);ax.set_ylabel('Public marker hit rate (%)')
ax.set_title('Exploratory warm-condition p0 control: sham differs from plain',fontsize=12)
ax.legend(frameon=False);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
ax.set_axisbelow(True)
fig.text(.5,.015,'Descriptive counts, no confidence interval or new confirmatory test. Primary sham equivalence concerns the cold-condition endpoint.',ha='center',fontsize=8)
fig.tight_layout(rect=[0,.05,1,1])
for extension in ('png','pdf','svg'):fig.savefig(ROOT/f'warm-sham-exploratory.{extension}',dpi=180)
plt.close(fig)
(ROOT/'warm-sham-counts.json').write_text(json.dumps({'scope':'Exploratory descriptive counts only','rows':warm},indent=2)+'\n')
print('Generated two supporting figures in PNG/PDF/SVG; no new hardware collection.')
