import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from mye_c_automation.full_product_audit import build_inventory, build_queue, assemble_report
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.product_state import canonical_state_hash
import test_full_product_audit as fixture_module


class RecoveryTests(unittest.TestCase):
    def setup_parent(self, temp):
        helper=fixture_module.FullProductAuditTests();product,raw=helper.fixture(temp)
        manager=JobManager(Path(temp)/'jobs')
        job=manager.create(1,7,{'ai_requests':40,'total_tokens':500000},mode='audit')
        manager.bind_account(job['job_id'],'a'*64);job=manager.bind_input(job['job_id'],product)
        root=manager.directory(job['job_id']);inv=build_inventory(product,raw)
        queue=build_queue(product,inv,root);results=helper.decisions(inv)
        for item in queue['items']:
            for row in results[item['id']]['results']:
                row.update(task_type=item['task_type'],item_id=item['id'])
                if item['task_type']=='watermark':row.update(owner='factory',location='bottom')
                if item['task_type']=='sku_match':row.update(sku_id=item['sku_id'],image_id=item['image_id'])
        for key in results:
            if key.startswith('WM_'):
                for row in results[key]['results']:row['confidence']=.79
        atomic_json(root/'audit_product.json',product);atomic_json(root/'audit_raw.json',{'images':raw})
        atomic_json(root/'full_inventory.json',inv);atomic_json(root/'full_ai_queue.json',queue)
        atomic_json(root/'full_ai_judgements.json',results)
        atomic_json(root/'full_ai_metrics.json',{'requests':1,'usage_available':False,'calls':[{'called':True,'usage_status':'UNKNOWN','total_tokens':None}]})
        atomic_json(root/'full_audit_report.json',assemble_report(product,inv,results,[]))
        (root/'budget.sqlite').write_bytes(b'original frozen budget')
        config={'schema':'model-gateway/v1','base_url':'http://127.0.0.1:8788/v1','models':['a','b'],'max_output_tokens':8192,'retries':0,'timeout':150}
        auth={'schema':'read-only-audit-recovery-proposal/v1','enabled':True,'parent_job_id':job['job_id'],
              'shop':7,'pid':1,'source_state_sha256':canonical_state_hash(product),'model_config':config,
              'supplemental_phase_limits':{'ai_requests':28,'total_tokens':500000,'site_save':0,'upload':0,'translate_title':0,'delete':0,'status':0}}
        class Reader:
            def current_shop(self):return 7
            def account_fingerprint(self):return 'a'*64
            def product(self,pid):return deepcopy(product)
            def save(self,*args):raise AssertionError('no writer allowed')
        return root,auth,Reader(),helper.decisions(inv),product

    def test_select_only_unresolved_pairs_and_never_drop_sku_positions(self):
        from mye_c_automation.full_audit_recovery import select_pending
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp)
            read=lambda n:json.loads((root/n).read_text())
            queue=select_pending(product,read('full_inventory.json'),read('full_ai_queue.json'),read('full_ai_judgements.json'))
            self.assertEqual(len(queue['items']),2)
            self.assertTrue(all(v['task_type']=='watermark' for v in queue['items']))

    def test_disabled_authorization_does_not_create_phase_or_call_models(self):
        from mye_c_automation.full_audit_recovery import recover
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp);auth['enabled']=False
            with patch('mye_c_automation.full_audit_recovery.JudgeClient') as judge:
                with self.assertRaisesRegex(ValueError,'AUTHORIZATION'):recover(root,auth,reader)
                judge.assert_not_called()
            self.assertFalse((root/'recovery_8788_1').exists())

    def test_state_drift_blocks_before_inference(self):
        from mye_c_automation.full_audit_recovery import recover
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp);product['title']='changed'
            with patch('mye_c_automation.full_audit_recovery.JudgeClient') as judge:
                with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):recover(root,auth,reader)
                judge.assert_not_called()

    def test_changed_account_blocks_before_inference(self):
        from mye_c_automation.full_audit_recovery import recover
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp)
            reader.account_fingerprint=lambda:'b'*64
            with patch('mye_c_automation.full_audit_recovery.JudgeClient') as judge:
                with self.assertRaisesRegex(ValueError,'ACCOUNT_MISMATCH'):recover(root,auth,reader)
                judge.assert_not_called()

    def test_remote_content_drift_blocks_before_inference(self):
        from mye_c_automation.full_audit_recovery import recover
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp)
            with patch('mye_c_automation.full_audit_recovery.download_unique',return_value={}),patch('mye_c_automation.full_audit_recovery.JudgeClient') as judge:
                with self.assertRaisesRegex(ValueError,'REMOTE_IMAGE_SOURCE_CHANGED'):recover(root,auth,reader)
                judge.assert_not_called()

    def test_fake_recovery_preserves_parent_budget_and_unknown_total(self):
        from mye_c_automation.full_audit_recovery import recover
        with tempfile.TemporaryDirectory() as temp:
            root,auth,reader,expected,product=self.setup_parent(temp)
            before=(root/'budget.sqlite').read_bytes()
            class FakeJudge:
                models=('a','b')
                metrics={'requests':0,'total_tokens':0,'usage_available':True,'calls':[]}
                def classify(self,task,item,context):return deepcopy(expected[item['id']])
            inv=json.loads((root/'full_inventory.json').read_text())
            def downloads(urls,directory,**kwargs):
                return {url:{'path':Path(content['file'])} for content in inv['contents'].values() for url in content['urls']}
            with patch('mye_c_automation.full_audit_recovery.download_unique',side_effect=downloads):
                report=recover(root,auth,reader,judge_factory=lambda *a,**kw:FakeJudge())
            self.assertTrue(report['audit_complete'])
            self.assertEqual(report['image_and_reference_count'],7)
            self.assertIsNone(report['combined_token_accounting']['total_tokens'])
            self.assertEqual(report['combined_token_accounting']['token_status'],'UNKNOWN')
            self.assertEqual((root/'budget.sqlite').read_bytes(),before)
            self.assertEqual(report['site_save_calls'],0)
            with self.assertRaisesRegex(ValueError,'ALREADY_STARTED'):recover(root,auth,reader)

    def test_human_labels_are_exact_sha_scoped_and_do_not_set_verdicts(self):
        from mye_c_automation.full_audit_recovery import add_source_labels
        queue={'items':[{'id':'x','task_type':'watermark','sha256':'a'*64,'purpose':'pixels'}]}
        registry={'samples':[{'source_sha256':'a'*64,'ground_truth':{'third_party_watermark':False},
            'confirmations':[{'sample_id':'R01','label_status':'USER_CONFIRMED','ground_truth':{'third_party_watermark':False}}]},
            {'source_sha256':'b'*64,'ground_truth':{'third_party_watermark':True},'confirmations':[]}]}
        enriched,proof=add_source_labels(queue,registry)
        self.assertIn('false',enriched['items'][0]['purpose'])
        self.assertEqual(proof[0]['source_sha256'],'a'*64)
        self.assertNotIn('verdict',enriched['items'][0])
        registry['samples'][0]['confirmations'][0]['label_status']='MODEL_PREDICTED'
        unchanged,proof=add_source_labels(queue,registry)
        self.assertEqual(unchanged,queue);self.assertFalse(proof)
