import tempfile
import unittest
import hashlib
from pathlib import Path
from PIL import Image
from candidate_quality import CandidateQualityGate
from remedy_planner import RemedyPlanner
from test_auto_remedy import Inspector
from local_image_pool import load_official_pool

class OfficialPoolTests(unittest.TestCase):
    def test_explicit_provenance_and_hash_are_required(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); image=root/'official.png';Image.new('RGB',(800,800),'white').save(image)
            row={'file':'official.png','sha256':hashlib.sha256(image.read_bytes()).hexdigest(),'official_source':True,'source_url':'https://maker.example/image','model':'NA-H74','packaging_type':'FIGURE'}
            index=root/'pool.json';index.write_text(json.dumps({'schema':'official-image-pool/v1','items':[row]}))
            self.assertEqual(len(load_official_pool(index)),1)
            for field,value in [('sha256','0'*64),('official_source',False),('source_url','')]:
                index.write_text(json.dumps({'schema':'official-image-pool/v1','items':[dict(row,**{field:value})]}))
                self.assertEqual(load_official_pool(index),[])
    def test_planner_uses_product_identity_model(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); source=root/'source.png';official=root/'official.png'
            Image.new('RGB',(800,800),'white').save(source);Image.new('RGB',(800,800),'white').save(official)
            item={'id':'WM_MAIN_000','image_id':'MAIN_000','pool':'main','kind':'main','index':0,'local':str(source),'source_url':'https://x/a','evidence_ids':['E1']}
            pool=[{'file':str(official),'official_source':True,'model':'NA-H74','sha256':hashlib.sha256(official.read_bytes()).hexdigest()}]
            result=RemedyPlanner(root,CandidateQualityGate(Inspector())).plan(item,[],{'identityJson':{'modelCode':'NA-H74'}},local_pool=pool)
            self.assertEqual(result['action'],'REPLACE_LOCAL')
