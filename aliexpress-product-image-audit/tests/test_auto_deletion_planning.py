import tempfile,unittest,hashlib
from pathlib import Path
from PIL import Image
from auto_deletions import plan_deletion

class DeletionPlanningTests(unittest.TestCase):
    def fixture(self,root):
        path=Path(root)/'banner.png';Image.new('RGB',(800,800),'red').save(path)
        product={'images':{'main':['https://x/banner','https://x/body'],'detail':['https://x/detail'],'sku':['https://x/body']}}
        item={'id':'WM_MAIN_000','image_id':'MAIN_000','pool':'main','kind':'main','index':0,'local':str(path),'source_url':'https://x/banner','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'evidence_ids':['WM_MAIN_000']}
        return product,item
    def test_only_independently_verified_non_box_non_official_banner_can_delete(self):
        class Inspector:
            def inspect_deletion(self,*args,**kwargs):return {'ok':True,'is_box':False,'is_official':False,'category':'STORE_BANNER','information_preserved':True,'evidence_ids':['DUAL_DELETE']}
        with tempfile.TemporaryDirectory() as root:
            product,item=self.fixture(root)
            row=plan_deletion(root,item,product,[],Inspector())
            self.assertEqual(row['action'],'DELETE_REDUNDANT');self.assertFalse(row['is_box'])
    def test_box_official_uncertain_and_last_image_are_preserved(self):
        for changes in ({'is_box':True},{'is_official':True},{'ok':False},{'information_preserved':False}):
            class Inspector:
                def inspect_deletion(self,*args,**kwargs):return dict({'ok':True,'is_box':False,'is_official':False,'category':'STORE_BANNER','information_preserved':True,'evidence_ids':['DUAL_DELETE']},**changes)
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as root:
                product,item=self.fixture(root)
                self.assertIsNone(plan_deletion(root,item,product,[],Inspector()))
        with tempfile.TemporaryDirectory() as root:
            product,item=self.fixture(root);product['images']['main']=product['images']['main'][:1]
            self.assertIsNone(plan_deletion(root,item,product,[],Inspector()))
