import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image

FIXTURES=Path(__file__).parent/'fixtures/global_glyphs'

def actual(n):
    source=FIXTURES/f'5173-main{n}.webp'
    value=json.loads((FIXTURES/f'5173-main{n}-auto-observation.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==value['image_sha256']
    return source,np.array(Image.open(source).convert('RGB')),value['observation']


class DefaultPreciseWatermarksTests(unittest.TestCase):
    def prepare(self,image,observation,**policy):
        from mye_c_automation.watermark_processing.text_masks import prepare_execution
        from mye_c_automation.watermark_processing.contracts import policy_options
        return prepare_execution(image,observation,policy_options(policy))

    def test_default_policy_prefers_pattern_and_bounded_print_restore(self):
        from mye_c_automation.watermark_processing.contracts import policy_options
        p=policy_options();self.assertTrue(p['prefer_repeated_glyphs']);self.assertEqual(p['covered_print_policy'],'BOUNDED_RESTORE')

    def test_fresh_car_and_robot_regions_get_precise_global_plan_without_raw_rewrite(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        for n in (2,3):
            with self.subTest(n=n):
                _,image,observation=actual(n);before=copy.deepcopy(observation)
                executed,plan=self.prepare(image,observation)
                mask,ratio=mask_for((800,800),executed,image=image)
                self.assertLess(ratio,.08);self.assertGreater(ratio,.01)
                self.assertTrue(any(m.get('glyph_search_scope')=='IMAGE' for m in executed['watermarks']))
                self.assertTrue(plan['groups']);self.assertTrue(plan['protection_adjustments'])
                self.assertEqual(observation,before)
                self.assertEqual(executed['decision'],observation['decision'])
                self.assertEqual(executed['product_identity'],observation['product_identity'])

    def test_exact_policy_keeps_print_overlap_blocked(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        _,image,o=actual(2);executed,_=self.prepare(image,o,covered_print_policy='EXACT')
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):mask_for((800,800),executed,image=image)

    def test_structural_protection_without_a_matching_ai_print_label_stays_exact(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        _,image,o=actual(3);o['preserve_regions'].append(dict(kind='physical_hinge',bbox=[.1,.1,.9,.9],scope='EXACT_REGION'))
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):
            executed,_=self.prepare(image,o);mask_for((800,800),executed,image=image)

    def test_manufacturer_logo_and_creator_keep_labels_are_not_relaxed(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        for kind in ('MANUFACTURER_LOGO','CREATOR_CREDIT','NORMAL_PHOTO_TEXT'):
            with self.subTest(kind=kind):
                _,image,o=actual(2)
                for row in o['watermarks']:
                    if row.get('action')=='KEEP':row['kind']=kind
                with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):
                    executed,_=self.prepare(image,o);mask_for((800,800),executed,image=image)

    def test_unidentified_print_region_is_not_relaxed_by_nearby_print(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        _,image,o=actual(2)
        o['preserve_regions'].append(dict(kind='unknown',bbox=[.40,.25,.70,.65],scope='EXACT_REGION'))
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):
            executed,_=self.prepare(image,o);mask_for((800,800),executed,image=image)

    def test_policy_opt_out_retains_old_generic_input(self):
        _,image,o=actual(3);executed,plan=self.prepare(image,o,prefer_repeated_glyphs=False,covered_print_policy='EXACT')
        self.assertEqual(executed,o);self.assertFalse(plan['groups'])

    def test_one_region_has_no_implicit_image_search(self):
        _,image,o=actual(3);o['watermarks']=[o['watermarks'][0]];o['preserve_regions']=[]
        executed,plan=self.prepare(image,o)
        self.assertFalse(plan['groups']);self.assertNotIn('glyph_search_scope',executed['watermarks'][0])

    def test_filled_shapes_do_not_become_global_letter_templates(self):
        from watermark_module_fixtures import sample
        with tempfile.TemporaryDirectory() as d:
            request=sample(d,boxes=[[.02,.1,.12,.16],[.76,.6,.9,.65]],complexity='COMPLEX')
            image=np.array(Image.open(request['image_path']).convert('RGB'))
            executed,plan=self.prepare(image,request)
            self.assertFalse(plan['groups']);self.assertEqual(executed['watermarks'],request['watermarks'])

    def test_no_usable_explicit_samples_can_return_to_bounded_regions(self):
        from test_general_text_watermarks import text_fixture
        with tempfile.TemporaryDirectory() as d:
            request,_,_=text_fixture(d,multiple=True);image=np.array(Image.open(request['image_path']).convert('RGB'))
            observation=dict(watermarks=request['watermarks'][:2],preserve_regions=[],decision='REMOVE_TEXT',background_complexity='SMOOTH')
            for m in observation['watermarks']:m.update(repair_mode='TEMPLATE_GLYPHS',glyph_template_bbox=[0,.01,.05,.05])
            with patch('mye_c_automation.template_glyphs.repeated_template_strokes',side_effect=ValueError('GLYPH_TEMPLATE_BACKGROUND')):
                executed,plan=self.prepare(image,observation)
            self.assertFalse(plan['groups']);self.assertTrue(plan['sample_failures'])
            self.assertTrue(all(m['repair_mode']=='REGION' for m in executed['watermarks']))
            self.assertTrue(all('glyph_template_bbox' not in m for m in executed['watermarks']))

    def test_native_remove_text_records_derived_execution_and_preserves_source_pixels(self):
        from mye_c_automation.image_repairs_v2 import remove_text,deterministic_quality
        source,image,o=actual(3);before=copy.deepcopy(o);original=source.read_bytes()
        def backend(pixels,mask):pixels[mask>0]=0;return pixels
        with tempfile.TemporaryDirectory() as d:
            result=remove_text(source,o,Path(d)/'repair',rights='OWNED_OR_LICENSED',lama=backend)
            self.assertLess(result['mask_ratio'],.08)
            self.assertTrue(result['execution_plan']['groups']);self.assertTrue(result['execution_observation'])
            self.assertTrue(deterministic_quality(source,result['output_path'],result['mask_path'])['ok'])
            self.assertTrue((Path(d)/'repair/execution-plan.json').is_file())
        self.assertEqual(o,before);self.assertEqual(source.read_bytes(),original)

    def test_explicit_glyph_path_obeys_nested_mask_cap_before_loading_lama(self):
        from test_global_watermark_flow import global_observation
        from mye_c_automation.image_repairs_v2 import remove_text
        image,o,_=global_observation();calls=[]
        def backend(image,mask):calls.append(True);return image
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.png';Image.fromarray(image).save(source)
            with self.assertRaisesRegex(ValueError,'MASK_AREA'):
                remove_text(source,o,Path(d)/'repair',rights='OWNED_OR_LICENSED',lama=backend,
                    processing_policy=dict(max_mask_area=.001))
        self.assertFalse(calls)

    def test_current_fake_workflow_reviews_actual_executed_pattern_and_never_uploads_quality_failure(self):
        from test_v2_workflow import V2WorkflowTests
        source,_,o=actual(3)
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':
                row['watermarks']=copy.deepcopy(o['watermarks']);row['preserve_regions']=copy.deepcopy(o['preserve_regions'])
            return row
        def backend(pixels,mask):pixels[mask>0]=0;return pixels
        for fail in (False,'identity'):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as d:
                root=Path(d);model=root/'fake.pt';model.write_bytes(b'fake weights')
                with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:source},
                        observation_transform=transform,image_options={'lama_model_path':str(model)},quality_fail=fail)
                self.assertEqual(result['writer'].uploads,0 if fail else 1)
                self.assertIn('image_quality_v2',result['calls'])
