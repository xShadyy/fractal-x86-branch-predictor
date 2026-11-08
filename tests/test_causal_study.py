"""Controller integrity fixtures only: no Windows execution or CPU measurements."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REAL_RUN = subprocess.run
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import causal_receiver_study as study
from causal_receiver_contract import MODES


def host_fixture():
    return dict(schema=1, captured_utc='2030-01-01T12:00:00+00:00',
        boot_utc='2030-01-01T11:00:00+00:00',
        cpu={'Name':'SOFTWARE FIXTURE CPU'}, os={'BuildNumber':'SOFTWARE FIXTURE BUILD'},
        bios={'Version':'FIXTURE'}, baseboard={'Product':'FIXTURE'},
        hypervisor_present=True, vbs={'status':'FIXTURE'},
        microcode_update_revision_hex='aabbccdd', microcode_query_status='available',
        power_plan='SOFTWARE FIXTURE POWER PLAN')


class CausalStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=tempfile.TemporaryDirectory(prefix='causal-study-tests-')
        cls.template=Path(cls.master.name)/'template';cls.template.mkdir()
        policy=study.read(ROOT/study.POLICY)
        for name in policy['source_files']:
            target=cls.template/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        (cls.template/'.gitignore').write_text('out/\n__pycache__/\n')
        subprocess.run(['git','init','-q','-b','main',str(cls.template)],check=True)
        subprocess.run(['git','-C',str(cls.template),'add','.'],check=True)
        subprocess.run(['git','-C',str(cls.template),'-c','user.name=Software Fixture',
            '-c','user.email=fixture@example.invalid','commit','-qm','Software fixture only'],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.master.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=self.master.name)
        self.repo=Path(self.temp.name)/'repo'
        subprocess.run(['git','clone','-q',str(self.template),str(self.repo)],check=True)
        self.folder=self.repo/'out/study'
        build=self.folder/'build';build.mkdir(parents=True)
        self.host=host_fixture()
        self.runtime=dict(version='SOFTWARE FIXTURE PYTHON',image_sha256='a'*64,
                          image_path='SOFTWARE FIXTURE PATH')
        for name,data in [('collector.exe',b'NOT AN EXECUTABLE: SOFTWARE FIXTURE'),
                          ('collector.disasm.txt',b'NOT DISASSEMBLY: SOFTWARE FIXTURE'),
                          ('build.log',b'NO COMPILATION: SOFTWARE FIXTURE')]:
            (build/name).write_bytes(data)
        revision,sources=study.source_state(self.repo)
        study.write(build/'initial-host.json',self.host)
        study.write(build/'build.json',dict(schema=1,study='windows_causal_followup',
            build_runtime_status='built',git_head=revision,git_clean=True,
            source_sha256_lf=sources,binary_sha256=study.file_hash(build/'collector.exe'),
            tools={n:dict(sha256='b'*64,file_version='SOFTWARE FIXTURE')
                   for n in ('cl.exe','link.exe','dumpbin.exe')}))
        self.patches=ExitStack()
        self.patches.enter_context(patch.object(study,'runtime',side_effect=lambda:deepcopy(self.runtime)))
        self.addCleanup(self.patches.close)
        self.addCleanup(self.temp.cleanup)
        self.launches=[];self.capture_count=0;self.analysis_calls=[]

    def plan(self):
        with redirect_stdout(StringIO()):
            return study.create_plan(self.repo,self.folder)

    def capture(self,repo,path):
        self.capture_count+=1
        host=deepcopy(self.host);host['captured_utc']=f'2030-01-01T12:{self.capture_count:02d}:00+00:00'
        study.write(path,host)
        return host

    def execute(self,args,stdout,stderr,check=False):
        # This intercepts only the collector subprocess. It never executes one.
        self.assertTrue((self.folder/'plan.json').exists())
        self.assertTrue((self.folder/'plan.sha256').exists())
        snapshots=list((self.repo/'out').glob('causal-plan-*.zip'))
        self.assertEqual(len(snapshots),1)
        with zipfile.ZipFile(snapshots[0]) as z:
            self.assertIn('plan.json',z.namelist())
            self.assertEqual(z.read('attempt-ledger.jsonl'),b'')
            self.assertFalse(any(n.startswith('attempt-') for n in z.namelist() if n!='attempt-ledger.jsonl'))
        _,name,seed,prefix=args
        target=Path(prefix).parent
        fixture=dict(study=name,seed=int(seed),platform='windows',apparatus_controls_pass=True,
            classification='SOFTWARE FIXTURE ONLY',mechanism_proven=False,
            artifact_audit={'binary_sha256':study.file_hash(self.folder/'build/collector.exe')})
        stdout.write(json.dumps(fixture).encode('utf-8'))
        stderr.write(b'NONMEASURING PROCESS STUB\n')
        for mode in MODES[name]:
            (target/('runtime.'+mode+'.bin')).write_bytes(b'SOFTWARE RUNTIME FIXTURE '+mode.encode())
        self.launches.append((name,int(seed)))
        return subprocess.CompletedProcess(args,0)

    def analyze(self,target,attempt,binary):
        self.analysis_calls.append(attempt['number'])
        return study.read(target/'trace.log')

    def collect(self,*,capture=None,execute=None,analyze=None):
        # All native interactions are mocked. The Windows platform selection
        # exercises controller branches, not real Windows compatibility.
        def dispatch(args,*positional,**kwargs):
            if args[0]=='git':
                return REAL_RUN(args,*positional,**kwargs)
            return (execute or self.execute)(args,*positional,**kwargs)
        with patch.object(study.sys,'platform','win32'), \
             patch.object(study,'capture_host',side_effect=capture or self.capture), \
             patch.object(study.subprocess,'run',side_effect=dispatch), \
             patch.object(study,'analyze_attempt',side_effect=analyze or self.analyze), \
             redirect_stdout(StringIO()):
            study.collect(self.repo,self.folder)

    def package(self,*,analyze=None):
        with patch.object(study,'analyze_attempt',side_effect=analyze or self.analyze):
            result=study.package(self.repo,self.folder)
        with zipfile.ZipFile(result['archive']) as z:
            self.assertIsNone(z.testzip())
            manifest=json.loads(z.read('MANIFEST.json'))
            self.assertEqual(set(manifest['files_sha256']),set(z.namelist())-{'MANIFEST.json'})
            for name,expected in manifest['files_sha256'].items():
                self.assertEqual(study.digest(z.read(name)),expected,name)
        return result

    def start_without_finishing(self):
        plan=self.plan();attempt=plan['attempts'][0]
        target=self.folder/'attempt-01';target.mkdir()
        study.write(target/'started.json',dict(schema=1,attempt=attempt,
            plan_sha256=study.file_hash(self.folder/'plan.json'),
            source_revision=plan['source_revision'],started_utc=study.utc()),exclusive=True)
        study.append_ledger(self.folder,plan,attempt,'started')
        (target/'trace.log').write_bytes(b'PARTIAL SOFTWARE TRACE FIXTURE')
        return target

    def test_plan_freezes_six_unique_seeds_and_three_interleaved_pairs_before_launch(self):
        with patch.object(study.secrets,'randbits',side_effect=[0,11,11,22,33,44,55,66]):
            plan=self.plan()
        self.assertEqual([a['number'] for a in plan['attempts']],list(range(1,7)))
        self.assertEqual([a['seed'] for a in plan['attempts']],[11,22,33,44,55,66])
        for i in range(3):
            pair=plan['attempts'][i*2:i*2+2]
            self.assertEqual({a['study'] for a in pair},{'dependency','receiver'})
            self.assertEqual({a['repetition'] for a in pair},{i+1})
        self.assertFalse(list(self.folder.glob('attempt-??')))
        self.assertEqual(self.launches,[])
        before=(self.folder/'plan.json').read_bytes()
        self.assertEqual(self.plan(),plan)
        self.assertEqual((self.folder/'plan.json').read_bytes(),before)

    def test_capture_timestamp_is_excluded_but_boot_and_configuration_are_frozen(self):
        host=deepcopy(self.host);host['captured_utc']='2030-01-02T12:00:00+00:00'
        self.assertEqual(study.host_identity(host),study.host_identity(self.host))
        for field,value in [('boot_utc','2030-01-02T11:00:00+00:00'),
                            ('os',{'BuildNumber':'CHANGED'}),('hypervisor_present',False),
                            ('power_plan','CHANGED')]:
            changed=deepcopy(self.host);changed[field]=value
            self.assertNotEqual(study.host_identity(changed),study.host_identity(self.host),field)

    def test_missing_host_configuration_is_rejected(self):
        for field in ('bios','microcode_query_status','power_plan'):
            host=deepcopy(self.host);del host[field]
            with self.assertRaisesRegex(ValueError,'Missing host'):study.host_identity(host)
        host=deepcopy(self.host);host['hypervisor_present']='true'
        with self.assertRaisesRegex(ValueError,'Boolean'):study.host_identity(host)

    def test_build_source_inventory_mismatch_prevents_initial_plan(self):
        path=self.folder/'build/build.json';record=study.read(path)
        record['source_sha256_lf']={};study.write(path,record)
        with self.assertRaisesRegex(ValueError,'source inventory'):self.plan()
        self.assertFalse((self.folder/'plan.json').exists())

    def test_failed_build_cannot_be_frozen_as_a_measurement_plan(self):
        path=self.folder/'build/build.json';record=study.read(path)
        record['build_runtime_status']='failed';study.write(path,record)
        with self.assertRaisesRegex(ValueError,'did not finish successfully'):self.plan()
        self.assertFalse((self.folder/'plan.json').exists())

    def test_changed_live_source_is_rejected(self):
        self.plan();path=self.repo/'programs/causal_receiver.c';path.write_bytes(path.read_bytes()+b'\n/* changed */\n')
        with self.assertRaisesRegex(ValueError,'not clean'):study.load_plan(self.repo,self.folder)

    def test_changed_build_file_is_rejected(self):
        self.plan();(self.folder/'build/collector.exe').write_bytes(b'CHANGED FIXTURE BINARY')
        with self.assertRaisesRegex(ValueError,'Build or source archive changed'):study.load_plan(self.repo,self.folder)

    def test_changed_source_snapshot_is_rejected(self):
        self.plan()
        with (self.folder/'sources.zip').open('ab') as f:f.write(b'CHANGED ARCHIVE FIXTURE')
        with self.assertRaisesRegex(ValueError,'Build or source archive changed'):study.load_plan(self.repo,self.folder)

    def test_changed_plan_bytes_are_rejected(self):
        self.plan();path=self.folder/'plan.json';value=study.read(path);value['attempts'][0]['seed']=99;study.write(path,value)
        with self.assertRaisesRegex(ValueError,'plan hash mismatch'):study.load_plan(self.repo,self.folder)

    def test_duplicate_or_out_of_range_plan_seeds_rejected_after_digest_reseal(self):
        self.plan();path=self.folder/'plan.json';original=study.read(path)
        for value in (0,2**32,original['attempts'][1]['seed']):
            plan=deepcopy(original);plan['attempts'][0]['seed']=value;study.write(path,plan)
            (self.folder/'plan.sha256').write_text(study.file_hash(path)+'\n')
            with self.assertRaisesRegex(ValueError,'Invalid'):study.load_plan(self.repo,self.folder)

    def test_runtime_change_blocks_before_collection(self):
        self.plan();self.runtime['image_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'Python runtime'):self.collect()
        self.assertEqual(self.launches,[])
        self.assertFalse((self.folder/'collection.lock').exists())

    def test_complete_controller_freezes_plan_before_all_six_processes_and_cleans_lock(self):
        self.collect();plan=study.load_plan(self.repo,self.folder)
        self.assertEqual(self.launches,[(a['study'],a['seed']) for a in plan['attempts']])
        self.assertEqual(len(study.validate_ledger(self.folder,plan)),12)
        self.assertEqual(self.capture_count,12)
        self.assertFalse((self.folder/'collection.lock').exists())
        self.collect()
        self.assertEqual(len(self.launches),6)

    def test_existing_lock_blocks_another_controller_without_removing_lock(self):
        lock=self.folder/'collection.lock';lock.write_text('EXISTING OWNER FIXTURE')
        with self.assertRaises(FileExistsError):self.collect()
        self.assertEqual(lock.read_text(),'EXISTING OWNER FIXTURE')
        self.assertEqual(self.launches,[])

    def test_deleted_whole_attempt_folder_is_detected_without_replacement(self):
        self.collect();shutil.rmtree(self.folder/'attempt-03');launched=len(self.launches)
        with self.assertRaisesRegex(ValueError,'Ledger-bound'):self.collect()
        self.assertEqual(len(self.launches),launched)
        self.assertFalse((self.folder/'attempt-03').exists())

    def test_changed_started_and_finished_records_are_ledger_bound(self):
        self.collect()
        for name in ('started.json','finished.json'):
            path=self.folder/'attempt-02'/name;before=path.read_bytes()
            path.write_bytes(before+b'\n')
            with self.assertRaisesRegex(ValueError,'Ledger-bound'):study.load_plan(self.repo,self.folder)
            path.write_bytes(before)

    def test_partial_or_reordered_ledger_blocks_future_collection(self):
        self.collect();path=self.folder/'attempt-ledger.jsonl';original=path.read_bytes()
        path.write_bytes(original[:-1])
        with self.assertRaisesRegex(ValueError,'Partial'):study.load_plan(self.repo,self.folder)
        lines=original.splitlines(keepends=True);lines[0],lines[1]=lines[1],lines[0];path.write_bytes(b''.join(lines))
        with self.assertRaisesRegex(ValueError,'sequence mismatch'):study.load_plan(self.repo,self.folder)

    def test_interrupted_attempt_blocks_without_automatic_replacement(self):
        target=self.start_without_finishing();saved=(target/'trace.log').read_bytes()
        with self.assertRaisesRegex(ValueError,'Interrupted attempt retained'):self.collect()
        self.assertEqual(self.launches,[])
        self.assertEqual((target/'trace.log').read_bytes(),saved)
        self.assertFalse((self.folder/'attempt-02').exists())
        self.assertFalse((self.folder/'collection.lock').exists())

    def test_partial_interrupted_evidence_is_packaged_with_valid_manifest(self):
        target=self.start_without_finishing();raw=(target/'trace.log').read_bytes()
        result=self.package()
        self.assertEqual(result['outcome'],'inconclusive_invalid_plan_or_evidence')
        with zipfile.ZipFile(result['archive']) as z:
            self.assertEqual(z.read('attempt-01/trace.log'),raw)
            self.assertIn('Interrupted attempt retained',z.read('summary.json').decode())
        self.assertEqual((target/'trace.log').read_bytes(),raw)

    def test_changed_attempt_artifact_is_rejected_and_preserved_in_failure_package(self):
        self.collect();path=self.folder/'attempt-02/trace.log';path.write_bytes(b'ALTERED RAW FIXTURE')
        result=self.package()
        self.assertEqual(result['outcome'],'inconclusive_invalid_plan_or_evidence')
        self.assertTrue(any('artifact was changed' in e for e in result['failures']))
        with zipfile.ZipFile(result['archive']) as z:
            self.assertEqual(z.read('attempt-02/trace.log'),b'ALTERED RAW FIXTURE')
        self.assertEqual(path.read_bytes(),b'ALTERED RAW FIXTURE')

    def test_complete_package_replays_each_saved_analysis_exactly(self):
        self.collect();self.analysis_calls.clear();result=self.package()
        self.assertEqual(self.analysis_calls,list(range(1,7)))
        self.assertEqual(result['outcome'],'complete_valid_intervention_series')
        self.assertEqual(result['recorded_attempts'],6)
        self.assertFalse(result['mechanism_proven'])
        report=study.read(self.folder/'summary.json')
        self.assertTrue(report['all_saved_analyses_replayed'])
        self.assertEqual(len(report['attempts']),6)
        self.assertFalse(report['mechanism_proven'])

    def test_changed_replayed_analysis_prevents_complete_valid_label(self):
        self.collect()
        def changed(target,attempt,binary):
            result=self.analyze(target,attempt,binary);result['classification']='DIFFERENT REPLAY FIXTURE';return result
        result=self.package(analyze=changed)
        self.assertEqual(result['outcome'],'inconclusive_invalid_plan_or_evidence')
        self.assertTrue(any('does not exactly replay' in e for e in result['failures']))

    def test_collector_failure_consumes_slot_and_keeps_raw_output(self):
        def failed(*args,**kwargs):
            process=self.execute(*args,**kwargs)
            return subprocess.CompletedProcess(process.args,7)
        self.collect(execute=failed)
        self.assertEqual(len(self.launches),6)
        for target in sorted(self.folder.glob('attempt-??')):
            end=study.read(target/'finished.json')
            self.assertEqual(end['execution_exit_code'],7)
            self.assertEqual(end['outcome'],'failed_attempt_retained')
            self.assertTrue((target/'trace.log').exists())
            self.assertFalse((target/'analysis.json').exists())
        self.collect();self.assertEqual(len(self.launches),6)
        self.assertEqual(self.package()['outcome'],'complete_inconclusive_series')

    def test_boot_or_configuration_change_cannot_be_silently_collected(self):
        self.plan()
        def changed(repo,path):
            host=self.capture(repo,path);host['boot_utc']='2030-01-02T11:00:00+00:00';study.write(path,host);return host
        self.collect(capture=changed)
        self.assertEqual(self.launches,[])
        self.assertEqual(len(list(self.folder.glob('attempt-??'))),6)
        for target in self.folder.glob('attempt-??'):
            self.assertIn('configuration changed',study.read(target/'finished.json')['failure'])

    def test_native_development_analysis_cannot_enter_windows_collection(self):
        def development(target,attempt,binary):
            result=self.analyze(target,attempt,binary);result['platform']='native_dev';return result
        self.collect(analyze=development)
        self.assertEqual(len(self.launches),6)
        for target in self.folder.glob('attempt-??'):
            end=study.read(target/'finished.json')
            self.assertEqual(end['outcome'],'failed_attempt_retained')
            self.assertIn('Trace identity differs',end['failure'])
            self.assertFalse((target/'analysis.json').exists())
        self.assertEqual(self.package()['outcome'],'complete_inconclusive_series')

    def test_non_windows_platform_cannot_start_collection(self):
        with patch.object(study.sys,'platform','linux'):
            with self.assertRaisesRegex(ValueError,'requires Windows'):study.collect(self.repo,self.folder)
        self.assertFalse((self.folder/'plan.json').exists())
        self.assertEqual(self.launches,[])


if __name__=='__main__':
    unittest.main()
