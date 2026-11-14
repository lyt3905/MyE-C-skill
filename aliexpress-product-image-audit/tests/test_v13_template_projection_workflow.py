import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
from evidence_builder import build
from template_applicability import resolve
from visual_quality import VisualQualityInspector
import test_v13_account_cli as cli


class TemplateProjectionWorkflowTests(unittest.TestCase):
    def test_unknown_config_projection_cannot_silently_use_gray(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'INVALID_TEMPLATE_PROJECTION'):
            resolve(root, 7, templates=[{'shop_id': 7, 'path': 'template.npy', 'projection': 'typo'}])

    def test_evidence_preserves_projection_and_suspect_roi(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.png'; template = root / 'template.npy'
            Image.new('RGB', (800, 800), 'white').save(source)
            np.save(template, np.ones((16, 16), dtype=np.float32))
            with patch('wm_tpl.scan', return_value={'ncc': .72, 'source_coordinates': [200, 300, 216, 316]}) as scan:
                build(root, [{'kind': 'main', 'index': 0, 'file': str(source)}], shop_id=7,
                      templates=[{'shop_id': 7, 'path': str(template), 'projection': 'red_excess'}])
            self.assertEqual(scan.call_args.kwargs.get('projection'), 'red_excess')
            item = json.loads((root / 'template_scan.json').read_text())['items'][0]
            self.assertEqual((item['status'], item['projection']), ('SUSPECT', 'red_excess'))
            self.assertEqual((item['hit_threshold'], item['clean_threshold']), (.8, .65))
            self.assertTrue(json.loads((root / 'candidate_crop_manifest.json').read_text())['items'])

    def test_suspect_cannot_pass_independent_candidate_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'source.png'; template = root / 'template.npy'
            Image.new('RGB', (800, 800), 'white').save(source); np.save(template, np.ones((16, 16), dtype=np.float32))
            (root / 'template_config.json').write_text(json.dumps({'templates': [
                {'shop_id': 7, 'path': str(template), 'projection': 'red_excess'}], 'required_shop_ids': [7]}))
            flags = 'product_identity_match source_clean candidate_visual_validation protected_elements_preserved residual_pass subject_bounds_safe model_match packaging_match official_source'.split()
            judge = Mock(); judge.classify.return_value = {'status': 'CLEAN', 'results': [
                {'decision': 'MATCH', 'confidence': .99, 'abstain': False, 'checks': dict.fromkeys(flags, True)}] * 2}
            with patch('wm_tpl.scan', return_value=.72) as scan:
                observed = VisualQualityInspector(root, {'shop_id': 7, 'templates_required': True},
                    judge=judge, ocr_engine=lambda _: ([], None)).inspect(source, source, {})
            self.assertEqual(scan.call_args.kwargs.get('projection'), 'red_excess')
            self.assertFalse(observed['template_pass'])
            self.assertTrue(observed['product_identity_match'])

    def test_standard_cli_routes_suspect_to_model_without_writes(self):
        seen = []
        def suspect(path, template, return_location=False, projection='gray'):
            seen.append(projection)
            return {'ncc': .72, 'source_coordinates': [200, 300, 216, 316]} if return_location else .72
        with tempfile.TemporaryDirectory() as temp, patch('wm_tpl.scan', side_effect=suspect):
            writer, path, _, error = cli.AccountCliTests().execute(temp, case='template_localization',
                                                                template_projection='red_excess')
            self.assertIsNone(error, repr(error))
            self.assertTrue(seen); self.assertEqual(set(seen), {'red_excess'})
            self.assertEqual((writer.uploads, writer.saves), (0, 0))
            scans = json.loads((path / 'template_scan.json').read_text())['items']
            self.assertTrue(all(x['status'] == 'SUSPECT' for x in scans))
            queue = json.loads((path / 'ai_queue.json').read_text())['items']
            self.assertTrue(any(x.get('pool') == 'detail' and x.get('index') == 0 for x in queue))
