"""Read-only archive, source, local chronology and attempt-provenance audit."""
from datetime import datetime
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
REPO=BASE/'windows-followup-repo'
FINAL=BASE/'upload/causal-windows-evidence-20261108T173801487095Z-6d4bcf3a.zip'
PRIOR=BASE/'upload/causal-plan-20261108T173628840158Z-ddcc9de4.zip'
EXPECTED='8080faed480a9eef086f1fc0396e38dba7de31c7'

def digest(data):return hashlib.sha256(data).hexdigest()
def j(data):return json.loads(data.decode('utf-8-sig'))
def instant(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    assert result.tzinfo is not None
    return result
def git(*args):return subprocess.check_output(['git','-C',str(REPO),*args])
def identity(host):
    keys=('boot_utc','cpu','os','bios','baseboard','hypervisor_present','vbs',
          'microcode_update_revision_hex','microcode_query_status','power_plan')
    return {key:host[key] for key in keys}

def checked_archive(path):
    z=zipfile.ZipFile(path)
    names=z.namelist()
    assert len(names)==len(set(names))
    assert z.testzip() is None
    for name in names:
        p=PurePosixPath(name)
        assert not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name
    manifest=j(z.read('MANIFEST.json'))
    assert set(manifest['files_sha256'])==set(names)-{'MANIFEST.json'}
    for name,h in manifest['files_sha256'].items():assert digest(z.read(name))==h,name
    return z,{'filename':path.name,'bytes':path.stat().st_size,'sha256':digest(path.read_bytes()),
              'entries':len(names),'hashed_entries':len(manifest['files_sha256']),
              'zip_crc_and_exact_manifest_valid':True}

def main():
    git('cat-file','-e',EXPECTED+'^{commit}')
    final,final_meta=checked_archive(FINAL)
    prior,prior_meta=checked_archive(PRIOR)
    assert final_meta['sha256']=='9fe89126c57bb68f25ccb8a451fdd7200a96b5b7e29dbbcbaa1b9e626d46d787'
    assert final.read('plan.json')==prior.read('plan.json')
    assert final.read('plan.sha256')==prior.read('plan.sha256')
    plan=j(final.read('plan.json'))
    assert digest(final.read('plan.json'))==final.read('plan.sha256').decode().strip()
    assert plan['source_revision']==EXPECTED
    assert prior.read('attempt-ledger.jsonl')==b''
    assert not any(name.startswith('attempt-0') for name in prior.namelist())
    preserved=[]
    for name in prior.namelist():
        if name in ('MANIFEST.json','attempt-ledger.jsonl','collection.lock'):continue
        assert name in final.namelist() and prior.read(name)==final.read(name),name
        preserved.append(name)
    assert 'collection.lock' not in final.namelist()
    build=j(final.read('build/build.json'))
    assert build['git_head']==EXPECTED and build['git_clean'] is True
    assert build['build_runtime_status']=='built' and build['error'] is None
    assert plan['policy']==j(git('show',EXPECTED+':protocols/WINDOWS_CAUSAL_POLICY.json'))
    assert plan['policy']['total_planned_episodes']==983040
    assert set(plan['source_sha256_lf'])==set(plan['policy']['source_files'])
    assert build['source_sha256_lf']==plan['source_sha256_lf']
    source_bytes=final.read('sources.zip')
    assert digest(source_bytes)==plan['source_archive_sha256']
    source_audit={}
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as sources:
        assert len(sources.namelist())==len(set(sources.namelist()))
        assert set(sources.namelist())==set(plan['source_sha256_lf'])
        for name,h in plan['source_sha256_lf'].items():
            data=sources.read(name)
            assert digest(data)==build['source_sha256'][name]
            assert digest(data.replace(b'\r\n',b'\n'))==h
            assert data.replace(b'\r\n',b'\n')==git('show',EXPECTED+':'+name).replace(b'\r\n',b'\n')
            source_audit[name]=h
    for name,h in plan['build_sha256'].items():assert digest(final.read('build/'+name))==h
    assert build['binary_sha256']==plan['build_sha256']['collector.exe']
    assert set(build['tools'])=={'cl.exe','link.exe','dumpbin.exe'}
    for t in build['tools'].values():assert len(t['sha256'])==64 and t['file_version']
    initial=j(final.read('build/initial-host.json'))
    assert identity(initial)==plan['host_identity']
    assert instant(build['build_start_utc'])<instant(initial['captured_utc'])<=instant(build['build_end_utc'])<instant(plan['created_utc'])
    entries=final.read('attempt-ledger.jsonl').splitlines(keepends=True)
    assert len(entries)==12
    previous=digest(final.read('plan.json'))
    for index,line in enumerate(entries):
        assert line.endswith(b'\n')
        entry=j(line)
        expected=plan['attempts'][index//2]
        state='started' if index%2==0 else 'finished'
        assert entry['schema']==1 and entry['attempt']==expected and entry['state']==state
        assert entry['previous_sha256']==previous
        name=f'attempt-{expected["number"]:02d}/{state}.json'
        assert entry['record_sha256']==digest(final.read(name))
        previous=digest(line)
    attempts=[]
    previous_time=instant(plan['created_utc'])
    total=0
    for expected in plan['attempts']:
        folder=f'attempt-{expected["number"]:02d}'
        started=j(final.read(folder+'/started.json'))
        finished=j(final.read(folder+'/finished.json'))
        analysis=j(final.read(folder+'/analysis.json'))
        before=j(final.read(folder+'/host-before.json'));after=j(final.read(folder+'/host-after.json'))
        assert started['attempt']==finished['attempt']==expected
        assert started['source_revision']==EXPECTED
        assert started['plan_sha256']==finished['plan_sha256']==digest(final.read('plan.json'))
        names={name[len(folder)+1:] for name in final.namelist() if name.startswith(folder+'/')}
        assert set(finished['files_sha256'])==names-{'finished.json'}
        for name,h in finished['files_sha256'].items():assert digest(final.read(folder+'/'+name))==h
        assert identity(before)==identity(after)==plan['host_identity']
        timestamps=[instant(started['started_utc']),instant(before['captured_utc']),instant(finished['execution_start_utc']),
                    instant(finished['execution_end_utc']),instant(after['captured_utc']),instant(finished['finished_utc'])]
        assert previous_time<timestamps[0] and timestamps==sorted(timestamps)
        previous_time=timestamps[-1]
        command=finished['command']
        assert command[1]==expected['study'] and int(command[2])==expected['seed']
        assert PureWindowsPath(command[0]).name=='collector.exe'
        assert PureWindowsPath(command[3]).parts[-2:]==(folder,'runtime')
        assert finished['execution_exit_code']==0 and finished['outcome']=='completed_valid'
        assert final.read(folder+'/stderr.log')==b''
        assert analysis['study']==expected['study'] and analysis['seed']==expected['seed']
        assert analysis['count']==163840 and analysis['platform']=='windows'
        assert analysis['artifact_audit']['binary_sha256']==build['binary_sha256']
        assert analysis['trace_sha256']==digest(final.read(folder+'/trace.log'))
        total+=analysis['count']
        attempts.append({'attempt':expected,'rows':analysis['count'],'heldout_rows':analysis['count']//2,
              'gates_passed':sum(analysis['gates'].values()),'gates_total':len(analysis['gates']),
              'classification':analysis['classification'],'started_utc':started['started_utc'],
              'execution_seconds':(timestamps[3]-timestamps[2]).total_seconds(),
              'finished_utc':finished['finished_utc'],'host_identity_before_after_equal':True,
              'runtime_code_address':analysis['run']['code_addr'],'observed_aux':analysis['observed_tsc_aux']})
    assert total==983040
    report={'passed':True,'scope':'Read-only file, local timestamp and source consistency checks. No executable or uploaded script executed; not independent hardware attestation.',
      'final_archive':final_meta,'prior_plan_archive':prior_meta,'plan_id':plan['plan_id'],
      'plan_sha256':digest(final.read('plan.json')),'plan_created_utc':plan['created_utc'],
      'plan_only_zero_attempts':True,'plan_and_sources_and_build_preserved_from_prior_archive':preserved,
      'source_revision':EXPECTED,'source_files_verified':source_audit,'ledger_entries_verified':12,
      'attempts':attempts,'total_recorded_rows':total,'total_heldout_rows':total//2,
      'all_before_after_host_inventories_match_plan':True,'host_identity':plan['host_identity'],
      'collected_binary_sha256':build['binary_sha256'],'summary_outcome':j(final.read('summary.json'))['outcome'],
      'limitations':['Plan-only archive was supplied alongside final evidence, not externally timestamped before collection.',
                    'Local metadata and hashes establish consistency, not cryptographic CPU attestation.',
                    'One boot, one reported workstation, three fresh processes per study.']}
    (ROOT/'integrity.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':True,'final_hashed_entries':final_meta['hashed_entries'],'prior_hashed_entries':prior_meta['hashed_entries'],
                      'source_files':len(source_audit),'ledger_entries':12,'total_recorded':total,'heldout':total//2}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--final',type=Path,default=FINAL)
    parser.add_argument('--prior',type=Path,default=PRIOR)
    parser.add_argument('--output',type=Path,default=ROOT)
    args=parser.parse_args()
    REPO=args.repo.resolve();FINAL=args.final.resolve();PRIOR=args.prior.resolve();ROOT=args.output.resolve()
    ROOT.mkdir(parents=True,exist_ok=True)
    main()
