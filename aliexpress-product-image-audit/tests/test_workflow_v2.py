import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from budget_manager import BudgetManager, BudgetExceeded
from job_manager import JobManager
from workflow_runner import run

class ControlTests(unittest.TestCase):
    def test_atomic_budget(self):
        budget = BudgetManager({'ai': 4})
        def attempt(_):
            try:
                budget.reserve('ai')
                return 1
            except BudgetExceeded:
                return 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(40))), 4)
    def test_no_state_skip(self):
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(root)
            job = manager.create(1, 7, {})
            with self.assertRaises(ValueError):
                manager.transition(job['job_id'], 'APPLIED')
    def test_read_only_adapter(self):
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(root)
            job = manager.create(1, 7, {})
            calls = []
            run(manager, job, lambda pid, shop, output_dir: calls.append((pid, shop, output_dir)))
            self.assertEqual(calls[0][:2], (1, 7))
            self.assertTrue((calls[0][2] / 'review.json').exists())
    def test_resume_failed_audit(self):
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(root)
            job = manager.create(1, 7, {})
            def fail(*args, **kwargs):
                raise RuntimeError('offline failure')
            with self.assertRaises(RuntimeError):
                run(manager, job, fail)
            manager.recover(job['job_id'])
            calls = []
            run(manager, manager.load(job['job_id']), lambda *a, **k: calls.append(a))
            self.assertEqual(len(calls), 1)

    def test_modified_binding_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(root)
            job = manager.create(1, 7, {})
            path = manager.directory(job['job_id']) / 'job.json'
            job['pid'] = 2
            path.write_text(json.dumps(job))
            with self.assertRaises(ValueError):
                manager.load(job['job_id'])

class BindingRecoveryTests(unittest.TestCase):
    def test_input_binding_rejects_drift(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root); job=manager.create(1,7,{})
            manager.bind_input(job['job_id'],{'titleEn':'first'})
            manager.bind_input(job['job_id'],{'titleEn':'first'})
            with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):
                manager.bind_input(job['job_id'],{'titleEn':'second'})

    def test_live_lock_preserved(self):
        import json, os
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            lock=Path(root)/'pid_1.lock'
            lock.write_text(json.dumps({'job_id':job['job_id'],'pid':os.getpid()}))
            with self.assertRaises(ValueError): manager.recover(job['job_id'])
            self.assertTrue(lock.exists())

    def test_other_job_lock_preserved(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            lock=Path(root)/'pid_1.lock'
            lock.write_text(json.dumps({'job_id':'JOB_other','pid':999999999}))
            with self.assertRaises(ValueError): manager.recover(job['job_id'])
            self.assertTrue(lock.exists())

class OfflineEndToEndTests(unittest.TestCase):
    def test_complete_and_resume_without_side_effects(self):
        import json
        from pathlib import Path
        from job_manager import atomic_json
        from plan_v2 import validate_plan
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root); job=manager.create(123,7,{'ai_requests':0,'full_resolution_images':0})
            calls=[]
            def audit(pid,shop,output_dir):
                calls.append((pid,shop))
                atomic_json(output_dir/'audit_product.json',{'titleEn':'Offline fixture','images':{'main':[]}})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True,'image_errors':0},'anomalies':[]})
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':[]})
                atomic_json(output_dir/'run_metrics.json',{'elapsed_seconds':0.1})
            run(manager,job,audit)
            directory=manager.directory(job['job_id'])
            self.assertEqual(json.loads((directory/'state.json').read_text())['state'],'PLAN_READY')
            review=json.loads((directory/'review.json').read_text())
            metrics=json.loads((directory/'run_metrics.json').read_text())
            self.assertEqual(review['status'],'READ_ONLY_COMPLETE')
            self.assertEqual(metrics['ai']['requests'],0)
            self.assertEqual(metrics['executor']['site_save_calls'],0)
            self.assertFalse((directory/'dry_run.json').exists())
            validate_plan(json.loads((directory/'plan.v2.json').read_text()))
            report=(directory/'report.md').read_text(encoding='utf-8')
            self.assertIn('123',report)
            before={p.name:p.read_bytes() for p in directory.iterdir() if p.is_file()}
            manager.recover(job['job_id'])
            result=run(manager,manager.load(job['job_id']),audit)
            self.assertEqual(result,review)
            self.assertEqual(len(calls),1)
            self.assertEqual(before,{p.name:p.read_bytes() for p in directory.iterdir() if p.is_file()})
