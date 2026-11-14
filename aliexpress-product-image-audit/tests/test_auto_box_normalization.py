import tempfile,unittest,hashlib
from pathlib import Path
from PIL import Image,ImageDraw
from box_normalization import normalize_box
class BoxNormalizationTests(unittest.TestCase):
    def test_small_box_is_padded_without_cropping_and_original_is_immutable(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.png';target=Path(root)/'target.png'
            image=Image.new('RGB',(400,600),'white');ImageDraw.Draw(image).rectangle((0,0,399,599),outline='black',width=3);image.save(source)
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            result=normalize_box(source,target)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
            with Image.open(target) as image:
                self.assertEqual(image.size,(800,800));self.assertEqual(image.getpixel((0,400)),(255,255,255))
            self.assertEqual(result['source_sha256'],before)
            self.assertEqual(result['method'],'LANCZOS_WHITE_PAD_LIGHT_SHARPEN')
            self.assertEqual(result['content_box'],[133,0,666,800])
    def test_large_source_and_same_output_refuse_processing(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.png';Image.new('RGB',(800,800)).save(source)
            with self.assertRaisesRegex(ValueError,'NOT_SMALL'):normalize_box(source,Path(root)/'out.png')
            with self.assertRaisesRegex(ValueError,'SOURCE_OVERWRITE'):normalize_box(source,source)
    def test_planner_requires_box_observation_and_independent_recheck(self):
        from remedy_planner import RemedyPlanner
        from candidate_quality import CandidateQualityGate
        from test_auto_remedy import Inspector
        class BoxInspector(Inspector):
            def observe_image(self,path,context):return {'verified':True,'clean':True,'image_type':'BOX','model':'NA-H74','sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'evidence_ids':['BOX_DUAL']}
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'small.png';Image.new('RGB',(400,600),'blue').save(source)
            item={'id':'BOX_MAIN_000','image_id':'MAIN_000','pool':'main','index':0,'local':str(source),'evidence_ids':['SIZE']}
            planner=RemedyPlanner(root,CandidateQualityGate(BoxInspector()),allowed_actions={'BOX_NORMALIZE'})
            row=planner.plan_box(item,{'identityJson':{'modelCode':'NA-H74'}})
            self.assertEqual(row['action'],'BOX_NORMALIZE')
            self.assertTrue(row['checks']['box_verified'])
            planner.allowed_actions=set();self.assertIsNone(planner.plan_box(item,{'identityJson':{'modelCode':'NA-H74'}}))
