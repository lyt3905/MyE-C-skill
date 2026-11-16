import hashlib,json,tempfile,unittest
from pathlib import Path
from mye_c_automation.job_manager import JobManager,atomic_json
from mye_c_automation.execution_ledger import ExecutionLedger,operation_digest
from mye_c_automation.plan_v2 import plan_hash


class RejectedUploadFollowupTests(unittest.TestCase):
    def fixture(self,root):
        manager=JobManager(Path(root)/'jobs')
        job=manager.create(1,7,{},mode='auto_apply',image_workflow='v2')
        job=manager.bind_account(job['job_id'],'a'*64)
        product={'id':1,'images':{'main':['https://fake/a'],'detail':['https://fake/b'],'sku':[]}}
        job=manager.bind_input(job['job_id'],product);source=manager.directory(job['job_id'])
        plan=dict(schema='token-opt-plan/v3',job_id=job['job_id'],pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':job['input_state_sha256'],'account_fingerprint':'a'*64},evidence_refs=[],ai_judgement_refs=[],desired={'images':product['images']},post_actions={'uploads':[dict(path='asset.png',sha256='b'*64,pool='main',index=0)]},review={'status':'RESOLVED'},automation={'policy_sha256':'c'*64,'actions':['REMOVE_TEXT']})
        atomic_json(source/'plan.v2.json',plan);atomic_json(source/'audit_product.json',product)
        atomic_json(source/'local_execution.json',dict(confirmed=True,job_id=job['job_id'],pid=1,shop=7,plan_sha256=plan_hash(plan),state='APPLY_UNKNOWN',error='RuntimeError'))
        atomic_json(source/'upload_receipts.json',dict(schema='upload-receipts/v1',job_id=job['job_id'],pid=1,shop=7,state='UPLOAD_UNKNOWN',upload_calls=1,uploads=[],error='HTTPError: HTTP Error 400: '))
        ledger=ExecutionLedger(Path(root)/'ledger.sqlite');self.addCleanup(ledger.close)
        ledger.claim('a'*64,7,1,job['job_id'],job['input_state_sha256'],operation_digest(plan));ledger.begin_side_effect('a'*64,7,1,job['job_id'])
        args=dict(account='a'*64,shop=7,pid=1,job='JOB_new',before_hash=job['input_state_sha256'],operation=operation_digest(plan),source_directory=source,proof_path=Path(root)/'proof.json',authorization_id='EXPLICIT_NEW_COMPLETION')
        return ledger,args,source

    def test_rejected_upload_claims_fresh_job_and_preserves_old_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            ledger,args,source=self.fixture(root)
            before={p.name:p.read_bytes() for p in source.iterdir() if p.is_file()}
            self.assertTrue(ledger.claim_after_rejected_upload(**args)['ok'])
            self.assertEqual(ledger.state('a'*64,7,1,'JOB_new'),'RESERVED')
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir() if p.is_file()})
            self.assertEqual(ledger.db.execute('SELECT state FROM execution_rejected_upload_followups').fetchone()[0],'APPLY_UNKNOWN')
            self.assertFalse(ledger.claim_after_rejected_upload(**dict(args,job='JOB_another'))['ok'])
            ledger.close()

    def test_any_save_stage_evidence_blocks_continuation(self):
        for name in ('save_attempt.json','expected_after.json','apply_receipt.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as root:
                ledger,args,source=self.fixture(root);atomic_json(source/name,{})
                with self.assertRaisesRegex(ValueError,'SAVE_STAGE'):ledger.claim_after_rejected_upload(**args)
                ledger.close()

    def test_timeout_or_successful_upload_is_not_reclassified(self):
        for change in ({'error':'TimeoutError: timed out'},{'uploads':[{'url':'https://fake/upload'}]},{'upload_calls':2}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                ledger,args,source=self.fixture(root);p=source/'upload_receipts.json';v=json.loads(p.read_text());atomic_json(p,dict(v,**change))
                with self.assertRaisesRegex(ValueError,'REJECTED_FIRST_UPLOAD'):ledger.claim_after_rejected_upload(**args)
                ledger.close()

    def test_current_drift_account_and_authorization_block(self):
        for change in ({'before_hash':'d'*64},{'account':'e'*64},{'authorization_id':''}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                ledger,args,_=self.fixture(root)
                with self.assertRaises(ValueError):ledger.claim_after_rejected_upload(**dict(args,**change))
                ledger.close()

    def test_changed_plan_journal_binding_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            ledger,args,source=self.fixture(root);p=source/'local_execution.json';v=json.loads(p.read_text());atomic_json(p,dict(v,plan_sha256='f'*64))
            with self.assertRaisesRegex(ValueError,'BINDING'):ledger.claim_after_rejected_upload(**args)
            ledger.close()

    def test_proof_rechecks_source_and_save_stage_before_side_effect(self):
        from mye_c_automation.execution_ledger import verify_rejected_upload_proof
        with tempfile.TemporaryDirectory() as root:
            ledger,args,source=self.fixture(root)
            ledger.claim_after_rejected_upload(**args)
            self.assertEqual(verify_rejected_upload_proof(args['proof_path'])['next_job'],'JOB_new')
            atomic_json(source/'save_attempt.json',{})
            with self.assertRaisesRegex(ValueError,'SAVE_STAGE'):verify_rejected_upload_proof(args['proof_path'])
            ledger.close()
