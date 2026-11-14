import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from test_v21_compiler import CompilerReviewTests
from job_manager import atomic_json
from plan_v2 import plan_hash
from workflow_runner import live_dry_run

class LivePreviewTests(unittest.TestCase):
    def test_upload_has_visible_difference_without_mutation(self):
        from PIL import Image
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            manager,job,path=CompilerReviewTests().fixture(root)
            product={'id':1,'shopId':7,'images':{'main':['https://old/a'],'detail':['https://old/b'],'sku':['https://old/c']}}
            atomic_json(path/'audit_product.json',product)
            from plan_compiler import compile_plan
            compile_plan(path,job)
            plan=json.loads((path/'plan.v2.json').read_text())
            asset=path/'crop.png'; Image.new('RGB',(800,800)).save(asset)
            plan['desired']={'images':product['images']}
            plan['post_actions']={'uploads':[dict(path='crop.png',sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),pool='main',index=0)]}
            atomic_json(path/'plan.v2.json',plan)
            atomic_json(path/'compiled_plan.json',{'plan_sha256':plan_hash(plan)})
            atomic_json(path/'state.json',{'state':'PLAN_READY'})
            reader=Mock(); reader.product.return_value=product
            result=live_dry_run(manager,job['job_id'],reader)
            self.assertTrue(result['changes'])
            self.assertEqual(result['planned_upload_count'],1)
            self.assertIn('UPLOAD_TOKEN:',str(result['changes']))
            reader.upload.assert_not_called(); reader.save.assert_not_called()
