import copy
import tempfile
import unittest
from pathlib import Path
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.resources import resource_path
import json


def policy():
    value=json.loads(resource_path('config/automation.v2.example.json').read_text())
    value.update(enabled=True,pid_allowlist=[1],trim_seven_main_before_audit=True)
    return AutomationPolicy(value)


class MainPreflightTests(unittest.TestCase):
    def test_seven_trim_saves_then_independent_readback_and_preserves_other_fields(self):
        from mye_c_automation.workflow_runner import run_main_count_preflight
        from mye_c_automation.job_manager import JobManager
        from mye_c_automation.execution_ledger import ExecutionLedger
        from mye_c_automation.product_state import canonical_state_hash
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);urls=['https://fake/'+str(n) for n in range(7)]
            original=dict(id=1,images=dict(main=urls,detail=urls[:2],sku=urls[:1],ai=[],scene=[],gallery=[],attachList=[]),
                skus=[dict(skuId='A',skuName='With Box',skuImageUrl=urls[0],price=10,originalBox=True)],
                descriptionJson={'opaque':'unchanged'},price=10,weight=.2,presale=True,status='READY_TO_PUBLISH')
            events=[]
            class Writer:
                def __init__(self):self.value=copy.deepcopy(original);self.saves=0
                def product(self,pid):return copy.deepcopy(self.value)
                def account_fingerprint(self):return 'a'*64
                def current_shop(self):return 7
                def save(self,pid,product,*,expected_state_sha256,**kwargs):
                    if canonical_state_hash(self.value)!=expected_state_sha256:raise ValueError('STATE_DRIFT')
                    self.saves+=1;events.append('save');self.value=copy.deepcopy(product)
            writer=Writer()
            class Independent:
                def product(self,pid):events.append('independent_readback');return writer.product(pid)
                def account_fingerprint(self):return 'a'*64
                def current_shop(self):return 7
            ledger=ExecutionLedger(root/'execution.sqlite')
            try:
                manager=JobManager(root/'jobs')
                result=run_main_count_preflight(manager,1,7,policy(),writer,lambda:Independent(),execution_ledger=ledger)
                self.assertEqual(result['status'],'AUTO_VERIFIED')
                self.assertEqual(result['model_requests'],0)
                self.assertEqual(events,['save','independent_readback'])
                expected=copy.deepcopy(original);expected['images']['main']=urls[1:]
                self.assertEqual(writer.value,expected)
                self.assertEqual(writer.saves,1)
                again=run_main_count_preflight(manager,1,7,policy(),writer,lambda:Independent(),execution_ledger=ledger)
                self.assertEqual(again['status'],'NOT_NEEDED');self.assertEqual(writer.saves,1)
            finally:ledger.close()

    def test_count_other_than_exact_seven_does_not_write(self):
        from mye_c_automation.workflow_runner import run_main_count_preflight
        from mye_c_automation.job_manager import JobManager
        with tempfile.TemporaryDirectory() as tmp:
            class Writer:
                count=6
                def product(self,pid):return {'id':pid,'images':{'main':['https://x/'+str(n) for n in range(self.count)]}}
                def save(self,*a,**k):raise AssertionError('unexpected write')
                def account_fingerprint(self):return 'a'*64
                def current_shop(self):return 7
            writer=Writer()
            for count in (6,8):
                writer.count=count
                result=run_main_count_preflight(JobManager(Path(tmp)/'jobs'),1,7,policy(),writer,lambda:None)
                self.assertEqual(result['status'],'NOT_NEEDED')


class SellerPosterTests(unittest.TestCase):
    def row(self):
        from test_v2_vision import observation
        return observation(dict(id='A',sha256='a'*64,image_type='DETAIL',evidence_ids=['A']),decision='REVIEW',visual_class='DECORATED_COMPOSITE',
            watermarks=[dict(kind='STORE_WATERMARK',bbox=[.17,.925,.65,.995],confidence=.1,preserve_overlap_risk='LOW',owner='UNKNOWN',overlay_role='ADDED_WATERMARK'),
                dict(kind='PROMOTIONAL_TEXT',bbox=[.66,.925,.99,.995],confidence=.1,preserve_overlap_risk='LOW',owner='UNKNOWN',overlay_role='SELLER_NOTICE'),
                dict(kind='STORE_WATERMARK',bbox=[.1,.2,.4,.3],confidence=.1,preserve_overlap_risk='HIGH',owner='UNKNOWN',overlay_role='ADDED_WATERMARK'),
                dict(kind='STORE_WATERMARK',bbox=[.5,.5,.8,.6],confidence=.1,preserve_overlap_risk='MEDIUM',owner='UNKNOWN',overlay_role='ADDED_WATERMARK')])

    def test_explicit_shop_poster_deletes_without_rewriting_raw_review(self):
        from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules
        raw=self.row();before=copy.deepcopy(raw);adjusted,changes=apply_visual_rules(raw)
        self.assertEqual(raw,before);self.assertEqual(adjusted['decision'],'DELETE')
        self.assertEqual(changes[0]['raw_decision'],'REVIEW')
        self.assertEqual(changes[0]['rule'],'SELLER_PROMOTIONAL_COMPOSITE')

    def test_ordinary_photo_official_marks_and_explicit_abstention_are_not_deleted(self):
        from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules
        photo=self.row();photo['visual_class']='TOY_PRODUCT'
        abstain=self.row();abstain['abstain']=True
        official=self.row()
        for mark in official['watermarks']:mark['owner']='MANUFACTURER'
        badge=self.row();badge['watermarks']=badge['watermarks'][:1]
        for value in (photo,abstain,official,badge):
            with self.subTest(value=value):self.assertEqual(apply_visual_rules(value)[0]['decision'],'REVIEW')
