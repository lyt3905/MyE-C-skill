import tempfile
import unittest
from pathlib import Path
from PIL import Image
from budget_manager import BudgetManager
from ai_judge.client import JudgeClient

class ReservationTests(unittest.TestCase):
    def test_token_failure_leaves_no_image_reservation_or_request(self):
        with tempfile.TemporaryDirectory() as root:
            image=Path(root)/'image.png';Image.new('RGB',(800,800)).save(image)
            budget=BudgetManager({'ai_requests':10,'full_resolution_images':10,'total_tokens':1})
            client=JudgeClient(budget,Path(root)/'cache',transport=lambda *args:self.fail('must not call'))
            result=client.classify('watermark',{'id':'W1','local':str(image),'evidence_ids':['W1']},{})
            self.assertEqual(result['error'],'BUDGET_EXCEEDED')
            self.assertEqual(budget.snapshot()['used']['full_resolution_images'],0)
            self.assertEqual(client.metrics['requests'],0)
            budget.close()
