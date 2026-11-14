import tempfile
import unittest
import json
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG,remedy
from auto_test_evidence import bind_image
from plan_compiler import compile_auto_plan

class OptionalPoolPlanTests(unittest.TestCase):
    def test_image_change_preserves_existing_auxiliary_pools(self):
        with tempfile.TemporaryDirectory() as root:
            manager=JobManager(root);job=manager.create(1,7,{})
            directory=manager.directory(job['job_id'])
            product={'images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':['https://x/a'],'ai':['https://x/a'],'scene':[],'gallery':[],'attachList':[]}}
            atomic_json(directory/'audit_product.json',product)
            row=remedy();bind_image(directory,product,row)
            result=compile_auto_plan(directory,job,[row],AutomationPolicy(CONFIG))
            self.assertTrue(result['ok'],result)
            images=json.loads((directory/'plan.v2.json').read_text())['desired']['images']
            for pool in ('ai','scene','gallery','attachList'):self.assertEqual(images[pool],product['images'][pool])
