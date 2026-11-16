import json
import tempfile
import unittest
import test_v13_account_cli as cli
from mye_c_automation.check import check_saved_job


class LegacySkuDeliveryCliTests(unittest.TestCase):
    def test_forged_before_cannot_make_new_outside_reference_look_legacy(self):
        with tempfile.TemporaryDirectory() as root:
            _, path, _, error = cli.AccountCliTests().execute(root, case='lowres_legacy_sku')
            self.assertIsNone(error, repr(error))
            self.assertTrue(check_saved_job(path)['ok'])
            for name in ('before.json', 'after.json', 'expected_after.json'):
                target = path / name
                snapshot = json.loads(target.read_text(encoding='utf-8'))
                snapshot['skus'][0]['skuImageUrl'] = 'https://fake/unapproved-new-reference'
                target.write_text(json.dumps(snapshot), encoding='utf-8')
            checked = check_saved_job(path)
            self.assertFalse(checked['ok'], checked)
            self.assertIn('BEFORE_SNAPSHOT_BINDING_MISMATCH', checked['error'])

    def test_independent_hd_action_preserves_existing_reference_and_passes_delivery(self):
        with tempfile.TemporaryDirectory() as root:
            writer, path, _, error = cli.AccountCliTests().execute(root, case='lowres_legacy_sku')
            self.assertIsNone(error, repr(error))
            self.assertEqual((writer.uploads, writer.saves), (0, 1))
            before = json.loads((path / 'audit_product.json').read_text(encoding='utf-8'))
            after = writer.product(1)
            self.assertEqual(after['skus'], before['skus'])
            self.assertEqual(after['images']['sku'], before['images']['sku'])
            self.assertEqual(after['images']['main'], ['https://fake/detail'])
            self.assertTrue(json.loads((path / 'final_check.json').read_text())['ok'])
            checked = check_saved_job(path)
            self.assertTrue(checked['ok'], checked)
