"""Prospective, finite Windows user-mode K7/K8 follow-up and evidence packaging."""
from __future__ import annotations
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid
import zipfile

POLICY = 'protocols/WINDOWS_CAUSAL_POLICY.json'
STUDY = 'windows_causal_followup_v1'

def utc():
    return datetime.now(timezone.utc).isoformat()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args], text=True).strip()

def source_state(repo):
    if git(repo,'status','--porcelain','--untracked-files=normal'):
        raise ValueError('Source tree is not clean. Commit or stash edits before collection.')
    policy = read(repo/POLICY)
    files = policy['source_files']
    if len(files)!=len(set(files)) or POLICY not in files:
        raise ValueError('Invalid source inventory.')
    hashes = {}
    for name in files:
        p = Path(name)
        if p.is_absolute() or '..' in p.parts:
            raise ValueError('Unsafe source inventory.')
        hashes[name] = digest((repo/name).read_bytes().replace(b'\r\n',b'\n'))
    return git(repo,'rev-parse','HEAD'), hashes

def runtime():
    image = Path(sys.executable)
    if sys.platform == 'win32':
        api = ctypes.WinDLL('kernel32',use_last_error=True).GetModuleFileNameW
        api.argtypes = [ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint32]
        api.restype = ctypes.c_uint32
        buf = ctypes.create_unicode_buffer(32768)
        n = api(None,buf,len(buf))
        if not n or n>=len(buf):
            raise OSError('Cannot resolve the loaded Python image.')
        image = Path(buf.value)
    return {'version':sys.version,'image_sha256':file_hash(image),'image_path':str(image)}

def host_identity(host):
    if host.get('schema')!=1 or not host.get('boot_utc') or not host.get('cpu') or not host.get('os'):
        raise ValueError('Incomplete Windows host inventory.')
    if not isinstance(host.get('hypervisor_present'),bool):
        raise ValueError('Hypervisor inventory must be an explicit Boolean.')
    # Captured time changes; boot and configuration must not change in this study.
    required = ('boot_utc','cpu','os','bios','baseboard','hypervisor_present',
                'vbs','microcode_update_revision_hex','microcode_query_status','power_plan')
    missing = [k for k in required if k not in host]
    if missing:
        raise ValueError('Missing host fields: '+','.join(missing))
    return {k:host[k] for k in required}

def build_hashes(folder):
    root = folder/'build'
    names = ('collector.exe','collector.disasm.txt','build.json','build.log','initial-host.json')
    return {n:file_hash(root/n) for n in names}

def create_plan(repo, folder):
    if (folder/'plan.json').exists():
        return load_plan(repo,folder)
    if any(folder.glob('attempt-*')):
        raise ValueError('Attempt evidence exists without a plan. Preserve this folder.')
    revision,sources = source_state(repo)
    policy = read(repo/POLICY)
    build = read(folder/'build/build.json')
    if build.get('schema')!=1 or build.get('study')!='windows_causal_followup' or build.get('build_runtime_status')!='built':
        raise ValueError('The measurement build did not finish successfully.')
    if build.get('git_head')!=revision or not build.get('git_clean'):
        raise ValueError('Build does not match the clean source revision.')
    if build.get('source_sha256_lf')!=sources:
        raise ValueError('Compiled source inventory differs from the prospective plan.')
    if build.get('binary_sha256')!=file_hash(folder/'build/collector.exe'):
        raise ValueError('Built binary hash mismatch.')
    tools=build.get('tools',{})
    if set(tools)!={'cl.exe','link.exe','dumpbin.exe'} or any(not t.get('sha256') or not t.get('file_version') for t in tools.values()):
        raise ValueError('Missing compiler/linker/disassembler provenance.')
    host=read(folder/'build/initial-host.json')
    attempts=[]
    used=set()
    for repetition in range(1,4):
        pair=['dependency','receiver']
        secrets.SystemRandom().shuffle(pair)
        for name in pair:
            seed=0
            while not seed or seed in used:
                seed=secrets.randbits(32)
            used.add(seed)
            attempts.append({'number':len(attempts)+1,'study':name,'repetition':repetition,'seed':seed})
    plan={'schema':1,'study':STUDY,'plan_id':str(uuid.uuid4()),'created_utc':utc(),
          'source_revision':revision,'source_sha256_lf':sources,'policy':policy,
          'build_sha256':build_hashes(folder),'runtime':runtime(),
          'host_identity':host_identity(host),'attempts':attempts,
          'scope':'Three fresh processes per study on one unchanged Windows boot/configuration. No mechanism proof.'}
    with zipfile.ZipFile(folder/'sources.zip','x',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(sources):
            z.writestr(name,(repo/name).read_bytes())
    plan['source_archive_sha256']=file_hash(folder/'sources.zip')
    write(folder/'plan.json',plan,exclusive=True)
    (folder/'plan.sha256').write_text(file_hash(folder/'plan.json')+'\n',encoding='ascii')
    (folder/'attempt-ledger.jsonl').open('x',encoding='utf-8').close()
    # Preserve a distinct plan-only snapshot before launching a collector.
    snapshot=archive_tree(repo,folder,'causal-plan')
    print('PLAN FROZEN BEFORE COLLECTION: '+str(snapshot),flush=True)
    return load_plan(repo,folder)

def load_plan(repo,folder):
    plan=read(folder/'plan.json')
    if file_hash(folder/'plan.json')!=(folder/'plan.sha256').read_text().strip():
        raise ValueError('Frozen plan hash mismatch.')
    if plan.get('schema')!=1 or plan.get('study')!=STUDY or len(plan.get('attempts',[]))!=6:
        raise ValueError('Unsupported prospective plan.')
    revision,sources=source_state(repo)
    if revision!=plan['source_revision'] or sources!=plan['source_sha256_lf'] or read(repo/POLICY)!=plan['policy']:
        raise ValueError('Live source revision or policy differs from the frozen plan.')
    if build_hashes(folder)!=plan['build_sha256'] or file_hash(folder/'sources.zip')!=plan['source_archive_sha256']:
        raise ValueError('Build or source archive changed after plan creation.')
    with zipfile.ZipFile(folder/'sources.zip') as z:
        if set(z.namelist())!=set(sources) or len(z.namelist())!=len(sources):
            raise ValueError('Source archive inventory mismatch.')
        for name,h in sources.items():
            if digest(z.read(name).replace(b'\r\n',b'\n'))!=h:
                raise ValueError('Frozen source archive mismatch: '+name)
    current=runtime()
    if any(current[k]!=plan['runtime'][k] for k in ('version','image_sha256')):
        raise ValueError('Loaded Python runtime differs from the frozen plan.')
    expected=[(a['number'],a['study'],a['repetition'],a['seed']) for a in plan['attempts']]
    if [a[0] for a in expected]!=list(range(1,7)) or len({a[3] for a in expected})!=6:
        raise ValueError('Invalid fixed attempt sequence.')
    for repetition in range(1,4):
        pair=plan['attempts'][(repetition-1)*2:repetition*2]
        if {a['study'] for a in pair}!={'dependency','receiver'} or any(a['repetition']!=repetition or not 0<a['seed']<2**32 for a in pair):
            raise ValueError('Invalid pair or seed.')
    validate_ledger(folder,plan)
    return plan

def validate_ledger(folder,plan):
    """Detect deleted/replaced attempt folders before a repeat invocation."""
    previous=file_hash(folder/'plan.json')
    records=[]
    for index,line in enumerate((folder/'attempt-ledger.jsonl').read_bytes().splitlines(keepends=True)):
        if not line.endswith(b'\n') or index>=12:
            raise ValueError('Partial or overlong attempt ledger.')
        entry=json.loads(line)
        number=index//2+1
        state='started' if index%2==0 else 'finished'
        expected=plan['attempts'][number-1]
        if entry.get('schema')!=1 or entry.get('previous_sha256')!=previous or entry.get('attempt')!=expected or entry.get('state')!=state:
            raise ValueError('Attempt ledger sequence mismatch.')
        target=folder/f'attempt-{number:02d}'/(state+'.json')
        if not target.exists() or file_hash(target)!=entry.get('record_sha256'):
            raise ValueError('Ledger-bound attempt evidence is missing or changed.')
        previous=digest(line)
        records.append(entry)
    started={f'attempt-{entry["attempt"]["number"]:02d}' for entry in records if entry['state']=='started'}
    actual={p.name for p in folder.glob('attempt-*') if p.is_dir()}
    if started!=actual:
        raise ValueError('Attempt directories disagree with the persistent ledger.')
    return records

def append_ledger(folder,plan,attempt,state):
    # The caller validates the previous ledger before creating a new directory.
    if state=='finished':
        validate_ledger(folder,plan)
    lines=(folder/'attempt-ledger.jsonl').read_bytes().splitlines(keepends=True)
    index=len(lines)
    if index>=12 or attempt!=plan['attempts'][index//2] or state!=('started' if index%2==0 else 'finished'):
        raise ValueError('Cannot append an out-of-order attempt record.')
    path=folder/f'attempt-{attempt["number"]:02d}'/(state+'.json')
    entry={'schema':1,'state':state,'attempt':attempt,'record_sha256':file_hash(path),
           'previous_sha256':digest(lines[-1]) if lines else file_hash(folder/'plan.json')}
    data=(json.dumps(entry,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    with (folder/'attempt-ledger.jsonl').open('ab') as f:
        f.write(data);f.flush();os.fsync(f.fileno())

def capture_host(repo,path):
    windows=Path(os.environ.get('SystemRoot','C:/Windows'))
    shell=windows/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                    '-File',str(repo/'scripts/capture_causal_host_windows.ps1'),
                    '-OutputFile',str(path)],check=True)
    return read(path)

def attempt_files(folder):
    return {p.name:file_hash(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name!='finished.json'}

def check_finished(folder,attempt,plan):
    result=read(folder/'finished.json')
    if result.get('attempt')!=attempt or result.get('plan_sha256')!=file_hash(folder.parent/'plan.json'):
        raise ValueError('Attempt identity differs from the frozen plan.')
    if result.get('files_sha256')!=attempt_files(folder):
        raise ValueError('Recorded attempt artifact was changed: '+folder.name)
    started=read(folder/'started.json')
    if started.get('attempt')!=attempt or started.get('source_revision')!=plan['source_revision']:
        raise ValueError('Started record mismatch.')
    return result

def analyze_attempt(folder,attempt,binary):
    from analyze_causal_receiver import analyze
    from causal_receiver_contract import MODES
    images={m:folder/('runtime.'+m+'.bin') for m in MODES[attempt['study']]}
    return analyze(folder/'trace.log',binary,images)

def collect(repo,folder):
    if sys.platform!='win32':
        raise ValueError('Collection requires Windows. Development traces cannot enter this ledger.')
    folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'collection.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,str(os.getpid()).encode('ascii'))
        plan=create_plan(repo,folder)
        binary=folder/'build/collector.exe'
        known={f'attempt-{a["number"]:02d}' for a in plan['attempts']}
        if any(p.is_dir() and p.name not in known for p in folder.glob('attempt-*')):
            raise ValueError('Unplanned attempt directory. Preserve evidence for review.')
        for attempt in plan['attempts']:
            load_plan(repo,folder)
            target=folder/f'attempt-{attempt["number"]:02d}'
            if target.exists():
                if not (target/'finished.json').exists():
                    raise ValueError('Interrupted attempt retained; no automatic replacement: '+target.name)
                check_finished(target,attempt,plan)
                continue
            validate_ledger(folder,plan)
            target.mkdir()
            write(target/'started.json',{'schema':1,'attempt':attempt,'plan_sha256':file_hash(folder/'plan.json'),
                  'source_revision':plan['source_revision'],'started_utc':utc()},exclusive=True)
            append_ledger(folder,plan,attempt,'started')
            result={'schema':1,'attempt':attempt,'plan_sha256':file_hash(folder/'plan.json'),
                    'outcome':'failed_before_collection','mechanism_proven':False}
            print(f'Attempt {attempt["number"]}/6: {attempt["study"]}, repetition {attempt["repetition"]}, preselected seed {attempt["seed"]}. Collecting 163840 episodes.',flush=True)
            try:
                before=capture_host(repo,target/'host-before.json')
                if host_identity(before)!=plan['host_identity']:
                    raise ValueError('Boot or host configuration changed from the frozen plan.')
                args=[str(binary),attempt['study'],str(attempt['seed']),str(target/'runtime')]
                result['command']=args
                result['execution_start_utc']=utc()
                with (target/'trace.log').open('wb') as out,(target/'stderr.log').open('wb') as err:
                    process=subprocess.run(args,stdout=out,stderr=err,check=False)
                result['execution_exit_code']=process.returncode
                result['execution_end_utc']=utc()
                after=capture_host(repo,target/'host-after.json')
                if host_identity(after)!=plan['host_identity']:
                    raise ValueError('Boot or host configuration changed during the attempt.')
                if file_hash(binary)!=plan['build_sha256']['collector.exe']:
                    raise ValueError('Collector binary changed during collection.')
                if process.returncode:
                    raise ValueError('Collector exited with '+str(process.returncode))
                analysis=analyze_attempt(target,attempt,binary)
                if analysis['study']!=attempt['study'] or analysis['seed']!=attempt['seed'] or analysis['platform']!='windows':
                    raise ValueError('Trace identity differs from the fixed attempt.')
                if analysis['artifact_audit']['binary_sha256']!=plan['build_sha256']['collector.exe']:
                    raise ValueError('Analyzed executable hash differs from the plan.')
                write(target/'analysis.json',analysis,exclusive=True)
                result['outcome']='completed_valid' if analysis['apparatus_controls_pass'] else 'completed_inconclusive_controls'
                result['apparatus_controls_pass']=analysis['apparatus_controls_pass']
                print('  '+result['outcome']+'; response and equivalence intervals retained.',flush=True)
            except Exception as e:
                result['failure']=str(e)
                result['outcome']='failed_attempt_retained'
                print('  Attempt failed and retained: '+str(e),flush=True)
            finally:
                result['finished_utc']=utc()
                result['files_sha256']=attempt_files(target)
                write(target/'finished.json',result,exclusive=True)
                append_ledger(folder,plan,attempt,'finished')
    finally:
        os.close(fd)
        lock.unlink()

def archive_tree(repo,folder,prefix):
    repo_out=repo/'out'; repo_out.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path=repo_out/(prefix+'-'+stamp+'-'+uuid.uuid4().hex[:8]+'.zip')
    files={p.relative_to(folder).as_posix():p for p in folder.rglob('*') if p.is_file()}
    if 'MANIFEST.json' in files:
        raise ValueError('Reserved manifest path in evidence folder.')
    manifest={'schema':1,'study':STUDY,'created_utc':utc(),
              'files_sha256':{n:file_hash(p) for n,p in sorted(files.items())}}
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(files.items()):
            z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('Evidence ZIP CRC check failed.')
    return path

def package(repo,folder):
    folder.mkdir(parents=True,exist_ok=True)
    report={'schema':1,'validated_utc':utc(),'planned_attempts':6,'recorded_attempts':0,
            'outcome':'inconclusive_no_validated_complete_plan','mechanism_proven':False,
            'scope':'Windows user-mode intervention study only; no physical kernel, M1 or exact predictor-mechanism claim.',
            'failures':[],'attempts':[]}
    try:
        plan=load_plan(repo,folder)
        binary=folder/'build/collector.exe'
        expected={f'attempt-{a["number"]:02d}' for a in plan['attempts']}
        if any(p.is_dir() and p.name not in expected for p in folder.glob('attempt-*')):
            raise ValueError('Unexpected attempt folder outside the prospective plan.')
        for attempt in plan['attempts']:
            target=folder/f'attempt-{attempt["number"]:02d}'
            if not target.exists():
                continue
            if not (target/'finished.json').exists():
                raise ValueError('Interrupted attempt retained: '+target.name)
            result=check_finished(target,attempt,plan)
            report['recorded_attempts']+=1
            entry={'attempt':attempt,'outcome':result['outcome']}
            if (target/'analysis.json').exists():
                analysis=analyze_attempt(target,attempt,binary)
                if analysis!=read(target/'analysis.json'):
                    raise ValueError('Saved analysis does not exactly replay: '+target.name)
                if host_identity(read(target/'host-before.json'))!=plan['host_identity'] or host_identity(read(target/'host-after.json'))!=plan['host_identity']:
                    raise ValueError('Attempt host differs from the frozen configuration.')
                entry['analysis']=analysis
            else:
                entry['failure']=result.get('failure','No analysis saved.')
            report['attempts'].append(entry)
        if report['recorded_attempts']==6:
            valid=all(e.get('analysis',{}).get('apparatus_controls_pass',False) for e in report['attempts'])
            report['outcome']='complete_valid_intervention_series' if valid else 'complete_inconclusive_series'
        else:
            report['outcome']='incomplete_series'
        report['all_saved_analyses_replayed']=True
        # Effects remain per attempt; processes on one boot are not host replications.
    except Exception as e:
        report['failures'].append(str(e))
        report['outcome']='inconclusive_invalid_plan_or_evidence'
    write(folder/'summary.json',report)
    path=archive_tree(repo,folder,'causal-windows-evidence')
    return {'archive':str(path),'sha256':file_hash(path),'outcome':report['outcome'],
            'recorded_attempts':report['recorded_attempts'],'planned_attempts':6,'mechanism_proven':False,
            'failures':report['failures']}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('collect','package'))
    p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--folder',required=True,type=Path)
    args=p.parse_args(argv)
    repo=args.repo.resolve();folder=args.folder.resolve()
    # Keep archives outside their input tree and exclude source folders.
    out=(repo/'out').resolve()
    if folder==out or out not in folder.parents:
        raise ValueError('Study folder must be a subdirectory of repository out/.')
    if args.action=='collect':
        collect(repo,folder)
    else:
        print(json.dumps(package(repo,folder),sort_keys=True))

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        print(json.dumps({'error':str(e),'mechanism_proven':False}),file=sys.stderr)
        sys.exit(2)
