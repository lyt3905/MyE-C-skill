import unittest
from pathlib import Path
import tempfile
from final_state import simulate_final_snapshot
from workflow_v2_pipeline import image_candidate

class MainChainTests(unittest.TestCase):
    def test_candidate_has_stable_business_target(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'original.jpg'; path.write_bytes(b'image')
            row={'file':str(path),'kind':'main','index':2,'url':'https://old/image'}
            item=image_candidate(row)
            self.assertEqual(item['image_id'],'MAIN_002')
            self.assertEqual((item['kind'],item['pool'],item['index']),('main','main',2))
            self.assertEqual(item['source_url'],row['url'])
            self.assertEqual(len(item['source_sha256']),64)
            self.assertNotIn(str(path),item['image_id'])
    def test_upload_remaps_all_exact_references(self):
        before={'images':{'main':['https://old/a'],'detail':['https://old/a'],'sku':['https://old/a']},'skus':[{'skuImageUrl':'https://old/a'}],'descriptionJson':{'blocks':[{'url':'https://old/a'},{'text':'https://old/a?keep'}]}}
        plan={'desired':{},'post_actions':{'uploads':[{'pool':'main','index':0}]}}
        after=simulate_final_snapshot(before,plan,['https://new/a'])
        self.assertEqual(after['skus'][0]['skuImageUrl'],'https://new/a')
        self.assertEqual(after['images']['detail'],['https://new/a'])
        self.assertEqual(after['descriptionJson'],before['descriptionJson'])  # v1.2 opaque fixed field
        self.assertEqual(after['descriptionJson']['blocks'][1]['text'],'https://old/a?keep')
        self.assertEqual(before['images']['main'],['https://old/a'])
