"""Prospective, three-boot Windows K5 replication. No mechanism proof is inferred."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gc
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile

import analyze_dependency_receiver as k5

STUDY = 'k5_windows_three_boot_replication_v1'
POLICY = 'protocols/K5_REPLICATION_POLICY.json'
CORE = (
    'programs/dependency_receiver.c', 'programs/cpu_features.c', 'programs/cpu_features.h',
    'programs/dependency_receiver_code.h', 'programs/dependency_receiver_layout.S',
    'scripts/dependency_receiver_contract.py', 'scripts/analyze_cache_probe.py',
    'scripts/verify_dependency_receiver_layout.py', 'protocols/DEPENDENCY_RECEIVER_K5.md',
    'scripts/analyze_dependency_receiver.py', 'scripts/check_dependency_receiver_windows.ps1',
)
FROZEN = CORE + ('.vscode/tasks.json', POLICY, 'protocols/DEPENDENCY_RECEIVER_K5_REPLICATION.md',
                 'scripts/k5_replication.py', 'scripts/run_k5_replication_windows.ps1')
STEM = re.compile(r'^dependency-receiver-windows-[0-9]{8}T[0-9]{9}Z$')


def utc():
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(path):
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, sort_keys=True, indent=2) + '\n'
    if exclusive:
        with path.open('x', encoding='utf-8', newline='\n') as f:
            f.write(content)
    else:
        temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(path)


def git(repo, *arguments):
    return subprocess.check_output(['git', '-C', str(repo), *arguments], text=True).strip()


def local_sources(repo):
    if git(repo, 'status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('Source tree is not clean. Commit or stash edits before collection.')
    return git(repo, 'rev-parse', 'HEAD'), {n: canonical_hash(repo / n) for n in FROZEN}


def validate_host(meta, policy):
    if meta.get('schema') != 1 or not meta.get('machine_fingerprint_sha256'):
        raise ValueError('Missing host identity metadata.')
    if instant(meta['boot_utc']).tzinfo is None:
        raise ValueError('Boot time must include its UTC offset.')
    env = meta['environment']
    expected = policy['baseline_environment']
    for key, value in expected.items():
        if env.get(key) != value:
            raise ValueError(f'Host differs from audited pilot: {key}: {env.get(key)!r}, expected {value!r}.')
    tools=env.get('compiler_tools',{})
    if set(tools) != {'cl.exe','link.exe','dumpbin.exe'} or any(not t.get('file_version') or re.fullmatch('[0-9a-f]{64}',t.get('sha256','')) is None for t in tools.values()):
        raise ValueError('Missing MSVC compiler/linker/disassembler inventory.')
    if env.get('cl_environment') or env.get('_cl_environment'):
        raise ValueError('Unexpected CL/_CL_ compiler option overrides.')
    return env


def python_runtime():
    return dict(version=sys.version, executable_sha256=digest(Path(sys.executable).read_bytes()))


def load_plan(folder):
    path = folder / 'plan.json'
    if digest(path.read_bytes()) != (folder / 'plan.sha256').read_text().strip():
        raise ValueError('Frozen plan SHA256 changed.')
    plan = read(path)
    if plan.get('schema') != 1 or plan.get('study') != STUDY or plan.get('run_count') != 3:
        raise ValueError('Invalid replication plan or changed run count.')
    seeds = plan['seeds']
    if len(seeds) != 3 or len(set(seeds)) != 3 or any(type(s) is not int or not 0 < s < 2**32 for s in seeds):
        raise ValueError('Plan must contain three distinct nonzero uint32 seeds.')
    if plan['exploratory_pilot_seed'] in seeds:
        raise ValueError('Exploratory pilot seed cannot enter the confirmatory set.')
    if set(plan['source_sha256_lf']) != set(FROZEN):
        raise ValueError('Incomplete frozen-source inventory.')
    for name, expected in plan['source_sha256_lf'].items():
        if canonical_hash(folder / 'frozen-source' / name) != expected:
            raise ValueError('Frozen source snapshot changed: ' + name)
    policy = read(folder / 'frozen-source' / POLICY)
    if policy['study'] != STUDY or policy['run_count'] != 3:
        raise ValueError('Frozen policy changed.')
    if policy['core_sha256_lf'] != {n: plan['source_sha256_lf'][n] for n in CORE}:
        raise ValueError('Original K5 measurement code or analysis changed.')
    return plan, policy


def initialize(repo, folder, meta):
    policy = read(repo / POLICY)
    validate_host(meta, policy)
    revision, hashes = local_sources(repo)
    if policy['core_sha256_lf'] != {n: hashes[n] for n in CORE}:
        raise ValueError('K5 core differs from the audited pilot; start a separately reviewed study.')
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'plan.json').exists():
        return load_plan(folder)[0]
    seeds = []
    while len(seeds) != 3:
        seed = secrets.randbelow(2**32 - 1) + 1
        if seed != policy['exploratory_pilot_seed'] and seed not in seeds:
            seeds.append(seed)
    plan = dict(schema=1, study=STUDY, plan_id=str(uuid.uuid4()), run_count=3,
                created_utc=utc(), creation_boot_utc=meta['boot_utc'],
                seeds=seeds, exploratory_pilot_seed=policy['exploratory_pilot_seed'],
                source_revision=revision, source_sha256_lf=hashes,
                analysis_python=python_runtime(),
                machine_fingerprint_sha256=meta['machine_fingerprint_sha256'],
                expected_environment=meta['environment'], initial_host=meta,
                scope='one Windows host, hypervisor present; CPL 3 only',
                time_attestation='local prospective ledger, not an independent preregistration service')
    for name in FROZEN:
        target = folder / 'frozen-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / name, target)
    write(folder / 'plan.json', plan, exclusive=True)
    (folder / 'plan.sha256').write_text(digest((folder / 'plan.json').read_bytes()) + '\n', encoding='ascii')
    return plan


def collect_artifacts(repo, folder, number):
    attempt = folder / f'session-{number:02d}'
    start = read(attempt / 'started.json')
    previous = set(start['preexisting_build_records'])
    builds = [p for p in (repo / 'out').glob('dependency-receiver-windows-*.build.json')
              if p.name not in previous and STEM.fullmatch(p.name.removesuffix('.build.json'))]
    copied = []
    for build in sorted(builds):
        stem = build.name.removesuffix('.build.json')
        archive = build.with_name(stem + '.zip')
        paths = [archive] if archive.is_file() else [p for p in build.parent.glob(stem + '.*') if p.is_file()]
        for path in paths:
            destination = attempt / 'artifacts' / path.name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(str(destination.relative_to(attempt)).replace('\\', '/'))
    return copied


def finish(repo, folder, number, meta, exit_code, *, interrupted=False):
    attempt = folder / f'session-{number:02d}'
    if (attempt / 'finished.json').exists():
        raise ValueError('This slot is already closed; it cannot be retried.')
    errors = []
    try:
        artifacts = collect_artifacts(repo, folder, number)
    except (OSError, ValueError) as exc:
        artifacts = []
        errors.append('Artifact capture failed: ' + str(exc))
    try:
        revision, hashes = local_sources(repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        revision, hashes = None, {}
        errors.append('Post-run source check: ' + str(exc))
    write(attempt / 'finished.json', dict(schema=1, ended_utc=utc(), exit_code=exit_code,
          interrupted=interrupted, artifacts=artifacts, capture_errors=errors,
          artifact_sha256={n:digest((attempt/n).read_bytes()) for n in artifacts},
          source_revision=revision, source_sha256_lf=hashes, host=meta), exclusive=True)


def prepare(repo, folder, meta):
    created = not (folder / 'plan.json').exists()
    plan = initialize(repo, folder, meta)
    plan, policy = load_plan(folder)
    validate_host(meta, policy)
    revision, hashes = local_sources(repo)
    if revision != plan['source_revision'] or hashes != plan['source_sha256_lf']:
        raise ValueError('Source revision or frozen source changed after the plan was saved.')
    if python_runtime() != plan['analysis_python']:
        raise ValueError('The analysis Python runtime changed after plan creation.')
    if meta['machine_fingerprint_sha256'] != plan['machine_fingerprint_sha256'] or meta['environment'] != plan['expected_environment']:
        raise ValueError('Recorded host/configuration changed after plan creation.')
    starts = sorted(folder.glob('session-*/started.json'))
    boot = instant(meta['boot_utc'])
    if len(starts) == 3 and all((p.parent / 'finished.json').exists() for p in starts):
        return dict(action='complete', plan_id=plan['plan_id'], recorded_attempts=3)
    if boot <= instant(plan['created_utc']) or any(instant(read(p)['host']['boot_utc']) == boot for p in starts):
        return dict(action='restart_required', plan_created=created, plan_id=plan['plan_id'],
                    seeds=plan['seeds'], recorded_attempts=len(starts), message='Restart Windows, then run the K5 replication task once.')
    # A terminated/unfinished attempt is retained and consumes its slot. It is
    # never replaced by a new measurement under the same planned seed.
    for p in starts:
        if not (p.parent / 'finished.json').exists():
            finish(repo, folder, read(p)['ordinal'], meta, None, interrupted=True)
    if len(starts) == 3:
        return dict(action='complete', plan_id=plan['plan_id'], recorded_attempts=3)
    if len(starts) > 3:
        raise ValueError('Unexpected extra attempts; retain the folder for review.')
    number = len(starts) + 1
    attempt = folder / f'session-{number:02d}'
    attempt.mkdir()
    write(attempt / 'started.json', dict(schema=1, ordinal=number, seed=plan['seeds'][number-1],
          started_utc=utc(), host=meta, source_revision=revision, source_sha256_lf=hashes,
          preexisting_build_records=sorted(p.name for p in (repo / 'out').glob('dependency-receiver-windows-*.build.json'))), exclusive=True)
    return dict(action='collect', ordinal=number, seed=plan['seeds'][number-1],
                attempt_directory=str(attempt), planned_attempts=3)


def zip_members(archive, limit):
    entries = {}
    if sum(i.file_size for i in archive.infolist()) > limit:
        raise ValueError('Archive exceeds the expected K5 size limit.')
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace('\\', '/')
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or name.casefold() in {n.casefold() for n in entries}:
            raise ValueError('Unsafe or duplicate archive path.')
        entries[name] = archive.read(info)
    return entries


def analyze_archive(path, plan, expected_seed, *, window=None):
    with zipfile.ZipFile(path) as archive:
        files = zip_members(archive, 150_000_000)
    manifests = [n for n in files if n.endswith('.manifest.json')]
    if len(manifests) != 1:
        raise ValueError('Evidence must contain exactly one artifact manifest.')
    manifest = json.loads(files[manifests[0]].decode('utf-8-sig'))
    if set(manifest['files_sha256']) != set(files) - set(manifests):
        raise ValueError('Missing, extra or unhashed evidence artifact.')
    for name, expected in manifest['files_sha256'].items():
        if digest(files[name]) != expected:
            raise ValueError('Artifact SHA256 mismatch: ' + name)
    stem = manifests[0].removesuffix('.manifest.json')
    if not STEM.fullmatch(stem):
        raise ValueError('Unexpected evidence archive basename.')
    build = json.loads(files[stem + '.build.json'].decode('utf-8-sig'))
    host = json.loads(files[stem + '.host.json'].decode('utf-8-sig'))
    if build['seed'] != expected_seed or not build['git_clean'] or build['git_head'] != plan['source_revision'] or manifest['git_head'] != plan['source_revision']:
        raise ValueError('Seed/source revision/clean-tree provenance mismatch.')
    if build.get('execution_exit_code') != 0 or build.get('build_runtime_status') != 'analyzed':
        raise ValueError('K5 did not complete collection and analysis.')
    command=build['compilation_command']
    if command[:6] != ['cl.exe','/nologo','/std:c11','/O2','/W4','/WX'] or len(command)!=9 or \
            not command[6].startswith('/Fe') or not command[6].endswith(stem+'.exe') or \
            not command[7].replace('\\','/').endswith('/programs/dependency_receiver.c') or \
            not command[8].replace('\\','/').endswith('/programs/cpu_features.c'):
        raise ValueError('Compilation command differs from the frozen K5 build.')
    if digest(files[stem + '.exe']) != build.get('binary_sha256'):
        raise ValueError('Build/executable SHA256 mismatch.')
    import io
    with zipfile.ZipFile(io.BytesIO(files[stem + '.sources.zip'])) as archive:
        sources = zip_members(archive, 5_000_000)
    if set(sources) != set(CORE) | {'.vscode/tasks.json'} or set(build['source_sha256']) != set(sources):
        raise ValueError('Incomplete or unexpected K5 source snapshot.')
    for name, data in sources.items():
        if digest(data) != build['source_sha256'][name] or digest(data.replace(b'\r\n', b'\n')) != plan['source_sha256_lf'][name]:
            raise ValueError('Captured source changed: ' + name)
    trace = k5.parse_trace(files[stem + '.log'].decode('utf-8-sig'))
    if trace.run['platform'] != 'windows' or int(trace.run['seed']) != expected_seed:
        raise ValueError('Trace is not the planned Windows run.')
    policy = plan['expected_environment']
    for name,tool in policy.get('compiler_tools',{}).items():
        if build['tools'][name]['file_version'] != tool['file_version']:
            raise ValueError('Recorded build tool differs from the plan: '+name)
    if trace.cpu['signature'].lower() != '0x00b40f40' or trace.cpu['hypervisor'] != '1' or \
            host['virtualization']['HypervisorPresent'] is not True or trace.host['windows_build'] != str(policy['windows_build']):
        raise ValueError('CPU/hypervisor/Windows build differs from the planned configuration.')
    cpu = host['cpu'][0]
    microcode = host['microcode_registry_update_revision']
    if isinstance(microcode,dict): microcode=microcode.get('value')
    if cpu['Name'].strip() != policy['cpu_name'] or cpu['Manufacturer'].strip() != policy['cpu_vendor'] or \
            cpu['NumberOfCores'] != policy['cores'] or cpu['NumberOfLogicalProcessors'] != policy['logical_processors'] or \
            host['os']['Version'] != policy['windows_version'] or \
            host['bios']['SMBIOSBIOSVersion'] != policy['bios_version'] or bytes(microcode).hex() != policy['microcode_update_revision_hex']:
        raise ValueError('K5 host inventory disagrees with the plan.')
    if window:
        lo,hi=(instant(t) for t in window)
        recorded=[datetime.strptime(build['build_start_utc'],'%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc),
                  datetime.strptime(trace.host['run_utc'],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc),
                  datetime.strptime(build['execution_end_utc'],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)]
        if any(t < lo-timedelta(seconds=1) or t > hi+timedelta(seconds=1) for t in recorded):
            raise ValueError('Collection timestamps fall outside the recorded attempt.')
    with tempfile.TemporaryDirectory(prefix='k5-replay-') as temporary:
        folder = Path(temporary)
        paths = []
        for suffix in ('.exe', '.plain.bin', '.mask.bin', '.cpuid.bin'):
            target = folder / ('image' + suffix)
            target.write_bytes(files[stem + suffix]); paths.append(target)
        artifact_audit = k5.audit_files(trace, *paths)
    if not artifact_audit['template_present_in_linked_image']:
        raise ValueError('Frozen template missing from the recorded executable.')
    result = k5.summarize(trace)
    result['artifact_audit'] = artifact_audit
    saved = json.loads(files[stem + '.analysis.json'].decode('utf-8-sig'))
    if result != saved:
        raise ValueError('Replayed frozen analysis differs from the saved analysis.')
    if build.get('control_status') != ('passed' if result['apparatus_controls_pass'] else 'inconclusive') or build.get('numerical_signature_detected') != result['numerical_signature_detected']:
        raise ValueError('Build status disagrees with raw-trace analysis.')
    row = dict(archive=path.name, archive_sha256=digest(path.read_bytes()), seed=expected_seed,
               validated=True, sample_count=result['sample_count'],
               controls_passed=result['apparatus_controls_pass'], gates_passed=sum(result['gates'].values()),
               gates_total=len(result['gates']), failed_gates=[n for n,v in result['gates'].items() if not v],
               numerical_signature=result['numerical_signature_detected'],
               primary=result['outcomes']['p0'], secondary=result['outcomes']['p1'],
               cpu=result['cpu'], thresholds=result['thresholds'],
               mechanism_conclusion='not_proven', user_to_kernel='not_tested')
    del trace, result, files, sources
    gc.collect()
    return row


def classify(rows, deviations):
    if deviations:
        return 'inconclusive_protocol_deviation'
    if len(rows) != 3:
        return 'pending_sessions'
    if not all(r.get('validated') for r in rows):
        return 'inconclusive_invalid_or_missing_evidence'
    if not all(r['controls_passed'] for r in rows):
        return 'inconclusive_failed_controls'
    count = sum(r['numerical_signature'] for r in rows)
    return ('replicated_k5_numerical_signature_this_host_configuration' if count == 3 else
            'no_k5_numerical_signature_in_three_valid_runs' if count == 0 else
            'not_consistently_replicated')


def audit(folder):
    plan, policy = load_plan(folder)
    active_root=Path(__file__).resolve().parents[1]
    if any(canonical_hash(active_root/n) != expected for n,expected in plan['source_sha256_lf'].items()):
        raise ValueError('Active validation/source files differ from the frozen plan.')
    rows, deviations, boots = [], [], []
    previous_end=None
    for number in range(1, 4):
        attempt = folder / f'session-{number:02d}'
        if not (attempt / 'started.json').exists():
            continue
        start = read(attempt / 'started.json')
        row = dict(ordinal=number, seed=plan['seeds'][number-1], validated=False)
        for key, expected in [('ordinal',number), ('seed',row['seed']), ('source_revision',plan['source_revision']), ('source_sha256_lf',plan['source_sha256_lf'])]:
            if start.get(key) != expected:
                deviations.append(f'session {number}: changed {key}')
        meta = start['host']; boot = meta['boot_utc']; boots.append(boot)
        if instant(boot) <= instant(plan['created_utc']) or instant(start['started_utc']) < instant(boot):
            deviations.append(f'session {number}: boot does not follow plan creation')
        if previous_end and instant(boot) <= previous_end:
            deviations.append(f'session {number}: boot overlaps the previous attempt')
        if meta['machine_fingerprint_sha256'] != plan['machine_fingerprint_sha256'] or meta['environment'] != plan['expected_environment']:
            deviations.append(f'session {number}: host/configuration mismatch')
        try:
            end = read(attempt / 'finished.json')
            if end['interrupted'] or end['exit_code'] != 0 or end['capture_errors']:
                raise ValueError('Interrupted/failed collector or artifact capture; attempt retained.')
            actual={str(p.relative_to(attempt)).replace('\\','/') for p in (attempt/'artifacts').rglob('*') if p.is_file()}
            if actual != set(end['artifacts']) or actual != set(end['artifact_sha256']):
                raise ValueError('Captured artifact inventory changed after the attempt.')
            if any(digest((attempt/n).read_bytes()) != end['artifact_sha256'][n] for n in actual):
                raise ValueError('Captured artifact hash changed after the attempt.')
            if end['source_revision'] != plan['source_revision'] or end['source_sha256_lf'] != plan['source_sha256_lf'] or end['host']['boot_utc'] != boot or end['host']['environment'] != plan['expected_environment'] or end['host']['machine_fingerprint_sha256'] != plan['machine_fingerprint_sha256']:
                deviations.append(f'session {number}: post-run source/host changed')
            if instant(end['ended_utc']) < instant(start['started_utc']):
                deviations.append(f'session {number}: reversed timestamps')
            previous_end=instant(end['ended_utc'])
            paths = [p for p in (attempt / 'artifacts').glob('*.zip') if STEM.fullmatch(p.stem)]
            if len(paths) != 1:
                raise ValueError('Expected exactly one complete K5 evidence ZIP; source snapshots do not count.')
            row.update(analyze_archive(paths[0], plan, row['seed'],window=(start['started_utc'],end['ended_utc'])))
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            row['error'] = str(exc)
        row['boot_utc'] = boot
        rows.append(row)
    if len(set(instant(b) for b in boots)) != len(boots) or [instant(b) for b in boots] != sorted(instant(b) for b in boots):
        deviations.append('Repeated or nonchronological Windows boot identifiers.')
    expected_dirs = {f'session-{i:02d}' for i in range(1,4)}
    if any(p.name not in expected_dirs for p in folder.glob('session-*')):
        deviations.append('Unexpected extra session directories.')
    result = dict(schema=1, study=STUDY, plan_id=plan['plan_id'], planned_runs=3,
                  recorded_attempts=len(rows), validated_runs=sum(r['validated'] for r in rows),
                  source_revision=plan['source_revision'], results=rows, deviations=deviations,
                  outcome=classify(rows,deviations), mechanism_proven=False,
                  fractal_paper_claims_reproduced=False, user_to_kernel_tested=False,
                  environment_scope='one Windows host with a hypervisor present',
                  bootstrap_scope='per-run 16-block cycles; no pooled between-host confidence interval',
                  exploratory_pilot_included=False, local_boot_records_are_independent_attestation=False)
    valid = [r['primary']['interaction']['hit_rate_difference'] for r in rows if r['validated']]
    if valid:
        result['descriptive_primary_mean'] = sum(valid)/len(valid)
        result['descriptive_primary_range'] = [min(valid),max(valid)]
    return result


def package(folder, destination):
    try:
        report = audit(folder)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = dict(schema=1, study=STUDY, outcome='inconclusive_invalid_plan_or_ledger', error=str(exc),
                      mechanism_proven=False, fractal_paper_claims_reproduced=False, user_to_kernel_tested=False)
    write(folder / 'analysis.json', report)
    files = sorted(p for p in folder.rglob('*') if p.is_file() and p.name != 'files-sha256.json')
    hashes = {str(p.relative_to(folder)).replace('\\','/'): digest(p.read_bytes()) for p in files}
    write(folder / 'files-sha256.json', hashes)
    files.append(folder / 'files-sha256.json')
    if destination.exists():
        raise ValueError('Evidence ZIP already exists; existing files will not be overwritten.')
    temporary = destination.with_suffix('.partial')
    if temporary.exists():
        raise ValueError('A partial evidence ZIP already exists; retain it for review.')
    try:
        with zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED) as z:
            for path in files:
                z.write(path,str(path.relative_to(folder)).replace('\\','/'),
                        compress_type=zipfile.ZIP_STORED if path.suffix=='.zip' else zipfile.ZIP_DEFLATED)
        temporary.rename(destination)
    except BaseException:
        if temporary.exists(): temporary.unlink()
        raise
    return dict(archive=str(destination), sha256=digest(destination.read_bytes()), outcome=report['outcome'],
                recorded_attempts=report.get('recorded_attempts',0), planned_runs=3,
                mechanism_proven=False, fractal_paper_claims_reproduced=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','finish','package'))
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--metadata',type=Path)
    p.add_argument('--ordinal',type=int)
    p.add_argument('--exit-code',type=int)
    p.add_argument('--archive',type=Path)
    args = p.parse_args()
    try:
        if args.action=='prepare':
            output=prepare(args.repo,args.folder,read(args.metadata))
        elif args.action=='finish':
            if args.ordinal not in (1,2,3):raise ValueError('Invalid attempt ordinal.')
            finish(args.repo,args.folder,args.ordinal,read(args.metadata),args.exit_code)
            output=dict(action='attempt_recorded',ordinal=args.ordinal)
        else:
            output=package(args.folder,args.archive)
        print(json.dumps(output,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(error=str(exc),mechanism_proven=False)),file=__import__('sys').stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
