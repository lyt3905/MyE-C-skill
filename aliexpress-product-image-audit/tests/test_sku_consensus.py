import json,tempfile,unittest
from copy import deepcopy
from ai_judge import JudgeClient
from budget_manager import BudgetManager
from full_product_audit import _sku

class SkuConsensusTests(unittest.TestCase):
    def classify(self,changes=None,decision='MATCH',both=False):
        base=dict(task_type='sku_match',item_id='SKU_ROW_001',sku_id='SKU_ROW_001',image_id='SKU_ROW_001',
                  decision=decision,confidence=.95,abstain=False,evidence_ids=['SKU_ROW_001'],
                  image_type='box',sku_packaging='with_box',shared_across_skus=False,missing_image=False)
        rows=[dict(base,**(changes or {})) if both else deepcopy(base),dict(base,**(changes or {}))]
        item=dict(id='SKU_ROW_001',task_type='sku_match',sku_id='SKU_ROW_001',image_id='SKU_ROW_001',
                  evidence_ids=['SKU_ROW_001'],sku_name='with retail box',shared_across_skus=False)
        with tempfile.TemporaryDirectory() as tmp:
            budget=BudgetManager({'ai_requests':2})
            def send(model,item,context):return {'choices':[{'message':{'content':json.dumps(rows[0 if model=='a' else 1])}}],
                                               'usage':{'prompt_tokens':90,'completion_tokens':10,'total_tokens':100}}
            try:return JudgeClient(budget,tmp,transport=send,models=('a','b'),retries=0).classify('sku_match',item,{})
            finally:budget.close()

    def test_actual_canary_box_mixed_disagreement_is_review(self):
        result=self.classify({'image_type':'mixed'})
        self.assertEqual(result['status'],'REVIEW')
        self.assertEqual(_sku(result,'with retail box',False),'UNKNOWN')
        self.assertEqual([r['image_type'] for r in result['results']],['box','mixed'])

    def test_packaging_and_boolean_disagreements_are_review(self):
        for field,value in [('sku_packaging','without_box'),('shared_across_skus',True),('missing_image',True)]:
            with self.subTest(field=field):self.assertEqual(self.classify({field:value})['status'],'REVIEW')

    def test_incomplete_or_explicit_unknown_observations_are_review(self):
        for field,value in [('image_type',None),('image_type','unknown'),('sku_packaging',None),('sku_packaging','unknown')]:
            with self.subTest(field=field):
                self.assertEqual(self.classify({field:value})['status'],'REVIEW')
                self.assertEqual(self.classify({field:value},both=True)['status'],'REVIEW')

    def test_consistent_complete_results_remain_usable(self):
        result=self.classify()
        self.assertEqual(result['status'],'CLEAN')
        self.assertEqual(_sku(result,'with retail box',False),'PASS')
        self.assertEqual(self.classify(decision='MISMATCH')['status'],'HIT')

if __name__=='__main__':unittest.main()
