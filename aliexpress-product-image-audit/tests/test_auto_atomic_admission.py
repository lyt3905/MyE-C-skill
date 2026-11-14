import tempfile
import unittest
from pathlib import Path
from PIL import Image
from budget_manager import BudgetManager
from ai_judge.client import JudgeClient

class AtomicAdmissionTests(unittest.TestCase):
    def test_request_budget_failure_rolls_back_image_and_token_admission(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'image.png';Image.new('RGB',(800,800)).save(path)
            budget=BudgetManager({'ai_requests':0,'full_resolution_images':10,'total_tokens':10000})
            client=JudgeClient(budget,Path(root)/'cache',transport=lambda *args:self.fail('no request allowed'))
            result=client.classify('watermark',{'id':'W1','local':str(path),'evidence_ids':['W1']},{})
            self.assertEqual(result['error'],'BUDGET_EXCEEDED')
            self.assertEqual(budget.snapshot()['used'],{'ai_requests':0,'full_resolution_images':0,'total_tokens':0})
            self.assertFalse(client._viewed);budget.close()
