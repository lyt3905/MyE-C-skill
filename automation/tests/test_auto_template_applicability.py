import tempfile,unittest,json
from pathlib import Path
from mye_c_automation.evidence_builder import build

class TemplateApplicabilityTests(unittest.TestCase):
    def test_required_missing_is_distinct_from_explicit_no_applicable(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            build(root,[],shop_id=7,templates_required=True)
            self.assertEqual(json.loads((root/'template_scan.json').read_text())['status'],'REQUIRED_TEMPLATE_MISSING')
            (root/'template_config.json').write_text(json.dumps({'templates':[],'required_shop_ids':[],'no_applicable_shop_ids':[7]}))
            build(root,[],shop_id=7,templates_required=True)
            self.assertEqual(json.loads((root/'template_scan.json').read_text())['status'],'NO_APPLICABLE_TEMPLATE')
            manifest=json.loads((root/'evidence_manifest.json').read_text())
            self.assertIn('template_config.json',{r['path'] for r in manifest['files']})
    def test_conflicting_template_declarations_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);(root/'template_config.json').write_text(json.dumps({'templates':[],'required_shop_ids':[7],'no_applicable_shop_ids':[7]}))
            with self.assertRaisesRegex(ValueError,'TEMPLATE_CONFIG_CONFLICT'):build(root,[],shop_id=7,templates_required=True)
