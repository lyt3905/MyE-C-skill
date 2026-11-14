import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from candidate_quality import CandidateQualityGate
from remedy_planner import RemedyPlanner

class Inspector:
    def inspect(self, source, candidate, context):
        return {'product_identity_match':True,'source_clean':True,'candidate_visual_validation':True,'protected_elements_preserved':True,'ocr_pass':True,'residual_pass':True,'template_pass':True,'subject_bounds_safe':True,'model_match':True,'packaging_match':True,'official_source':True,'evidence_ids':['CV_OCR_1','DUAL_VLM_1']}

class RemedyTests(unittest.TestCase):
    def fixture(self,root):
        image=Image.new('RGB',(1000,1000),'white');ImageDraw.Draw(image).rectangle((300,200,700,700),fill='blue')
        source=Path(root)/'source.png'; image.save(source)
        twin=Path(root)/'twin.png'; image.save(twin)
        return {'id':'WM_MAIN_000','image_id':'MAIN_000','pool':'main','kind':'main','index':0,'local':str(source),'source_url':'https://x/source','evidence_ids':['WM_MAIN_000']}, {'file':str(twin),'kind':'detail','index':0,'url':'https://x/twin'}
    def test_twin_requires_independent_quality(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root)
            planner=RemedyPlanner(root,CandidateQualityGate(Inspector()))
            result=planner.plan(item,[twin],{'model':'NA-H74'})
            self.assertEqual(result['action'],'REPLACE_TWIN'); self.assertTrue(result['checks']['source_bound'])
            self.assertTrue((Path(root)/'candidate_quality.json').exists())
    def test_dirty_twin_rejected(self):
        class Bad(Inspector):
            def inspect(self,*args): return dict(super().inspect(*args),source_clean=False)
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root)
            self.assertIsNone(RemedyPlanner(root,CandidateQualityGate(Bad())).plan(item,[twin],{}))
    def test_crop_produces_asset_and_keeps_subject(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root)
            result=RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[],{},crop_box=[0,0,1000,900],subject_box=[300,200,701,701])
            self.assertEqual(result['action'],'CROP_BANNER')
            with Image.open(Path(root)/result['candidate_asset']['path']) as im: self.assertGreaterEqual(min(im.size),800)
    def test_crop_intersecting_subject_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root)
            result=RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[],{},crop_box=[0,0,1000,600],subject_box=[300,200,701,701])
            self.assertIsNone(result)
    def test_missing_verifier_never_auto_passes(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root)
            self.assertIsNone(RemedyPlanner(root,CandidateQualityGate()).plan(item,[twin],{}))
    def test_wrong_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=self.fixture(root);twin['content_sha256']='0'*64
            self.assertIsNone(RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[twin],{}))
