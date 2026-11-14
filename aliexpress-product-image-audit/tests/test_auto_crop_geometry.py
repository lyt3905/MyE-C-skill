import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
import test_auto_remedy as helpers
from remedy_planner import RemedyPlanner
from candidate_quality import CandidateQualityGate

class CropGeometryTests(unittest.TestCase):
    def test_edge_crop_preserves_product_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as root:
            item,twin=helpers.RemedyTests().fixture(root)
            row=RemedyPlanner(root,CandidateQualityGate(helpers.Inspector())).plan(item,[],{},crop_box=[0,0,1000,900],subject_box=[300,200,701,701])
            image=np.asarray(Image.open(Path(root)/row['candidate_asset']['path']))
            mask=(image[:,:,2]>200)&(image[:,:,0]<30)&(image[:,:,1]<30)
            ys,xs=np.where(mask)
            self.assertAlmostEqual((xs.max()-xs.min()+1)/(ys.max()-ys.min()+1),401/501,delta=.02)
