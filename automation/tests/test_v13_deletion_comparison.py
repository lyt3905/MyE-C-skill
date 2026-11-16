import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.visual_quality import VisualQualityInspector
from mye_c_automation.auto_deletions import plan_deletion


class DeletionComparisonTests(unittest.TestCase):
    def test_legacy_explicit_reference_review_does_not_require_new_comparison_argument(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';reference=root/'reference.png'
            Image.new('RGB',(800,800),'blue').save(source);reference.write_bytes(source.read_bytes())
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            product={'images':{'main':['https://fake/source','https://fake/reference'],'detail':['https://fake/detail'],'sku':[]}}
            raw=[{'kind':'main','index':0,'url':'https://fake/source','file':str(source)},
                 {'kind':'main','index':1,'url':'https://fake/reference','file':str(reference)}]
            item={'id':'LEGACY','image_id':'MAIN_000','pool':'main','index':0,'local':str(source),
                  'source_url':'https://fake/source','source_sha256':digest,'evidence_ids':['LEGACY']}
            class LegacyInspector:
                def inspect_deletion(self,path,context):return {'ok':True,'is_box':False,'is_official':False,
                    'category':'REDUNDANT','information_preserved':True,'reference_url':'https://fake/reference','evidence_ids':['LEGACY_REVIEW']}
            self.assertIsNotNone(plan_deletion(root,item,product,raw,LegacyInspector()))

    def exercise(self,root,box_disagreement=False):
        root=Path(root);source=root/'source.png';reference=root/'reference.png'
        Image.new('RGB',(800,800),'blue').save(source);reference.write_bytes(source.read_bytes())
        seen=[];budget=BudgetManager({'ai_requests':8,'full_resolution_images':2})
        def transport(model,item,context):
            seen.append(item)
            result={'task_type':'deletion_quality','item_id':item['id'],'decision':'MATCH','confidence':.99,'abstain':False,
                    'evidence_ids':item['evidence_ids'],'is_box':box_disagreement and model=='kimi','is_official':False,
                    'category':'REDUNDANT','information_preserved':True}
            return {'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},'choices':[{'message':{'content':json.dumps(result)}}]}
        judge=JudgeClient(budget,root/'cache',models=('glm','kimi'),transport=transport,retries=0)
        inspector=VisualQualityInspector(root,{'shop_id':7,'budget':{}},judge=judge)
        return inspector,source,reference,seen,budget

    def test_real_inspector_binds_retained_full_image_for_both_model_judgements(self):
        with tempfile.TemporaryDirectory() as temp:
            inspector,source,reference,seen,budget=self.exercise(temp)
            try:
                result=inspector.inspect_deletion(source,{},comparison=reference)
                self.assertTrue(result['ok'])
                digest=hashlib.sha256(reference.read_bytes()).hexdigest()
                self.assertEqual(result['reference_sha256'],digest)
                self.assertEqual(len(seen),2)
                for item in seen:
                    self.assertEqual(item['purpose'],'EXACT_DUPLICATE_WITH_RETAINED_REFERENCE')
                    self.assertEqual(item['extra_images'][0]['sha256'],digest)
                    self.assertIn('RETAINED_REFERENCE',item['evidence_ids'])
            finally:budget.close()

    def test_box_semantic_disagreement_cannot_be_a_passed_deletion_review(self):
        with tempfile.TemporaryDirectory() as temp:
            inspector,source,reference,_,budget=self.exercise(temp,box_disagreement=True)
            try:self.assertFalse(inspector.inspect_deletion(source,{},comparison=reference)['ok'])
            finally:budget.close()

    def test_comparison_and_single_image_review_keep_distinct_evidence_records(self):
        with tempfile.TemporaryDirectory() as temp:
            inspector,source,reference,_,budget=self.exercise(temp)
            try:
                compared=inspector.inspect_deletion(source,{},comparison=reference)
                plain=inspector.inspect_deletion(source,{})
                self.assertTrue(compared['ok']);self.assertFalse(plain['ok'])
                self.assertEqual(len(list((Path(temp)/'quality_evidence').glob('*.json'))),2)
                self.assertNotEqual(compared['evidence_ids'][0],plain['evidence_ids'][0])
            finally:budget.close()
