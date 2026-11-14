from watermark_fixtures import exhaustive
"""Fusion status must not call a policy-review watermark class clean."""
import json
import tempfile
import unittest

from ai_judge import JudgeClient
from budget_manager import BudgetManager
from policy_engine import POLICY, evaluate


class ModelPolicyAlignmentTests(unittest.TestCase):
    def test_review_only_classes_stay_review_even_with_high_model_agreement(self):
        for classification,disposition in POLICY['watermark'].items():
            if disposition!='NEEDS_REVIEW':continue
            with self.subTest(classification=classification),tempfile.TemporaryDirectory() as root:
                def send(model,item,context):
                    result={'task_type':'watermark','item_id':item['id'],'classification':classification,
                        'owner':'store','location':'bottom','confidence':.99,'abstain':False,'evidence_ids':item['evidence_ids']}
                    return {'choices':[{'message':{'content':json.dumps(result)}}],
                        'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
                budget=BudgetManager({'ai_requests':2})
                try:
                    client=JudgeClient(budget,root,transport=send,retries=0)
                    result=client.classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{})
                    self.assertEqual(result['status'],'REVIEW',result)
                    self.assertEqual(evaluate(result),'NEEDS_REVIEW')
                finally:budget.close()

    def test_captured_4083_poster_is_reviewed_without_policy_changes(self):
        # Captured classifications/confidence; identifiers rebound per request.
        outputs=[{'task_type':'watermark','classification':'chinese_promotion_poster','owner':owner,
            'location':'bottom promotional banner','confidence':.9,'abstain':False}
            for owner in ('third-party seller/store','third_party_store')]
        with tempfile.TemporaryDirectory() as root:
            def send(model,item,context):
                output=dict(outputs[0 if model=='m1' else 1],item_id=item['id'],evidence_ids=item['evidence_ids'])
                return {'choices':[{'message':{'content':json.dumps(exhaustive(output))}}]}
            budget=BudgetManager({'ai_requests':2})
            try:
                result=JudgeClient(budget,root,models=('m1','m2'),transport=send,retries=0).classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{})
                self.assertEqual(result['status'],'REVIEW')
                self.assertEqual(evaluate(result),'NEEDS_REVIEW')
            finally:budget.close()

    def test_fusion_status_preserves_every_existing_policy_disposition(self):
        for classification,disposition in POLICY['watermark'].items():
            with self.subTest(classification=classification),tempfile.TemporaryDirectory() as root:
                def send(model,item,context):
                    output={'task_type':'watermark','item_id':item['id'],'classification':classification,
                        'owner':'known owner','location':'center','confidence':.99,'abstain':False,'evidence_ids':item['evidence_ids']}
                    return {'choices':[{'message':{'content':json.dumps(exhaustive(output))}}]}
                budget=BudgetManager({'ai_requests':2})
                try:
                    result=JudgeClient(budget,root,transport=send,retries=0).classify('watermark',{'id':'A','evidence_ids':['A'],'dimensions':[800,800]},{})
                    self.assertEqual(evaluate(result),disposition)
                    self.assertEqual(result['status'],{'KEEP':'CLEAN','REMOVE_CANDIDATE':'HIT','NEEDS_REVIEW':'REVIEW'}[disposition])
                finally:budget.close()


if __name__=='__main__':unittest.main()
