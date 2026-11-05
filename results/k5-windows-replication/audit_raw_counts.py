"""Independent cell-count and PE-byte checks. Reads evidence; runs no executable."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
from statistics import median
import struct
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def members(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        out={}
        for entry in z.infolist():
            if entry.is_dir():continue
            name=entry.filename.replace('\\','/')
            if name in out:raise ValueError('Duplicate evidence member')
            out[name]=z.read(entry)
        return out


def choose_threshold(hot,cold):
    # Balanced calibration classes let the objective be evaluated in integer
    # counts, rather than calling the original floating-point rank function.
    assert len(hot)==len(cold)>0
    h,c=sorted(hot),sorted(cold)
    unique=sorted(set(h+c))
    cuts=[unique[0]-1]+[(a+b)//2 for a,b in zip(unique,unique[1:])]+[unique[-1]]
    midpoint=(median(h)+median(c))/2
    return max(cuts,key=lambda cut:(bisect_right(h,cut)+len(c)-bisect_right(c,cut),-abs(cut-midpoint)))


def pe_sections(image):
    offset=struct.unpack_from('<I',image,0x3c)[0]
    assert image[offset:offset+4]==b'PE\0\0'
    count=struct.unpack_from('<H',image,offset+6)[0]
    optional_size=struct.unpack_from('<H',image,offset+20)[0]
    optional=offset+24
    assert struct.unpack_from('<H',image,optional)[0]==0x20b
    image_base=struct.unpack_from('<Q',image,optional+24)[0]
    table=optional+optional_size
    sections=[]
    for i in range(count):
        start=table+i*40
        name=image[start:start+8].split(b'\0')[0].decode('ascii')
        virtual_size,rva,raw_size,raw_offset=struct.unpack_from('<IIII',image,start+8)
        sections.append(dict(name=name,va=image_base+rva,virtual_size=virtual_size,
                             data=image[raw_offset:raw_offset+raw_size]))
    return sections


def verify_dumpbin(image,disassembly):
    sections=pe_sections(image)
    rows=[]
    for line in disassembly.splitlines():
        first=re.match(r'^\s+([0-9A-Fa-f]{16}): ((?:[0-9A-Fa-f]{2}(?: |$))+)',line)
        if first:
            rows.append([int(first[1],16),bytearray.fromhex(first[2])])
        elif rows and re.fullmatch(r'\s{20}(?:[0-9A-Fa-f]{2} ?)+\s*',line):
            rows[-1][1].extend(bytes.fromhex(line.strip()))
    assert rows,'No disassembly bytes found'
    count=0;covered=set()
    for address,data in rows:
        section=next(s for s in sections if s['va']<=address< s['va']+len(s['data']))
        offset=address-section['va']
        assert section['data'][offset:offset+len(data)]==data,hex(address)
        count+=len(data)
        covered.update(range(address,address+len(data)))
    text=next(s for s in sections if s['name']=='.text')
    assert covered==set(range(text['va'],text['va']+len(text['data'])))
    return dict(instruction_rows=len(rows),bytes_verified=count,
                all_text_section_bytes_covered=True,text_sha256=sha(text['data'])),text['data']


def audit_session(name,data,pilot_text=None):
    files=members(data)
    manifest=json.loads(next(v for n,v in files.items() if n.endswith('.manifest.json')).decode('utf-8-sig'))
    for n,digest in manifest['files_sha256'].items():assert sha(files[n])==digest
    saved=json.loads(next(v for n,v in files.items() if n.endswith('.analysis.json')).decode('utf-8-sig'))
    trace=next(v for n,v in files.items() if n.endswith('.log') and not n.endswith(('.build.log','.strict.log'))).decode('utf-8-sig')
    lines=trace.splitlines()
    hot,cold=defaultdict(list),defaultdict(list)
    totals=Counter();wanted=Counter();decoys=Counter();schedule=Counter();privilege=Counter();pcs=set()
    threshold=None;records=0
    for line in lines:
        if not line.startswith('K5_SAMPLE,'):continue
        row=line.split(',');assert len(row)==20
        index,block=int(row[1]),int(row[2]);mode,kind=row[3],row[5];bank=int(kind[-1])
        assert index==records;records+=1
        ticks,decoy=int(row[11]),int(row[12])
        schedule[block,mode,kind]+=1
        privilege['training_cpl_'+row[16]]+=1;privilege['probe_cpl_'+row[17]]+=1
        pcs.add(row[18])
        if row[17]=='3':assert row[18]==row[19]
        if block<256:
            if kind.startswith('hot_'):hot[bank].append(ticks)
            if kind.startswith('cold_'):cold[bank].append(ticks)
        else:
            if threshold is None:threshold={b:choose_threshold(hot[b],cold[b]) for b in (0,1)}
            totals[mode,kind]+=1
            wanted[mode,kind]+=ticks<=threshold[bank]
            decoys[mode,kind]+=decoy<=threshold[bank]
    assert records==393216
    assert len(schedule)==512*3*16 and set(schedule.values())=={16}
    assert len(pcs)==1 and privilege=={'training_cpl_3':393216,'probe_cpl_3':196608,'probe_cpl_255':196608}
    assert {'p'+str(b):v for b,v in threshold.items()}==saved['thresholds']
    rates={};decoy_rates={}
    for (mode,kind),total in totals.items():
        assert total==4096
        rates[mode,kind]=wanted[mode,kind]/total
        decoy_rates[mode,kind]=decoys[mode,kind]/total
        assert rates[mode,kind]==saved['heldout_hit_rates'][mode][kind]
        assert decoy_rates[mode,kind]==saved['heldout_decoy_hit_rates'][mode][kind]
    gates={}
    for (mode,kind),rate in rates.items():
        if kind.startswith(('hot_','arch_load_')):gates[mode+'/'+kind]=rate>=.95
        if kind.startswith(('cold_','no_probe_')):gates[mode+'/'+kind]=rate<=.05
        if kind.startswith('candidate_'):
            training=int(kind.split('_')[1][1]);bank=int(kind[-1])
            if training==bank or mode!='plain':gates[mode+'/'+kind]=rate<=.05
        gates[mode+'/'+kind+'/decoy']=decoy_rates[mode,kind]<=.05
    assert len(gates)==88 and gates==saved['gates']
    effects={}
    for bank in (0,1):
        adjusted={}
        for mode in ['plain','mask','cpuid']:
            candidate=rates[mode,f'candidate_t{1-bank}_p{bank}']-rates[mode,f'candidate_t{bank}_p{bank}']
            baseline=rates[mode,f'no_probe_t{1-bank}_p{bank}']-rates[mode,f'no_probe_t{bank}_p{bank}']
            adjusted[mode+'_adjusted']=candidate-baseline
        adjusted['interaction']=adjusted['plain_adjusted']-adjusted['mask_adjusted']
        for field,value in adjusted.items():assert value==saved['outcomes']['p'+str(bank)][field]['hit_rate_difference']
        effects['p'+str(bank)]={k:v*100 for k,v in adjusted.items()}
    image=next(v for n,v in files.items() if n.endswith('.exe'))
    disasm=next(v for n,v in files.items() if n.endswith('.disasm.txt')).decode('utf-8-sig')
    pe,text=verify_dumpbin(image,disasm)
    if pilot_text is not None:pe['text_identical_to_previously_reviewed_pilot']=text==pilot_text
    return dict(session=name,records=records,heldout_records=sum(totals.values()),
                cell_hit_and_decoy_rates_reproduced=96,gates_reproduced=88,
                gates_passed=sum(gates.values()),point_estimates_reproduced=8,
                thresholds=threshold,primary_and_secondary_pp=effects,
                per_cell_counts={mode+'/'+kind:dict(count=n,hits=wanted[mode,kind],decoy_hits=decoys[mode,kind]) for (mode,kind),n in sorted(totals.items())},
                cpl_counts=dict(privilege),one_branch_pc_within_run=True,
                linked_disassembly_consistency=pe,
                confidence_intervals='Checked separately by exact frozen-analysis replay; no pooled interval')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--pilot-exe',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    files=members(args.archive.read_bytes())
    pilot_text=None
    if args.pilot_exe:pilot_text=next(s['data'] for s in pe_sections(args.pilot_exe.read_bytes()) if s['name']=='.text')
    sessions=[]
    for name,data in sorted(files.items()):
        if re.fullmatch(r'session-0[123]/artifacts/dependency-receiver-windows-[0-9TZ]+\.zip',name):
            sessions.append(audit_session(name,data,pilot_text))
    assert len(sessions)==3
    report=dict(input_sha256=sha(args.archive.read_bytes()),all_checks_passed=True,
                scope='Independent raw cell counts and PE/dumpbin bytes; no executable rerun and no new measurements',sessions=sessions)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sessions'},indent=2))
    for s in sessions:print(json.dumps({k:v for k,v in s.items() if k not in ['per_cell_counts','primary_and_secondary_pp']},indent=2))


if __name__=='__main__':main()
