import tempfile
import unittest
import hashlib,json
from pathlib import Path
from PIL import Image
from budget_manager import BudgetManager
from ai_judge.client import JudgeClient

class ComparisonCacheTests(unittest.TestCase):
    def test_changed_comparison_bytes_cannot_reuse_cached_clean(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);primary=root/'primary.png';source=root/'source.png'
            Image.new('RGB',(800,800),'white').save(primary);Image.new('RGB',(800,800),'blue').save(source)
            evidence={'id':'W1','local':str(primary),'evidence_ids':['E1'],'extra_images':[{'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'image_id':'SOURCE'}]}
            row={'task_type':'watermark','item_id':'W1','confidence':.99,'abstain':False,'evidence_ids':['E1'],'classification':'manufacturer_branding','owner':'factory','location':'bottom'}
            budget=BudgetManager({'ai_requests':10,'full_resolution_images':10})
            client=JudgeClient(budget,root/'cache',models=('fake',),transport=lambda *args:{'choices':[{'message':{'content':json.dumps(row)}}]})
            self.assertEqual(client.classify('watermark',evidence,{})['status'],'CLEAN')
            Image.new('RGB',(800,800),'red').save(source)
            self.assertEqual(client.classify('watermark',evidence,{})['status'],'NEEDS_REVIEW')
            self.assertEqual(client.metrics['requests'],1);budget.close()
