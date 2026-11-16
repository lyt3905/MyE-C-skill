import json
import tempfile
import unittest
from PIL import Image
import test_v13_account_cli as cli


class OfficialLetterboxCliTests(unittest.TestCase):
    def test_standard_cli_uploads_original_hd_pixels_and_preserves_fields(self):
        with tempfile.TemporaryDirectory() as root:
            writer, path, _, error = cli.AccountCliTests().execute(root, case='lowres_local_letterbox')
            self.assertIsNone(error, repr(error))
            self.assertEqual((writer.uploads, writer.saves), (1, 1))
            before = json.loads((path / 'audit_product.json').read_text(encoding='utf-8'))
            after = writer.product(1)
            for field in ('descriptionJson', 'price', 'weight', 'status', 'skus', 'titleEn'):
                self.assertEqual(before[field], after[field])
            choices = json.loads((path / 'auto_decisions.json').read_text(encoding='utf-8'))['items']
            safe = [x for x in choices if x['decision'] == 'AUTO_SAFE']
            self.assertEqual([x['action'] for x in safe], ['REPLACE_LOCAL'])
            with Image.open(path / safe[0]['candidate_asset']['path']) as image:
                self.assertEqual(image.size, (1000, 1667))
            self.assertEqual(json.loads((path / 'state.json').read_text())['state'], 'AUTO_VERIFIED')

    def test_white_padding_match_never_bypasses_independent_identity(self):
        with tempfile.TemporaryDirectory() as root:
            writer, path, _, error = cli.AccountCliTests().execute(root, case='lowres_local_letterbox_mismatch')
            self.assertIsNone(error, repr(error))
            self.assertEqual((writer.uploads, writer.saves), (0, 0))
            self.assertEqual(writer.product(1)['images']['main'], ['https://fake/main'])
            self.assertEqual(json.loads((path / 'state.json').read_text())['state'], 'DEFERRED')
