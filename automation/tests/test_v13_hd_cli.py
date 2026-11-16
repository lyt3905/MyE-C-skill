import json
import tempfile
import unittest
import test_v13_account_cli


class HdCliTests(unittest.TestCase):
    def test_low_resolution_main_uses_existing_real_hd_bytes_without_upload_or_upscale(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='lowres')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(writer.product(1)['images']['main'],['https://fake/detail'])
            decisions=json.loads((path/'auto_decisions.json').read_text(encoding='utf-8'))['items']
            approved=[r for r in decisions if r['decision']=='AUTO_SAFE']
            self.assertEqual([r['action'] for r in approved],['REPLACE_TWIN'])
            self.assertEqual(approved[0]['source']['url'],'https://fake/detail')
            self.assertEqual(json.loads((path/'state.json').read_text())['state'],'AUTO_VERIFIED')
            proof=json.loads((path/'mye_c_automation.candidate_quality.json').read_text())['items'][0]
            self.assertEqual((proof['width'],proof['height']),(1000,1000))

    def test_no_genuine_hd_or_identity_conflict_preserves_original(self):
        for case in ('lowres_no_hd','lowres_mismatch','lowres_download_error','lowres_corrupt_hd','lowres_bad_sha'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case=case)
                self.assertIsNone(error,repr(error))
                self.assertEqual((writer.uploads,writer.saves),(0,0))
                self.assertEqual(writer.product(1)['images']['main'],['https://fake/main'])
                self.assertEqual(json.loads((path/'state.json').read_text())['state'],'DEFERRED')

    def test_shared_url_replacement_updates_both_real_pools_without_losing_references(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='lowres_shared')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            after=writer.product(1)
            self.assertEqual(after['images']['main'],['https://fake/detail'])
            self.assertEqual(after['images']['sku'],['https://fake/detail'])
            self.assertEqual(json.loads((path/'state.json').read_text())['state'],'AUTO_VERIFIED')

    def test_unrelated_missing_image_remains_deferred_while_safe_hd_action_completes(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='lowres_other_missing')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(json.loads((path/'state.json').read_text())['state'],'PARTIALLY_AUTO_FIXED')
            self.assertEqual(writer.product(1)['images']['detail'][1],'https://fake/missing')
            self.assertIn('AUDIT_COVERAGE_INCOMPLETE',(path/'deferred_items.json').read_text())
