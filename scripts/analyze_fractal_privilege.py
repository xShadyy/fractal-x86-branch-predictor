#!/usr/bin/env python3
"""Validate real CPL observations in K6, keeping emulation separate from evidence."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import analyze_dependency_receiver as k5
from analyze_cache_probe import fields, unsigned
from dependency_receiver_contract import CODE, BRANCH, code_for

PAIRS = ("uu", "kk", "uk", "ku")
CPL = {"uu": (3,3), "kk": (0,0), "uk": (3,0), "ku": (0,3)}
PIN = "03ad1c5b7c33621e7529ac6403eb9b1de4f8722f"


def physical_outcomes(cpu, run, samples):
    outcomes = {}
    for pair in PAIRS:
        subrun = dict(run, platform="fractal_physical")
        summary = k5.summarize(k5.Trace(cpu, subrun, {}, None, samples[pair]))
        outcomes[pair] = {key: summary[key] for key in (
            "apparatus_controls_pass", "gates", "thresholds", "heldout_hit_rates",
            "heldout_decoy_hit_rates", "outcomes", "numerical_signature_detected")}
    same = all(outcomes[p]["numerical_signature_detected"] for p in ("uu", "kk"))
    eligible = same and all(outcomes[p]["apparatus_controls_pass"] for p in ("uu", "kk", "uk"))
    return outcomes, bool(eligible), bool(eligible and outcomes["uk"]["numerical_signature_detected"])


def replay(blocks: int, episodes: int, warmup: int, seed: int):
    schedule=seed;tags=(seed^0xa5f1523d) or 1
    def shuffle(n):
        nonlocal schedule
        order=list(range(n))
        for i in range(n-1,0,-1):
            schedule=k5.next32(schedule);j=schedule%(i+1)
            order[i],order[j]=order[j],order[i]
        return order
    for count,keep in ((warmup,False),(blocks,True)):
        for block in range(count):
            for pair in shuffle(4):
                for mode in shuffle(3):
                    for round_number in range(episodes):
                        for position,kind in enumerate(shuffle(16)):
                            p=kind//8
                            tags=k5.next32(tags);tag0=1+tags%63
                            tags=k5.next32(tags);tag1=1+tags%63
                            wanted=tag0 if p else tag1
                            tags=k5.next32(tags);decoy=1+tags%62
                            if decoy>=wanted:decoy+=1
                            tags=k5.next32(tags);order=tags&1
                            if keep:yield(block,PAIRS[pair],k5.MODES[mode],round_number,position,k5.KINDS[kind],tag0,tag1,decoy,order)


def analyze(content: str, *, development: bool = False) -> dict:
    cpu=run=end=None;images={};samples={p:[] for p in PAIRS}
    expected=None;count=0;checksum=0;event_hash=k5.FNV_OFFSET;complete=False
    observed=Counter()
    for original in content.splitlines():
        row=original.strip()
        # Fractal emits boot and shutdown diagnostics around the experiment.
        if row.startswith("K6_ERROR:"):
            raise ValueError(row)
        if row.startswith("K6_CPU,"):
            if cpu is not None or run is not None:raise ValueError("duplicate or late CPU record")
            cpu=fields(row,"K6_CPU")
            if cpu.get("vendor")!="AuthenticAMD" or cpu.get("rdtscp")!="1" or cpu.get("clflush_bytes")!="64":
                raise ValueError("unsupported CPU timing contract")
        elif row.startswith("K6_RUN,"):
            if cpu is None or run is not None:raise ValueError("missing CPU or duplicate run")
            run=fields(row,"K6_RUN")
            fixed={"version":"1","protocol":"fractal_privilege_k6_v1","domains":"4","modes":"3","conditions":"16","controller_cpl":"3","upstream":PIN,"branch_offset":str(BRANCH),"code_bytes":str(len(CODE))}
            if any(run.get(k)!=v for k,v in fixed.items()):raise ValueError("run disagrees with K6 contract")
            physical=run.get("scope")=="physical_pilot"
            if physical:
                dims=(256,8,16,128,256)
                if cpu.get("hypervisor")!="0" or cpu.get("invariant_tsc")!="1" or int(cpu["signature"],16)!=0x00b40f40:
                    raise ValueError("physical collection platform requirements failed")
            elif run.get("scope")=="development_only" and development:dims=(2,1,1,8,8)
            else:raise ValueError("development trace requires --development; cannot become physical evidence")
            actual=tuple(unsigned(run[k],k) for k in ("blocks","episodes","warmup","prelude","train"))
            if actual!=dims:raise ValueError("collection dimensions changed")
            seed=unsigned(run["seed"],"seed")
            if not 0<seed<=k5.MASK32:raise ValueError("invalid seed")
            if physical and seed!=2180673261:raise ValueError("physical pilot seed changed from prospective plan")
            regions=[]
            for name in ("code","condition","token0","token1","bank0","bank1"):
                text=run[name+"_addr"]
                if not re.fullmatch(r"0x[0-9a-f]+",text):raise ValueError("invalid data/code address")
                address=int(text,16);size=4096*(64 if name.startswith("bank") else 1)
                if not address or address%4096 or address+size>k5.MASK64:raise ValueError("unaligned or invalid data/code region")
                regions.append((address,address+size))
            regions.sort()
            if any(a[1]>b[0] for a,b in zip(regions,regions[1:])):raise ValueError("overlapping data/code regions")
            expected=iter(replay(dims[0],dims[1],dims[2],seed))
        elif row.startswith("K6_CODE,"):
            if run is None or count or end is not None:raise ValueError("late code snapshot")
            record=fields(row,"K6_CODE");mode=record["mode"]
            if mode in images or bytes.fromhex(record["hex"])!=code_for(mode):raise ValueError("runtime code mismatch")
            images[mode]=record["hex"]
        elif row.startswith("K6_SAMPLE,"):
            if expected is None or set(images)!=set(k5.MODES) or end is not None:raise ValueError("sample outside code-audited run")
            c=row.split(",")
            if len(c)!=22 or unsigned(c[1],"index")!=count:raise ValueError("malformed sample index or columns")
            try:plan=next(expected)
            except StopIteration:raise ValueError("extra sample") from None
            actual=(unsigned(c[2],"block"),c[3],c[4],unsigned(c[5],"round"),unsigned(c[6],"position"),c[7],*(unsigned(v,"token or order") for v in c[8:12]))
            if actual!=plan:raise ValueError("schedule or token replay mismatch")
            block,pair,mode,round_number,position,kind,tag0,tag1,decoy,order=plan
            ticks,decoy_ticks,a,b,probe,train_cpl,recv_cpl,probe_cpl=(unsigned(v,"measurement") for v in c[12:20])
            kind_index=k5.KINDS.index(kind);p,member=divmod(kind_index,8)
            t=member&1 if member<4 else (1-p if member==7 else p)
            expected_probe=1+p if member in (0,1,7) else (2-p if member==6 else 0)
            if a!=int(run["prelude"])*3//2 or b!=int(run["train"])*(1+t) or probe!=expected_probe:
                raise ValueError("architectural return mismatch")
            expected_pc=int(run["code_addr"],16)+BRANCH;probed=member in (0,1,6,7)
            if (train_cpl,recv_cpl)!=(CPL[pair][0],CPL[pair][1]) or probe_cpl!=(CPL[pair][1] if probed else 255):
                raise ValueError("actual measured privilege does not match domain pair")
            if int(c[20],16)!=expected_pc or int(c[21],16)!=(expected_pc if probed else 0):
                raise ValueError("measured instruction address changed across privileges")
            if not ticks or not decoy_ticks:raise ValueError("zero timer delta")
            samples[pair].append(k5.Sample(block,mode,kind,round_number,order,ticks,decoy_ticks))
            observed[f"{train_cpl}->{recv_cpl}"]+=1
            count+=1;checksum=k5.mix(k5.mix(k5.mix(checksum,count),ticks),decoy_ticks)
            event_hash=k5.mix(event_hash,PAIRS.index(pair)*65536+k5.MODES.index(mode)*4096+kind_index*16+round_number)
            event_hash=k5.mix(event_hash,tag0*65536+tag1*256+decoy*2+order)
        elif row.startswith("K6_END,"):
            if run is None or end is not None:raise ValueError("unexpected end record")
            end=fields(row,"K6_END")
            target=int(run["blocks"])*int(run["episodes"])*4*3*16
            if count!=target or unsigned(end["count"],"count")!=count or unsigned(end["checksum"],"checksum")!=checksum or unsigned(end["event_hash"],"hash")!=event_hash or end.get("architecture_errors")!="0":
                raise ValueError("incomplete trace or checksum/architecture error")
        elif row=="FRACTAL_K6_OK: privilege transitions and complete trace collected":
            if end is None or complete:raise ValueError("unexpected completion marker")
            complete=True
        elif row.startswith("K6_"):raise ValueError("unknown experiment record")
    if cpu is None or run is None or end is None or not complete:raise ValueError("missing complete K6 experiment")
    result={"study":"fractal_privilege_k6_v1","cpu":cpu,"run":run,"samples":count,
            "actual_cpl_counts":dict(observed),"same_measured_instruction_address_verified":True,
            "all_runtime_code_snapshots_verified":True,"upstream_revision":PIN,
            "observed_cr4":end["observed_cr4"],"physical_mechanism_proven":False}
    if run["scope"]=="development_only":
        result.update(scope="functional_validation_only",hardware_eligible=False,
                      numerical_outcomes=None,user_to_kernel_numerical_signature_detected=False,
                      interpretation="CPL0/CPL3 transitions and trace logic verified in emulation; no physical branch-predictor inference")
    else:
        outcomes,eligible,signature=physical_outcomes(cpu,run,samples)
        result.update(scope="physical_engineering_pilot",hardware_eligible=eligible,numerical_outcomes=outcomes,
                      user_to_kernel_numerical_signature_detected=signature,
                      interpretation="Same-domain controls gate the user-to-kernel outcome; one physical pilot still requires linked review and independent sessions")
    return result


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("trace",type=Path);p.add_argument("--development",action="store_true");p.add_argument("--json",action="store_true");p.add_argument("--strict",action="store_true")
    a=p.parse_args()
    try:r=analyze(a.trace.read_text(encoding="utf-8-sig"),development=a.development)
    except (OSError,ValueError,KeyError,TypeError) as e:p.exit(2,f"Invalid K6 evidence: {e}\n")
    if a.json:print(json.dumps(r,sort_keys=True))
    else:
        print(f"K6 complete: {r['samples']} samples; scope={r['scope']}")
        print(f"Actual CPL pairs: {r['actual_cpl_counts']}")
        print(f"Same measured instruction address verified: {r['same_measured_instruction_address_verified']}")
        print(f"User-to-kernel hardware signature: {r['user_to_kernel_numerical_signature_detected']}")
        print(r["interpretation"])
    return 1 if a.strict and r["run"]["scope"]=="physical_pilot" and not r["hardware_eligible"] else 0


if __name__=="__main__":raise SystemExit(main())
