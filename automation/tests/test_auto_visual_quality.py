import tempfile
import unittest
from pathlib import Path
from PIL import Image
from mye_c_automation.visual_quality import VisualQualityInspector

class VisualQualityTests(unittest.TestCase):
    def test_machine_scans_and_dual_semantics_are_both_required(self):
        class Judge:
            def classify(self,task,item,context):
                self.item=item
                return {'status':'CLEAN','results':[{'decision':'MATCH','abstain':False,'confidence':0.99,'checks':{k:True for k in ('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe','model_match','packaging_match')},'evidence_ids':item['evidence_ids'],'image_type':'FIGURE','model':'NA-H74'} for _ in range(2)]}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'image.png';Image.new('RGB',(800,800),'white').save(path)
            judge=Judge();inspector=VisualQualityInspector(root,{'shop_id':7,'templates_required':False},judge=judge,ocr_engine=lambda image:([],None))
            result=inspector.inspect(path,path,{})
            self.assertTrue(result['ocr_pass']);self.assertTrue(result['residual_pass']);self.assertTrue(result['template_pass'])
            self.assertEqual(len(judge.item['extra_images']),2)
            self.assertTrue(list(Path(root).glob('quality_evidence/*.json')))
    def test_model_disagreement_cannot_pass(self):
        class Judge:
            def classify(self,*args):return {'status':'REVIEW','results':[]}
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'image.png';Image.new('RGB',(800,800)).save(path)
            result=VisualQualityInspector(root,{'shop_id':7},judge=Judge(),ocr_engine=lambda im:([],None)).inspect(path,path,{})
            self.assertFalse(result['source_clean'])
