import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
from mye_c_automation.candidate_quality import CandidateQualityGate, sha256
from mye_c_automation.imgpool import _phash, _ham
from mye_c_automation.remedy_planner import RemedyPlanner

class Inspector:
    def __init__(self, identity=True):
        self.identity=identity
        self.calls=[]
    def inspect(self, source, candidate, context):
        self.calls.append((source,candidate))
        return dict(product_identity_match=self.identity,source_clean=True,
                    candidate_visual_validation=True,protected_elements_preserved=True,
                    ocr_pass=True,residual_pass=True,template_pass=True,evidence_ids=['INDEPENDENT'])

class OfficialLetterboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        portrait=np.full((500,300,3),225,np.uint8)
        rng=np.random.default_rng(91)
        for _ in range(35):
            x,y=rng.integers(15,240),rng.integers(15,440)
            cv2.rectangle(portrait,(int(x),int(y)),(int(x+35),int(y+45)),tuple(map(int,rng.integers(20,200,3))),-1)
        self.source=np.full((500,500,3),255,np.uint8)
        self.source[:,100:400]=portrait
        self.original=self.root/'source.png'; self.candidate=self.root/'official.png'
        cv2.imwrite(str(self.original),self.source)
        cv2.imwrite(str(self.candidate),cv2.resize(portrait,(1000,1667)))
        self.item=dict(id='i',pool='main',index=0,image_id='img',local=str(self.original),source_url='source',evidence_ids=['SOURCE'])
        self.row=dict(local=str(self.candidate),official_source=True,model='MODEL',sha256=sha256(self.candidate))
        self.context={'model':'MODEL'}
    def plan(self,row=None,inspector=None):
        inspector=inspector or Inspector()
        planner=RemedyPlanner(self.root,CandidateQualityGate(inspector),allowed_actions={'REPLACE_LOCAL'})
        return planner.plan(self.item,[],self.context,local_pool=[row or self.row]),inspector
    def test_white_letterbox_admits_original_to_independent_gate_without_pixel_writes(self):
        before=[sha256(self.original),sha256(self.candidate)]
        src=cv2.imread(str(self.original),0); candidate=cv2.imread(str(self.candidate),0)
        self.assertGreater(_ham(_phash(src),_phash(candidate)),10)
        result,inspector=self.plan()
        self.assertIsNotNone(result)
        self.assertEqual(result['action'],'REPLACE_LOCAL')
        self.assertEqual(len(inspector.calls),1)
        output=cv2.imread(str(inspector.calls[0][1]))
        np.testing.assert_array_equal(output,cv2.imread(str(self.candidate)))
        self.assertEqual(output.shape[:2],(1667,1000))
        self.assertEqual(before,[sha256(self.original),sha256(self.candidate)])
    def test_nonwhite_edges_do_not_admit_letterbox_fallback(self):
        self.source[:,0]=200; self.source[:,-1]=200
        cv2.imwrite(str(self.original),self.source)
        result,inspector=self.plan()
        self.assertIsNone(result); self.assertEqual(inspector.calls,[])
    def test_top_bottom_letterbox_also_preserves_original_candidate(self):
        cv2.imwrite(str(self.original),cv2.transpose(self.source))
        cv2.imwrite(str(self.candidate),cv2.transpose(cv2.imread(str(self.candidate))))
        self.row['sha256']=sha256(self.candidate)
        result,inspector=self.plan()
        self.assertIsNotNone(result)
        self.assertEqual(len(inspector.calls),1)
        np.testing.assert_array_equal(cv2.imread(str(inspector.calls[0][1])),cv2.imread(str(self.candidate)))
    def test_colored_outer_edge_cannot_pass_via_gray_brightness(self):
        self.source[:,0]=(220,255,255)
        self.source[:,-1]=(220,255,255)
        cv2.imwrite(str(self.original),self.source)
        result,inspector=self.plan()
        self.assertIsNone(result); self.assertEqual(inspector.calls,[])
    def test_official_model_and_sha_requirements_remain_mandatory(self):
        for override in ({'official_source':False},{'model':'OTHER'},{'sha256':'wrong'}):
            with self.subTest(override=override):
                result,inspector=self.plan({**self.row,**override})
                self.assertIsNone(result); self.assertEqual(inspector.calls,[])
    def test_independent_identity_failure_still_rejects(self):
        inspector=Inspector(identity=False)
        result,_=self.plan(inspector=inspector)
        self.assertEqual(len(inspector.calls),1)
        self.assertIsNone(result)

if __name__=='__main__': unittest.main()
