"""Reanalyze the authors' pinned Fractal M1 traces without executing their code.

This is an analysis reproduction, not a new hardware experiment. Optional plots
require matplotlib. Summary statistics otherwise use only the standard library.
"""
from __future__ import annotations
import argparse
import ast
from bisect import bisect_left, bisect_right
import csv
import hashlib
import json
from pathlib import Path
import re
from statistics import mean, median
import sys
import urllib.request
import zipfile

VERSION_DOI='10.5281/zenodo.19557478'
SOURCE_URL='https://zenodo.org/api/records/19557478/files/fractal.zip/content'
SOURCE_SHA256='8ee05fcccc9c80769c812bdd9f698226b48155aee2dbb6f491798da668182ac2'
ARCHIVE_PREFIX='fractal-artifact-evaluation-sp26-e2cbabefe17a736be5b162f1e363eab618fc9796/'


def digest(data):return hashlib.sha256(data).hexdigest()


def describe(taken,not_taken):
    ordered=sorted(not_taken)
    twice_superior=sum(2*(len(ordered)-bisect_right(ordered,t))+bisect_right(ordered,t)-bisect_left(ordered,t) for t in taken)
    return dict(taken_count=len(taken),not_taken_count=len(not_taken),
        taken_median_cycles=median(taken),not_taken_median_cycles=median(not_taken),
        taken_mean_cycles=mean(taken),not_taken_mean_cycles=mean(not_taken),
        median_not_taken_minus_taken_cycles=median(not_taken)-median(taken),
        taken_faster_pair_probability_ties_half=twice_superior/(2*len(taken)*len(not_taken)))


def read_trace(data,filename):
    match=re.fullmatch(r'([ci])_([pe])_(uu|uk)_([fe])(_asid)?(_phantom)?\.txt',filename)
    if not match:raise ValueError('Unexpected trace filename: '+filename)
    branch,core,domains,sensor,asid,phantom=match.groups()
    if asid and domains!='uu':raise ValueError('Unexpected ASID/domain combination')
    content=data.decode('utf-8')
    if content.count('#### EXPERIMENT START\n')!=1 or content.count('#### EXPERIMENT STOP')!=1:
        raise ValueError('Missing or duplicate experiment markers: '+filename)
    body=content.split('#### EXPERIMENT START\n',1)[1].split('#### EXPERIMENT STOP',1)[0]
    literal=re.fullmatch(r'\s*data\s*=\s*(\[.*\])\s*',body,re.DOTALL)
    if literal is None:raise ValueError('Malformed trace body: '+filename)
    rows=ast.literal_eval(literal.group(1))
    if not isinstance(rows,list) or len(rows)!=5004:raise ValueError('Expected 5004 published rows: '+filename)
    if any(not isinstance(r,tuple) or len(r)!=2 or r[0] not in ('T','N') or type(r[1]) is not int or r[1]<=0 for r in rows):
        raise ValueError('Malformed latency row: '+filename)
    if [r[0] for r in rows[:4]]!=['N','T','N','T']:raise ValueError('Changed initial label sequence: '+filename)
    expected=[('ATTACK: '+('CONDITIONAL' if branch=='c' else 'INDIRECT')),
              ('PHANTOM MODE: '+('YES' if phantom else 'NO')),
              ('MEASURING '+('INST (FETCH)' if sensor=='f' else 'DATA (EXEC)')),
              ('RECV MODE: '+('KERN' if domains=='uk' else 'USER')),
              ('['+('pcore' if core=='p' else 'ecore')+']'),
              ('ASIDs V2: '+('ENABLED' if asid else 'DISABLED'))]
    if any(v not in content for v in expected):raise ValueError('Filename/header mismatch: '+filename)
    all_t=[v for k,v in rows if k=='T'];all_n=[v for k,v in rows if k=='N']
    tail=rows[4:];tail_t=[v for k,v in tail if k=='T'];tail_n=[v for k,v in tail if k=='N']
    return dict(filename=filename,sha256=digest(data),branch_type='conditional' if branch=='c' else 'indirect',
        core_type='performance' if core=='p' else 'efficiency',domains=domains,measurement='fetch' if sensor=='f' else 'execute',
        different_asid=bool(asid),phantom=bool(phantom),recorded_rows=len(rows),
        all_rows=describe(all_t,all_n),after_initial_four=describe(tail_t,tail_n)),rows


def figures(records,raw,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.colors as colors
    from matplotlib import font_manager
    font_root=Path(__file__).resolve().parents[1]/'docs/assets/fonts'
    for name in ('Inter-Regular.ttf','Inter-SemiBold.ttf'):
        font_path=font_root/name
        if not font_path.is_file():raise FileNotFoundError('Bundled Inter font missing: '+str(font_path))
        font_manager.fontManager.addfont(font_path)
    for weight,name in (('normal','Inter-Regular.ttf'),(600,'Inter-SemiBold.ttf')):
        resolved=font_manager.findfont(font_manager.FontProperties(family='Inter',weight=weight),fallback_to_default=False)
        if Path(resolved).resolve()!=(font_root/name).resolve():raise ValueError('Plot font did not resolve to bundled Inter: '+resolved)
    conditions=[('uu',False,False),('uk',False,False),('uu',True,False),('uu',False,True),('uk',False,True),('uu',True,True)]
    lookup={(r['branch_type'],r['core_type'],r['domains'],r['different_asid'],r['phantom'],r['measurement']):r for r in records}
    matrix=[]
    rowkeys=[('conditional','performance'),('conditional','efficiency'),('indirect','performance'),('indirect','efficiency')]
    for branch,core in rowkeys:
        matrix.append([lookup[branch,core,domain,asid,phantom,sensor]['after_initial_four']['taken_faster_pair_probability_ties_half'] for domain,asid,phantom in conditions for sensor in ['fetch','execute']])
    with plt.rc_context({'font.family':'Inter','font.size':11,'axes.labelsize':11,
                         'axes.titlesize':13,'axes.titleweight':600,
                         'xtick.labelsize':10.5,'ytick.labelsize':10.5,
                         'text.color':'#263a63','axes.labelcolor':'#263a63',
                         'axes.edgecolor':'#d7dfea','xtick.color':'#53647b','ytick.color':'#53647b',
                         'pdf.fonttype':42,'svg.fonttype':'path',
                         'svg.hashsalt':'fractal-authors-m1-v1'}):
        fig,ax=plt.subplots(figsize=(16,5.5),layout='constrained')
        image=ax.imshow(matrix,cmap='coolwarm',norm=colors.Normalize(vmin=0,vmax=1),aspect='auto')
        for y,row in enumerate(matrix):
            for x,value in enumerate(row):ax.text(x,y,f'{value:.3f}',ha='center',va='center',fontsize=11.5,color='white' if value<.12 or value>.88 else '#18243b')
        labels=[]
        for domain,asid,phantom in conditions:
            group='Different ASID' if asid else ('User/kernel' if domain=='uk' else 'User/user')
            if phantom:group='Phantom\n'+group
            labels.extend([group+'\nFetch',group+'\nExecute'])
        ax.set_xticks(range(12),labels)
        ax.set_yticks(range(4),[b.title()+' / '+c for b,c in rowkeys],fontsize=11.5)
        ax.tick_params(length=0,pad=9)
        ax.set_title("Authors' M1 traces: training-label separation",fontsize=17,pad=17,loc='left')
        for spine in ax.spines.values():spine.set_visible(False)
        colorbar=fig.colorbar(image,ax=ax,orientation='horizontal',shrink=.65,pad=.08,fraction=.08,aspect=45)
        colorbar.set_label('P(T latency < N latency) + 0.5 × ties',labelpad=8)
        colorbar.outline.set_visible(False)
        for ext in ['png','pdf','svg']:
            metadata={'Software':'Fractal x86 author-data reanalysis'} if ext=='png' else (
                {'CreationDate':None,'ModDate':None,'Creator':'Fractal x86 author-data reanalysis'} if ext=='pdf' else
                {'Date':None,'Creator':'Fractal x86 author-data reanalysis'})
            fig.savefig(out/('authors-m1-descriptive-matrix.'+ext),dpi=180,metadata=metadata)
        plt.close(fig)
        fig,axes=plt.subplots(2,2,figsize=(13.5,7.5),layout='constrained')
        names=['i_p_uu_e.txt','i_p_uk_e.txt','i_p_uu_f.txt','i_p_uk_f.txt']
        titles=['User/user: execute','User/kernel: execute','User/user: fetch','User/kernel: fetch']
        for ax,name,title in zip(axes.flat,names,titles):
            samples=raw[name][4:164]
            for label,color in [('T','#3156f3'),('N','#d84848')]:
                x=[i for i,r in enumerate(samples) if r[0]==label];y=[r[1] for r in samples if r[0]==label]
                ax.scatter(x,y,s=18,c=color,label=label,alpha=.9,linewidths=0)
            ax.set(title=title,xlabel='Sample after initial four',ylabel='Recorded cycles')
            ax.grid(alpha=.3,color='#cbd5e3');ax.set_axisbelow(True)
            ax.spines['top'].set_visible(False);ax.spines['right'].set_visible(False)
            ax.legend(title='Training label',fontsize=10.5,title_fontsize=10.5,frameon=False)
        fig.suptitle("Authors' M1 indirect-branch reference traces",fontsize=17,fontweight=600)
        for ext in ['png','pdf','svg']:
            metadata={'Software':'Fractal x86 author-data reanalysis'} if ext=='png' else (
                {'CreationDate':None,'ModDate':None,'Creator':'Fractal x86 author-data reanalysis'} if ext=='pdf' else
                {'Date':None,'Creator':'Fractal x86 author-data reanalysis'})
            fig.savefig(out/('authors-m1-reference-traces.'+ext),dpi=180,metadata=metadata)
        plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--download',action='store_true');p.add_argument('--plots',action='store_true')
    args=p.parse_args()
    if not args.archive.exists():
        if not args.download:p.error('Archive missing; supply the pinned ZIP or use --download')
        data=urllib.request.urlopen(SOURCE_URL,timeout=60).read()
        if digest(data)!=SOURCE_SHA256:raise ValueError('Downloaded archive SHA256 mismatch')
        args.archive.parent.mkdir(parents=True,exist_ok=True);args.archive.write_bytes(data)
    payload=args.archive.read_bytes()
    if digest(payload)!=SOURCE_SHA256:raise ValueError('Archive SHA256 differs from the pinned published release')
    records=[];raw={}
    with zipfile.ZipFile(args.archive) as z:
        for item in sorted(z.infolist(),key=lambda i:i.filename):
            if item.filename.startswith(ARCHIVE_PREFIX+'precollected_data/') and item.filename.endswith('.txt'):
                name=Path(item.filename).name
                if name in raw:raise ValueError('Duplicate trace filename')
                record,rows=read_trace(z.read(item),name);records.append(record);raw[name]=rows
    if len(records)!=48:raise ValueError('Expected all 48 released traces')
    label_sequences={tuple(k for k,v in rows) for rows in raw.values()}
    report=dict(schema=1,scope='Reanalysis of authors precollected M1 data; no new hardware measurements',
        source_version_doi=VERSION_DOI,source_url=SOURCE_URL,source_sha256=SOURCE_SHA256,python=sys.version,
        traces=48,total_recorded_rows=sum(r['recorded_rows'] for r in records),all_label_sequences_identical=len(label_sequences)==1,
        descriptive_method='Medians and empirical pairwise rank probability; no null/positive threshold, no inferential confidence interval or new hardware-replication claim',
        initial_four_handling='Both all rows and rows 4 onward reported. Authors latency/table figures display rows[4:164]; their histogram uses all rows.',
        licensing='Record metadata advertises CC-BY-4.0; sibling metadata.toml points to GPL-3.0. Original code is not redistributed here; review source licensing before vendoring.',
        results=records)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'authors-data-summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    columns=['filename','branch_type','core_type','domains','measurement','different_asid','phantom',
             'recorded_rows','sha256']
    statistics_columns=list(records[0]['after_initial_four'])
    with (args.output/'authors-data-summary.csv').open('w',newline='',encoding='utf-8') as destination:
        writer=csv.DictWriter(destination,fieldnames=columns+statistics_columns)
        writer.writeheader()
        for record in records:
            writer.writerow({**{key:record[key] for key in columns},**record['after_initial_four']})
    if args.plots:figures(records,raw,args.output)
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))


if __name__=='__main__':main()
