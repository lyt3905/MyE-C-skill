import tempfile
import unittest
from pathlib import Path
from PIL import Image
from mye_c_automation.visual_quality import VisualQualityInspector

class QualityEvidenceHistoryTests(unittest.TestCase):
    def test_readback_review_does_not_overwrite_original_quality_evidence(self):
        class Judge:
            def classify(self,task,item,context):
                return {'status':'CLEAN','results':[{'decision':'MATCH','abstain':False,'confidence':.99,'checks':{k:True for k in ('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe','model_match','packaging_match')},'evidence_ids':item['evidence_ids']} for _ in range(2)]}
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);source=root/'source.png';candidate=root/'candidate.png'
            Image.new('RGB',(800,800),'blue').save(source);Image.new('RGB',(800,800),'white').save(candidate)
            inspector=VisualQualityInspector(root,{'shop_id':7},judge=Judge(),ocr_engine=lambda im:([],None))
            inspector.inspect(source,candidate,{'title':'Before'})
            original={p:p.read_bytes() for p in (root/'quality_evidence').glob('*.json')}
            inspector.inspect(candidate,candidate,{'title':'After'})
            self.assertEqual(len(list((root/'quality_evidence').glob('*.json'))),2)
            self.assertTrue(all(p.read_bytes()==data for p,data in original.items()))
