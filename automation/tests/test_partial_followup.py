import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from mye_c_automation.execution_ledger import ExecutionLedger,operation_digest
from mye_c_automation.product_state import canonical_state_hash
from mye_c_automation.plan_v2 import plan_hash

class PartialFollowupTests(unittest.TestCase):
    def proof(self,root):
        from mye_c_automation.workflow_runner import validate_partial_followup
        product={'id':1,'images':{'main':['https://fake/retained']},'skus':[],'descriptionJson':None,'price':10}
        plan={'job_id':'JOB_old','pid':1,'shop':7,'desired':{'images':product['images']},'post_actions':{}}
        # plan_hash uses the same canonical JSON contract as ordinary plans.
        docs={'job.json':{'job_id':'JOB_old','pid':1,'shop_id':7,'account_fingerprint':'account'},'plan.v2.json':plan,'expected_after.json':product,'independent_after.json':product,
            'apply_receipt.json':{'job_id':'JOB_old','account_fingerprint':'account','plan_sha256':plan_hash(plan),'verification_ok':True,'apply_status':'APPLY_MATCHED','site_save_calls':1,'dry_run':False},
            'full_inventory.json':{'occurrences':[{'url':'https://fake/missing','sha256':None}]},
            'content_validation.json':{'ok':False,'structure':{'ok':True},'description_exact':True,'protected_fields_exact':True,'sku_references_exact':True,'items':[{'ok':True}],
                'image_readback':[{'url':'https://fake/missing','ok':False,'expected_sha256':None}]}}
        for name,v in docs.items():(root/name).write_text(json.dumps(v),encoding='utf-8')
        path=root/'followup-proof.json';path.write_text(json.dumps({'schema':'partial-write-followup/v1','evidence_root':str(root),'source_directory':str(root),'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in docs}}))
        return path,canonical_state_hash(product)

    def test_known_applied_partial_can_start_new_operation_without_forging_old_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proof,before=self.proof(root);ledger=ExecutionLedger(root/'ledger.sqlite')
            try:
                ledger.claim('account',7,1,'JOB_old','old-before',operation_digest(json.loads((root/'plan.v2.json').read_text())));ledger.finish('account',7,1,'JOB_old','CONTENT_REVIEW_REQUIRED')
                self.assertFalse(ledger.claim('account',7,1,'JOB_new',before,'new-operation')['ok'])
                result=ledger.claim_followup('account',7,1,'JOB_new',before,'new-operation',proof_path=proof,authorization_id='new-scoped-authorization')
                self.assertTrue(result['ok']);self.assertEqual(ledger.state('account',7,1,'JOB_new'),'RESERVED')
                archived=ledger.db.execute('SELECT state FROM execution_followups').fetchall();self.assertEqual(archived,[('CONTENT_REVIEW_REQUIRED',)])
                self.assertFalse(ledger.claim_followup('account',7,1,'JOB_third',before,'third',proof_path=proof,authorization_id='new')['ok'])
            finally:ledger.close()

    def test_unknown_save_and_wrong_context_still_block(self):
        for state in ('APPLY_UNKNOWN','RESERVED'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);proof,before=self.proof(root);ledger=ExecutionLedger(root/'ledger.sqlite')
                try:
                    ledger.claim('account',7,1,'JOB_old','old','old-operation')
                    if state=='APPLY_UNKNOWN':ledger.begin_side_effect('account',7,1,'JOB_old')
                    self.assertFalse(ledger.claim_followup('account',7,1,'JOB_new',before,'new',proof_path=proof,authorization_id='new')['ok'])
                finally:ledger.close()

    def test_known_byte_failure_or_changed_fields_cannot_be_acknowledged(self):
        from mye_c_automation.workflow_runner import validate_partial_followup
        for target,change in (('content_validation.json',lambda v:v['image_readback'][0].update(expected_sha256='a'*64)),('independent_after.json',lambda v:v.update(price=99)),('apply_receipt.json',lambda v:v.update(apply_status='APPLY_UNKNOWN'))):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);proof,_=self.proof(root);v=json.loads((root/target).read_text());change(v);(root/target).write_text(json.dumps(v))
                # Even rebinding the file hash must not turn bad evidence into permission.
                p=json.loads(proof.read_text());p['files'][target]=hashlib.sha256((root/target).read_bytes()).hexdigest();proof.write_text(json.dumps(p))
                with self.assertRaises(ValueError):validate_partial_followup(proof)

    def test_new_authorization_exact_current_state_and_different_operation_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proof,before=self.proof(root);ledger=ExecutionLedger(root/'ledger.sqlite');old=operation_digest(json.loads((root/'plan.v2.json').read_text()))
            try:
                ledger.claim('account',7,1,'JOB_old','old-before',old);ledger.finish('account',7,1,'JOB_old','CONTENT_REVIEW_REQUIRED')
                for account,state,operation,authorization in (('other',before,'new','yes'),('account','drift','new','yes'),('account',before,old,'yes'),('account',before,'new','')):
                    with self.subTest(account=account,state=state,operation=operation),self.assertRaises(ValueError):ledger.claim_followup(account,7,1,'JOB_new',state,operation,proof_path=proof,authorization_id=authorization)
                self.assertEqual(ledger.state('account',7,1,'JOB_old'),'CONTENT_REVIEW_REQUIRED')
            finally:ledger.close()

    def test_readonly_reconciliation_preserves_entire_previous_fake_job(self):
        from test_v2_workflow import V2WorkflowTests
        from mye_c_automation.workflow_runner import prepare_partial_followup,validate_partial_followup
        def missing(p,assets,urls):p['images']['detail'].append('https://fake/missing')
        with tempfile.TemporaryDirectory() as tmp:
            s=V2WorkflowTests.scenario(self,tmp,['DELETE','KEEP'],product_transform=missing)
            source=s['root'];before={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()};saves=s['writer'].saves
            proof=prepare_partial_followup(source,Path(tmp)/'independent-followup',s['writer'])
            self.assertEqual(validate_partial_followup(proof)['unread_reference_count'],1)
            self.assertEqual(s['writer'].saves,saves)
            self.assertEqual(before,{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()})
