import tempfile
import unittest
import json
from job_manager import atomic_json
from test_v21_compiler import CompilerReviewTests
from plan_compiler import compile_plan
from plan_v2 import plan_hash
from workflow_runner import live_dry_run

class PreviewIdentityTests(unittest.TestCase):
    def test_matching_product_hash_does_not_override_wrong_shop_session(self):
        with tempfile.TemporaryDirectory() as root:
            manager,job,path=CompilerReviewTests().fixture(root)
            product={'id':1,'shopId':7,'titleEn':'Before','images':{'main':['https://x/a'],'detail':['https://x/b'],'sku':[]}}
            atomic_json(path/'audit_product.json',product);compile_plan(path,job)
            plan=json.loads((path/'plan.v2.json').read_text());plan['desired']={'titleEn':'After'}
            atomic_json(path/'plan.v2.json',plan);atomic_json(path/'compiled_plan.json',{'plan_sha256':plan_hash(plan)})
            atomic_json(path/'state.json',{'state':'PLAN_READY'})
            class Reader:
                def product(self,pid):return product
                def current_shop(self):return 4
            with self.assertRaisesRegex(ValueError,'SHOP_MISMATCH'):live_dry_run(manager,job['job_id'],Reader())
