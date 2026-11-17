import json
import tempfile
import unittest
import test_v13_account_cli


class RemainingActionsCliTests(unittest.TestCase):
    def execute(self,root,case):return test_v13_account_cli.AccountCliTests().execute(root,case=case)
    def read(self,path,name):return json.loads((path/name).read_text(encoding='utf-8'))

    def test_brand_code_cli_updates_only_known_unambiguous_field(self):
        for case in ('brand','brand_alias'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=self.execute(root,case)
                self.assertIsNone(error,repr(error))
                before=self.read(path,'audit_product.json');after=writer.product(1)
                self.assertEqual((writer.uploads,writer.saves,writer.translations),(0,1 if case=='brand' else 0,0))
                self.assertEqual(after['brandId'],200017853 if case=='brand' else 200014695)
                for field in ('titleEn','descriptionJson','images','skus','price','weight','status'):self.assertEqual(after[field],before[field])

    def test_low_resolution_sku_cli_repairs_image_pool_and_live_sku_reference(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'lowres_sku')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            after=writer.product(1)
            self.assertEqual(after['images']['sku'],['https://fake/detail'])
            self.assertEqual(after['skus'][0],{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/detail','price':10})
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')

    def test_explicit_official_pool_cli_uploads_real_hd_with_provenance(self):
        for case in ('lowres_local','lowres_local_bad_hash','lowres_local_unverified','lowres_local_wrong_model'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=self.execute(root,case)
                self.assertIsNone(error,repr(error))
                self.assertEqual((writer.uploads,writer.saves),(1,1) if case=='lowres_local' else (0,0))
                self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED' if case=='lowres_local' else 'DEFERRED')
                if case=='lowres_local':
                    row=next(r for r in self.read(path,'auto_decisions.json')['items'] if r['decision']=='AUTO_SAFE')
                    self.assertEqual(row['action'],'REPLACE_LOCAL')
                    self.assertEqual(row['source']['source_url'],'https://maker.example/NA-H74.png')
                    self.assertEqual(self.read(path,'dry_run.json')['planned_upload_count'],1)

    def test_multicolor_skus_receive_their_own_verified_body_images(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'sku_multicolor')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual([r['skuImageUrl'] for r in writer.product(1)['skus']],['https://fake/red_body','https://fake/detail'])
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')

    def test_conflicting_explicit_sku_model_never_receives_parent_model_image(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'sku_model_conflict')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,0))
            self.assertEqual(self.read(path,'state.json')['state'],'DEFERRED')
            self.assertEqual(writer.product(1)['skus'][0]['skuImageUrl'],'https://fake/main')

    def test_conflicting_sku_is_deferred_while_independent_valid_sku_is_fixed(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'sku_multicolor_conflict')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual([r['skuImageUrl'] for r in writer.product(1)['skus']],['https://fake/main','https://fake/detail'])
            self.assertEqual(self.read(path,'state.json')['state'],'PARTIALLY_AUTO_FIXED')

    def test_bundle_or_accessory_spec_without_item_level_content_proof_does_not_get_generic_body(self):
        for case in ('sku_bundle','sku_bundle_count','sku_bundle_accessory','sku_bundle_pack'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=self.execute(root,case)
                self.assertIsNone(error,repr(error))
                self.assertEqual((writer.uploads,writer.saves),(0,0))
                self.assertEqual(self.read(path,'state.json')['state'],'DEFERRED')
                self.assertIn('SKU_COMPLEX_CONTENTS_UNVERIFIED',(path/'deferred_items.json').read_text(encoding='utf-8'))

    def test_uncertain_bundle_does_not_block_independent_simple_sku(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'sku_bundle_partial')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual([r['skuImageUrl'] for r in writer.product(1)['skus']],['https://fake/main','https://fake/detail'])
            self.assertEqual(self.read(path,'state.json')['state'],'PARTIALLY_AUTO_FIXED')
