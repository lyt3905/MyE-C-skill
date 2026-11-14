import json
import tempfile
import unittest
from audit_one import _image_urls
import test_v13_account_cli


class SkuReferenceIdentityTests(unittest.TestCase):
    def test_reference_only_image_has_distinct_audit_index_and_original_locator(self):
        rows=_image_urls({'images':{'sku':['https://fake/listed']},
                          'skus':[{'skuId':1,'skuImageUrl':'https://fake/reference'}]})
        self.assertEqual([r['index'] for r in rows],[0,1])
        self.assertEqual(rows[1]['source'],'skus')
        self.assertEqual(rows[1]['source_index'],0)

    def test_standard_cli_audits_reference_without_overwriting_listed_sku_target(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='sku_reference_only')
            self.assertIsNone(error,repr(error))
            raw=json.loads((path/'audit_raw.json').read_text(encoding='utf-8'))['images']
            ids=[r['image_id'] for r in raw]
            self.assertEqual(len(ids),len(set(ids)))
            reference=next(r for r in raw if r['url']=='https://fake/reference')
            self.assertEqual((reference['kind'],reference['index'],reference['source_index']),('sku',1,0))
            queue=json.loads((path/'ai_queue.json').read_text(encoding='utf-8'))['items']
            item=next(r for r in queue if r.get('source_url')=='https://fake/reference')
            self.assertTrue(item['reference_only'])
            decisions=json.loads((path/'auto_decisions.json').read_text(encoding='utf-8'))['items']
            decision=next(r for r in decisions if r['item_id']==item['id'])
            self.assertEqual((decision['action'],decision['decision']),('WEB_DEFER','DEFERRED'))
            self.assertIn('SKU_REFERENCE_ONLY_NO_POOL_TARGET',decision['reason_codes'])
            self.assertEqual((writer.uploads,writer.saves),(0,0))
            self.assertEqual(writer.product(1)['images']['sku'],['https://fake/main'])

    def test_low_resolution_reference_only_never_becomes_a_virtual_pool_write_target(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='sku_reference_lowres')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,0))
            rows=json.loads((path/'auto_decisions.json').read_text(encoding='utf-8'))['items']
            self.assertFalse(any(r['decision']=='AUTO_SAFE' and r.get('target',{}).get('pool')=='sku' and r['target'].get('index')==1 for r in rows))
