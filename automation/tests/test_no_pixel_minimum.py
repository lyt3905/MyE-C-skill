import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


class NoPixelMinimumTests(unittest.TestCase):
    def test_small_images_complete_fake_sku_save_and_readback(self):
        from test_v2_workflow import V2WorkflowTests
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = {}
            for index in range(2):
                path = root/f'small-{index}.png'
                im = Image.new('RGB', (790, 526), 'white')
                ImageDraw.Draw(im).rectangle((50+index*30, 50, 200, 350), fill=['blue', 'red'][index])
                im.save(path); assets[index] = path
            scenario = V2WorkflowTests().scenario(root, ['KEEP', 'KEEP'], two_sku_rows=True, asset_images=assets)
            self.assertEqual(scenario['writer'].saves, 1)
            self.assertEqual(scenario['writer'].uploads, 0)
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(len({s['skuImageUrl'] for s in scenario['product']['skus']}), 2)

    def test_790_pixel_product_photo_can_fill_without_box_sku(self):
        from test_v2_repairs_sku import RepairSkuTests
        from mye_c_automation.sku_assignment import select_v2
        rows = RepairSkuTests().records()[:2]
        rows[0].update(width=790, height=526)
        rows[1]['observation'].update(retail_box_status='PRESENT')
        product = dict(skus=[dict(id='no', name='No retail box'), dict(id='yes', name='With retail box')])
        result = select_v2(product, rows)
        self.assertEqual(result['assignments'], {'no': rows[0]['url'], 'yes': rows[1]['url']})
        self.assertNotIn('SKU_NO_NONBOX_IMAGE', result['reason_codes'])
        rows[0]['decision'] = 'REVIEW'
        self.assertNotIn('no', select_v2(product, rows)['assignments'])

    def test_clean_same_photo_candidate_has_no_pixel_minimum(self):
        from mye_c_automation.visual_versions import clean_candidate
        value = dict(decision='KEEP', observation=dict(abstain=False))
        self.assertTrue(clean_candidate(value, dict(width=790, height=526, format='JPEG')))
        self.assertFalse(clean_candidate(dict(value, decision='REVIEW'), dict(width=790, height=526, format='JPEG')))

    def test_small_local_repair_still_checks_outside_mask(self):
        from mye_c_automation.image_repairs_v2 import deterministic_quality
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, mask = (root/n for n in ('source.png', 'candidate.png', 'mask.png'))
            im = Image.new('RGB', (790, 526), 'white')
            ImageDraw.Draw(im).rectangle((30, 30, 80, 80), fill='blue')
            im.save(source)
            ImageDraw.Draw(im).rectangle((10, 10, 15, 15), fill='red')
            im.save(output)
            m = np.zeros((526, 790), dtype=np.uint8); m[10:16, 10:16] = 255
            Image.fromarray(m).save(mask)
            self.assertTrue(deterministic_quality(source, output, mask)['ok'])
            ImageDraw.Draw(im).point((100, 100), fill='black'); im.save(output)
            self.assertEqual(deterministic_quality(source, output, mask)['reason'], 'OUTSIDE_MASK_CHANGED')

    def test_upload_dry_run_accepts_small_decodable_image(self):
        from mye_c_automation.executor.service import ExecutorService
        from mye_c_automation.product_state import canonical_state_hash
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'image.png'
            Image.new('RGB', (790, 526), 'blue').save(path)
            ref = dict(path='image.png', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            plan = dict(schema='token-opt-plan/v2', job_id='JOB_small', pid=1, shop=7,
                workflow_version='token-opt-v2', policy_version='v2',
                precondition=dict(state_sha256=canonical_state_hash(dict(images={}))),
                evidence_refs=[ref], ai_judgement_refs=[], desired=dict(images=dict(main=['pending'])),
                post_actions=dict(uploads=[dict(ref, pool='main', index=0)]), review=dict(status='RESOLVED'))
            result = ExecutorService(None, None, root).execute(plan)
            self.assertTrue(result['dry_run'])
            self.assertEqual(result['upload_calls'], 0)
