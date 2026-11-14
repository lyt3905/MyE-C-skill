import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw
from remedy_planner import RemedyPlanner
from candidate_quality import CandidateQualityGate
from test_auto_remedy import Inspector

class EraseTrialTests(unittest.TestCase):
    def fixture(self,root):
        path=Path(root)/'source.png';image=Image.new('RGB',(1000,1000),'white')
        draw=ImageDraw.Draw(image);draw.rectangle((300,200,700,700),fill='blue');draw.text((30,30),'shop',fill=(230,230,230));image.save(path)
        return {'id':'WM_MAIN_000','image_id':'MAIN_000','pool':'main','kind':'main','index':0,'local':str(path),'source_url':'https://x/a','evidence_ids':['WM_MAIN_000']}
    def test_simple_background_trial_preserves_every_outside_pixel(self):
        with tempfile.TemporaryDirectory() as root:
            item=self.fixture(root)
            result=RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[],{},erase_box=[20,20,100,60],subject_box=[300,200,701,701])
            self.assertEqual(result['action'],'ERASE_LOCAL')
            self.assertTrue(result['checks']['outside_mask_unchanged']);self.assertTrue(result['checks']['mask_background_only'])
            self.assertTrue((Path(root)/'erase_MAIN_000_mask.png').exists())
    def test_erase_over_product_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            item=self.fixture(root)
            result=RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[],{},erase_box=[300,200,350,250],subject_box=[300,200,701,701])
            self.assertIsNone(result)
    def test_failed_independent_recheck_never_yields_candidate(self):
        class Bad(Inspector):
            def inspect(self,*args):return dict(super().inspect(*args),residual_pass=False)
        with tempfile.TemporaryDirectory() as root:
            item=self.fixture(root)
            self.assertIsNone(RemedyPlanner(root,CandidateQualityGate(Bad())).plan(item,[],{},erase_box=[20,20,100,60],subject_box=[300,200,701,701]))
