import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from watermark_module_fixtures import sample
from test_v2_workflow import V2WorkflowTests


class StructuredMaskGateTests(unittest.TestCase):
    def test_invalid_structure_protected_print_and_unknown_rights_never_enter_mask_or_lama(self):
        for mode in ['missing','enum','extra','coordinates','logo','product-print','rights']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);fixture=sample(root/'fixture');model=root/'model.pt';model.write_bytes(b'Fake only')
                def transform(row,item):
                    if row['decision']!='REMOVE_TEXT':return row
                    row.update(watermarks=copy.deepcopy(fixture['watermarks']),preserve_regions=fixture['preserve_regions'],background_complexity='COMPLEX')
                    if mode=='missing':row.pop('image_id')
                    elif mode=='enum':row['visual_class']='MADE_UP_CLASS'
                    elif mode=='extra':row['watermarks'][0]['command']='never executable'
                    elif mode=='coordinates':row['watermarks'][0]['bbox']=[-.1,0,.2,.2]
                    elif mode in {'logo','product-print'}:row['watermarks'][0]['kind']='MANUFACTURER_LOGO' if mode=='logo' else 'PRODUCT_PRINT'
                    return row
                with patch('mye_c_automation.image_repairs_v2.lama_torchscript',side_effect=AssertionError('Rejected observation reached LaMa')) as load:
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],rights='RIGHTS_UNKNOWN' if mode=='rights' else 'OWNED_OR_LICENSED',
                        asset_images={0:fixture['image_path']},observation_transform=transform,image_options=dict(lama_model_path=str(model)))
                self.assertEqual(load.call_count,0);self.assertEqual(result['writer'].uploads,0)
                self.assertFalse(list(result['root'].glob('v2_candidates/**/mask.png')))

    def test_valid_schema_business_and_rights_reach_existing_mask_and_mock_lama(self):
        from test_watermark_module_integration import WatermarkIntegrationTests
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);model=root/'model.pt';model.write_bytes(b'Fake only');calls=[]
            def backend(image,mask):calls.append(mask.copy());image[mask>0]=0;return image
            with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
                result=WatermarkIntegrationTests().scenario(root,complexity='COMPLEX',options=dict(lama_model_path=str(model)))
            self.assertTrue(calls);self.assertEqual(result['writer'].uploads,1);self.assertTrue(result['result']['content_validation']['ok'])
            self.assertTrue(list(result['root'].glob('v2_candidates/**/mask.png')))
