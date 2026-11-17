import tempfile
import unittest
from pathlib import Path
from test_auto_decision import CONFIG,remedy
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.job_manager import JobManager, atomic_json
from mye_c_automation.plan_compiler import compile_auto_plan
from mye_c_automation.final_state import simulate_final_snapshot

class AutoCompilerTests(unittest.TestCase):
    def test_safe_action_compiles_while_other_item_deferred(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            directory=manager.directory(job['job_id'])
            product={'id':1,'shopId':7,'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':['https://x/a']},'skus':[{'skuImageUrl':'https://x/a'}],'descriptionJson':{'url':'https://x/a'}}
            atomic_json(directory/'audit_product.json',product)
            good=remedy(); good['target']['index']=0
            bad=dict(remedy(),remedy_id='REM_bad',checks={})
            from auto_test_evidence import bind_image
            bind_image(directory,product,good)
            result=compile_auto_plan(directory,job,[good,bad],AutomationPolicy(CONFIG))
            self.assertTrue(result['ok'])
            import json
            plan=json.loads((directory/'plan.v2.json').read_text())
            self.assertEqual(len(plan['automation']['actions']),1)
            self.assertEqual(simulate_final_snapshot(product,plan)['images']['main'],['https://x/b'])
            self.assertEqual(len(json.loads((directory/'deferred_items.json').read_text())['items']),1)
    def test_bad_final_structure_blocks_all(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            directory=manager.directory(job['job_id'])
            atomic_json(directory/'audit_product.json',{'images':{'main':['https://x/a']}})
            good=remedy();good['target']['index']=0
            result=compile_auto_plan(directory,job,[good],AutomationPolicy(CONFIG))
            self.assertFalse(result['ok']);self.assertEqual(result['status'],'BLOCKED_FATAL')
            self.assertFalse((directory/'plan.v2.json').exists())
