import tempfile
import unittest
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG,remedy
from mye_c_automation.plan_compiler import compile_auto_plan
from mye_c_automation.final_state import simulate_final_snapshot
import json

class SemanticCompilerTests(unittest.TestCase):
    def fixture(self,root):
        manager=JobManager(root);job=manager.create(1,7,{})
        path=manager.directory(job['job_id'])
        product={'id':1,'shopId':7,'title':'NA-H74 威震天','titleEn':'Old','identityJson':{'logoCode':'keep'},'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':['https://x/a']},'skus':[{'skuId':1,'skuImageUrl':'https://x/a','price':10}]}
        atomic_json(path/'audit_product.json',product)
        policy=AutomationPolicy(dict(CONFIG,allow_actions=dict(CONFIG['allow_actions'],SKU_ASSIGN=True,TITLE_REWRITE=True)))
        return job,path,product,policy
    def test_sku_mapping_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as root:
            job,path,product,policy=self.fixture(root)
            row=remedy();row.update(action='SKU_ASSIGN',target={'sku_ids':['1']},assignments={'1':'https://x/b'})
            row['checks'].update(sku_assignment_unique=True,packaging_match=True,model_match=True)
            from auto_test_evidence import bind_semantic
            bind_semantic(path,product,row)
            result=compile_auto_plan(path,job,[row],policy)
            self.assertTrue(result['ok'],result)
            after=simulate_final_snapshot(product,json.loads((path/'plan.v2.json').read_text()))
            self.assertEqual(after['skus'][0],{'skuId':1,'skuImageUrl':'https://x/b','price':10})
            self.assertIn('https://x/b',after['images']['sku'])
    def test_title_model_is_authorized_and_logo_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            job,path,product,policy=self.fixture(root)
            row=remedy();row.update(action='TITLE_REWRITE',target={'field':'titleEn'},titleEn='Hot Sale Transformation NA-H74 NAH74 Megatank Action Figures Collection Gifts',modelCode='NA-H74')
            row['checks'].update(title_rules_pass=True,field_provenance=True,translation_once_policy=True)
            from auto_test_evidence import bind_semantic
            bind_semantic(path,product,row)
            result=compile_auto_plan(path,job,[row],policy)
            self.assertTrue(result['ok'],result)
            plan=json.loads((path/'plan.v2.json').read_text())
            self.assertTrue(plan['post_actions']['translate_title'])
            after=simulate_final_snapshot(product,plan)
            self.assertEqual(json.loads(after['identityJson']),{'logoCode':'keep','modelCode':'NA-H74'})
            self.assertEqual(after['title'],product['title'])
