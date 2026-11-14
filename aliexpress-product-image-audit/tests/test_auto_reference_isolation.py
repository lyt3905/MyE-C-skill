import tempfile
import unittest
import json
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG,remedy
from plan_compiler import compile_auto_plan
from final_state import simulate_final_snapshot

class ReferenceIsolationTests(unittest.TestCase):
    def test_shared_deferred_reference_keeps_original_url(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            directory=manager.directory(job['job_id'])
            product={'images':{'main':['https://x/a'],'detail':['https://x/a','https://x/b'],'sku':['https://x/a']},'skus':[{'skuImageUrl':'https://x/a'}],'descriptionJson':{'url':'https://x/a'}}
            atomic_json(directory/'audit_product.json',product)
            safe=remedy();safe['target']['index']=0
            deferred=dict(remedy(),remedy_id='REM_deferred',item_id='WM_DETAIL_000',target={'pool':'detail','index':0,'image_id':'DETAIL_000'},checks={})
            from auto_test_evidence import bind_image
            bind_image(directory,product,safe)
            compiled=compile_auto_plan(directory,job,[safe,deferred],AutomationPolicy(CONFIG))
            self.assertTrue(compiled['ok'],compiled)
            plan=json.loads((directory/'plan.v2.json').read_text())
            after=simulate_final_snapshot(product,plan)
            self.assertEqual(after['images']['main'],['https://x/b'])
            self.assertEqual(after['images']['detail'][0],'https://x/a')
            self.assertEqual(after['descriptionJson']['url'],'https://x/a')
