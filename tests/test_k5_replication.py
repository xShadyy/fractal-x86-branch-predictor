"""Software-only fixtures for K5 replication; these are not processor measurements."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import k5_replication as rep


def summary(seed=1,positive=True,controls=True):
    effect={'hit_rate_difference':.99 if positive else 0,'ci95':[.98,1] if positive else [-.01,.01]}
    return dict(validated=True,seed=seed,sample_count=393216,controls_passed=controls,
        gates_passed=88 if controls else 87,gates_total=88,numerical_signature=positive and controls,
        primary={'interaction':deepcopy(effect)},secondary={},mechanism_conclusion='not_proven',
        user_to_kernel='not_tested',scope='SOFTWARE FIXTURE, NOT A HARDWARE RESULT')


class ReplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory(prefix='k5-replication-tests-')
        cls.template=Path(cls.temporary.name)/'template';cls.template.mkdir()
        for name in rep.FROZEN+('.gitignore',):
            target=cls.template/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        subprocess.run(['git','init','-q','-b','main',str(cls.template)],check=True)
        subprocess.run(['git','-C',str(cls.template),'add','.'],check=True)
        subprocess.run(['git','-C',str(cls.template),'-c','user.name=Software Fixture',
            '-c','user.email=fixture@example.invalid','commit','-qm','Software-only test fixture'],check=True)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=self.temporary.name)
        self.repo=Path(self.temp.name)/'repo'
        subprocess.run(['git','clone','-q',str(self.template),str(self.repo)],check=True)
        self.folder=self.repo/'out/k5-replication'
        self.clock=datetime(2030,1,1,12,tzinfo=timezone.utc)
        self.patcher=patch.object(rep,'utc',side_effect=lambda:self.clock.isoformat());self.patcher.start()
        env=deepcopy(rep.read(self.repo/rep.POLICY)['baseline_environment'])
        env.update(windows_ubr=1234,vbs_query='available',vbs_status=2,vbs_services_running=[1,2],
            cl_environment='',_cl_environment='',compiler_tools={n:{'file_version':'SOFTWARE FIXTURE','sha256':'b'*64} for n in ['cl.exe','link.exe','dumpbin.exe']})
        self.meta={'schema':1,'boot_utc':(self.clock-timedelta(hours=1)).isoformat(),
            'machine_fingerprint_sha256':'a'*64,'environment':env,
            'scope':'SOFTWARE FIXTURE, NOT HARDWARE INVENTORY'}

    def tearDown(self):self.patcher.stop();self.temp.cleanup()

    def create(self):
        with patch.object(rep.secrets,'randbelow',side_effect=[10,20,30]):
            response=rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual(response['action'],'restart_required')
        return rep.load_plan(self.folder)[0]

    def fresh_boot(self):
        self.clock+=timedelta(hours=1)
        self.meta['boot_utc']=(self.clock-timedelta(minutes=1)).isoformat()

    def attempt(self,finish=True,exit_code=0):
        self.fresh_boot();decision=rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual(decision['action'],'collect')
        number=decision['ordinal']
        stem='dependency-receiver-windows-'+self.clock.strftime('%Y%m%dT%H%M%S')+'000Z'
        (self.repo/'out'/ (stem+'.build.json')).write_text('{"software_fixture_only":true}')
        (self.repo/'out'/ (stem+'.zip')).write_bytes(b'SOFTWARE FIXTURE. NOT A TRACE OR MEASUREMENT.')
        if finish:rep.finish(self.repo,self.folder,number,self.meta,exit_code)
        return decision

    def test_first_invocation_freezes_all_seeds_without_collecting(self):
        plan=self.create()
        self.assertEqual(len(set(plan['seeds'])),3)
        self.assertNotIn(1143445439,plan['seeds'])
        self.assertFalse(list(self.folder.glob('session-*')))

    def test_store_python_alias_is_not_opened_when_hashing_loaded_runtime(self):
        image=Path(self.temp.name)/'real Python runtime.exe';image.write_bytes(b'SOFTWARE EXECUTABLE FIXTURE')
        alias=r'C:\Users\Shadyy\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe'
        def loaded_image(module,buffer,size):
            self.assertIsNone(module);buffer.value=str(image);return len(str(image))
        api=Mock(side_effect=loaded_image)
        with patch.object(rep.sys,'platform','win32'),patch.object(rep.sys,'executable',alias), \
                patch('ctypes.WinDLL',return_value=SimpleNamespace(GetModuleFileNameW=api),create=True):
            runtime=rep.python_runtime()
        self.assertEqual(runtime['executable_sha256'],rep.digest(image.read_bytes()))
        self.assertEqual(runtime['executable_path'],str(image.resolve()))
        api.assert_called_once()

    def test_ordinary_runtime_still_requires_executable_bytes(self):
        image=Path(self.temp.name)/'python';image.write_bytes(b'ORDINARY RUNTIME FIXTURE')
        with patch.object(rep.sys,'platform','linux'),patch.object(rep.sys,'executable',str(image)):
            self.assertEqual(rep.python_runtime()['executable_sha256'],rep.digest(image.read_bytes()))
            image.unlink()
            with self.assertRaises(OSError):rep.python_runtime()

    def test_native_runtime_lookup_failure_does_not_use_unverified_alias(self):
        api=Mock(return_value=0)
        with patch.object(rep.sys,'platform','win32'), \
                patch('ctypes.WinDLL',return_value=SimpleNamespace(GetModuleFileNameW=api),create=True):
            with self.assertRaisesRegex(ValueError,'could not locate'):rep.python_runtime()

    def test_truncated_native_runtime_path_is_rejected(self):
        api=Mock(side_effect=lambda module,buffer,size:size)
        with patch.object(rep.sys,'platform','win32'), \
                patch('ctypes.WinDLL',return_value=SimpleNamespace(GetModuleFileNameW=api),create=True):
            with self.assertRaisesRegex(ValueError,'truncated'):rep.python_runtime()

    def test_runtime_change_blocks_collection_without_consuming_attempt(self):
        image=Path(self.temp.name)/'python';image.write_bytes(b'ORIGINAL RUNTIME FIXTURE')
        with patch.object(rep,'runtime_executable',return_value=image):
            self.create();saved=(self.folder/'plan.json').read_bytes()
            image.write_bytes(b'CHANGED RUNTIME FIXTURE');self.fresh_boot()
            with self.assertRaisesRegex(ValueError,'Python runtime changed'):
                rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual((self.folder/'plan.json').read_bytes(),saved)
        self.assertFalse(list(self.folder.glob('session-*')))

    def test_startup_alias_failure_recovery_preserves_logs_and_progress_archive(self):
        self.folder.mkdir(parents=True)
        log=self.folder/'controller-error-before-repair.json';log.write_text('{"error":"alias read failed"}')
        previous=self.repo/'out/k5-replication-evidence-before-repair.zip'
        previous.write_bytes(b'EXISTING PROGRESS ZIP FIXTURE')
        with patch.object(rep,'python_runtime',side_effect=OSError(22,'Invalid argument','WindowsApps/python.exe')):
            with self.assertRaises(OSError):rep.prepare(self.repo,self.folder,self.meta)
        self.assertFalse((self.folder/'plan.json').exists())
        self.assertFalse(list(self.folder.glob('session-*')))
        self.create()
        self.assertEqual(log.read_text(),'{"error":"alias read failed"}')
        self.assertEqual(previous.read_bytes(),b'EXISTING PROGRESS ZIP FIXTURE')
        self.assertFalse(list(self.folder.glob('session-*')))

    def test_plan_cannot_be_reseeded_by_repeated_invocation(self):
        before=self.create();after=rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual(after['action'],'restart_required')
        self.assertEqual(rep.load_plan(self.folder)[0],before)

    def test_first_and_later_measurements_require_new_boots(self):
        self.create();first=self.attempt()
        repeat=rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual(repeat['action'],'restart_required')
        self.assertEqual(len(list(self.folder.glob('session-*/started.json'))),1)
        self.assertEqual(first['ordinal'],1)

    def test_completed_plan_does_not_demand_fourth_reboot_or_collect_again(self):
        self.create()
        for _ in range(3):self.attempt()
        self.assertEqual(rep.prepare(self.repo,self.folder,self.meta)['action'],'complete')
        self.assertEqual(len(list(self.folder.glob('session-*/started.json'))),3)

    def test_interrupted_attempt_consumes_slot_and_retains_artifacts(self):
        self.create();self.attempt(finish=False);self.fresh_boot()
        second=rep.prepare(self.repo,self.folder,self.meta)
        self.assertEqual(second['ordinal'],2)
        end=rep.read(self.folder/'session-01/finished.json')
        self.assertTrue(end['interrupted']);self.assertTrue(end['artifacts'])

    def test_dirty_source_prevents_collection(self):
        self.create();self.fresh_boot()
        p=self.repo/'programs/dependency_receiver.c';p.write_text(p.read_text()+'\n/* edit */\n')
        with self.assertRaisesRegex(ValueError,'clean'):rep.prepare(self.repo,self.folder,self.meta)
        self.assertFalse(list(self.folder.glob('session-*')))

    def test_committed_revision_change_prevents_collection(self):
        self.create();self.fresh_boot()
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Software Fixture',
            '-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','Changed source revision'],check=True)
        with self.assertRaisesRegex(ValueError,'revision'):rep.prepare(self.repo,self.folder,self.meta)

    def test_machine_change_prevents_collection(self):
        self.create();self.fresh_boot();self.meta['machine_fingerprint_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'host/configuration'):rep.prepare(self.repo,self.folder,self.meta)

    def test_windows_update_prevents_silent_configuration_change(self):
        self.create();self.fresh_boot();self.meta['environment']['windows_ubr']+=1
        with self.assertRaisesRegex(ValueError,'host/configuration'):rep.prepare(self.repo,self.folder,self.meta)

    def test_hypervisor_change_prevents_silent_configuration_change(self):
        self.create();self.fresh_boot();self.meta['environment']['hypervisor_present']=False
        with self.assertRaisesRegex(ValueError,'audited pilot'):rep.prepare(self.repo,self.folder,self.meta)

    def test_changed_plan_hash_is_rejected(self):
        self.create();p=self.folder/'plan.json';data=rep.read(p);data['seeds'][0]=42;rep.write(p,data)
        with self.assertRaisesRegex(ValueError,'SHA256'):rep.load_plan(self.folder)

    def test_changed_frozen_source_snapshot_is_rejected(self):
        self.create();p=self.folder/'frozen-source'/rep.CORE[0];p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'snapshot changed'):rep.load_plan(self.folder)

    def test_duplicate_seeds_are_rejected_even_with_updated_plan_digest(self):
        self.create();p=self.folder/'plan.json';data=rep.read(p);data['seeds'][1]=data['seeds'][0]
        rep.write(p,data);(self.folder/'plan.sha256').write_text(rep.digest(p.read_bytes()))
        with self.assertRaisesRegex(ValueError,'distinct'):rep.load_plan(self.folder)

    def test_pilot_seed_is_excluded_at_validation(self):
        self.create();p=self.folder/'plan.json';data=rep.read(p);data['seeds'][0]=1143445439
        rep.write(p,data);(self.folder/'plan.sha256').write_text(rep.digest(p.read_bytes()))
        with self.assertRaisesRegex(ValueError,'Exploratory pilot'):rep.load_plan(self.folder)

    def test_positive_fixture_aggregate_never_proves_mechanism_or_paper(self):
        self.create()
        for _ in range(3):self.attempt()
        with patch.object(rep,'analyze_archive',side_effect=lambda p,plan,s,**kw:summary(s)):
            result=rep.audit(self.folder)
        self.assertEqual(result['outcome'],'replicated_k5_numerical_signature_this_host_configuration')
        for field in ['mechanism_proven','fractal_paper_claims_reproduced','user_to_kernel_tested']:
            self.assertFalse(result[field])

    def test_same_boot_cannot_count_as_replication(self):
        self.create()
        for _ in range(3):self.attempt()
        p=self.folder/'session-02/started.json';data=rep.read(p)
        data['host']['boot_utc']=rep.read(self.folder/'session-01/started.json')['host']['boot_utc'];rep.write(p,data)
        with patch.object(rep,'analyze_archive',side_effect=lambda p,plan,s,**kw:summary(s)):
            result=rep.audit(self.folder)
        self.assertEqual(result['outcome'],'inconclusive_protocol_deviation')

    def test_modified_collected_archive_is_retained_but_rejected(self):
        self.create()
        for _ in range(3):self.attempt()
        p=next((self.folder/'session-01/artifacts').glob('*.zip'));p.write_bytes(b'modified')
        with patch.object(rep,'analyze_archive',side_effect=lambda p,plan,s,**kw:summary(s)):
            result=rep.audit(self.folder)
        self.assertEqual(result['outcome'],'inconclusive_invalid_or_missing_evidence')
        self.assertIn('hash changed',result['results'][0]['error'])

    def test_audit_rejects_active_analyzer_that_differs_from_frozen_snapshot(self):
        self.create()
        original=rep.canonical_hash
        altered=ROOT/'scripts/analyze_dependency_receiver.py'
        with patch.object(rep,'canonical_hash',side_effect=lambda p:'f'*64 if p==altered else original(p)):
            with self.assertRaisesRegex(ValueError,'Active validation'):rep.audit(self.folder)

    def test_source_zip_is_never_counted_as_a_second_complete_archive(self):
        self.create()
        for _ in range(3):self.attempt()
        attempt=self.folder/'session-01';end=rep.read(attempt/'finished.json')
        primary=next((attempt/'artifacts').glob('*.zip'))
        source=primary.with_name(primary.stem+'.sources.zip')
        source.write_bytes(b'SOFTWARE SOURCE SNAPSHOT FIXTURE')
        relative=source.relative_to(attempt).as_posix()
        end['artifacts'].append(relative);end['artifact_sha256'][relative]=rep.digest(source.read_bytes())
        rep.write(attempt/'finished.json',end)
        with patch.object(rep,'analyze_archive',side_effect=lambda p,plan,s,**kw:summary(s)) as analyze:
            result=rep.audit(self.folder)
        self.assertEqual(analyze.call_count,3)
        self.assertEqual(result['outcome'],'replicated_k5_numerical_signature_this_host_configuration')

    def test_invalid_zip_cannot_be_promoted_without_test_mock(self):
        self.create()
        for _ in range(3):self.attempt()
        result=rep.audit(self.folder)
        self.assertEqual(result['outcome'],'inconclusive_invalid_or_missing_evidence')
        self.assertEqual(result['validated_runs'],0)

    def test_null_and_mixed_results_are_not_positive_replications(self):
        self.assertEqual(rep.classify([summary(positive=False) for _ in range(3)],[]),
            'no_k5_numerical_signature_in_three_valid_runs')
        self.assertEqual(rep.classify([summary(),summary(),summary(positive=False)],[]),
            'not_consistently_replicated')

    def test_failed_controls_are_not_rescued_by_large_effects(self):
        self.assertEqual(rep.classify([summary(),summary(),summary(controls=False)],[]),
            'inconclusive_failed_controls')

    def test_missing_evidence_and_protocol_deviations_withhold_success(self):
        self.assertEqual(rep.classify([summary(),summary(),{'validated':False}],[]),
            'inconclusive_invalid_or_missing_evidence')
        self.assertEqual(rep.classify([summary() for _ in range(3)],['changed seed']),
            'inconclusive_protocol_deviation')

    def test_package_retains_error_records_and_cannot_overwrite_existing_zip(self):
        self.create();self.attempt(exit_code=7)
        destination=self.repo/'out/fixture-evidence.zip'
        result=rep.package(self.folder,destination)
        self.assertEqual(result['recorded_attempts'],1)
        with zipfile.ZipFile(destination) as z:
            self.assertIn('session-01/finished.json',z.namelist())
            self.assertTrue(any(n.endswith('.zip') for n in z.namelist()))
        with self.assertRaisesRegex(ValueError,'already exists'):rep.package(self.folder,destination)

    def test_unsafe_archive_paths_and_case_collisions_are_rejected(self):
        for names in [['../escape'],['A','a'],['C:/escape']]:
            content=io.BytesIO()
            with zipfile.ZipFile(content,'w') as z:
                for name in names:z.writestr(name,b'fixture')
            with zipfile.ZipFile(io.BytesIO(content.getvalue())) as z:
                with self.assertRaisesRegex(ValueError,'Unsafe'):rep.zip_members(z,1000)


if __name__=='__main__':unittest.main()
