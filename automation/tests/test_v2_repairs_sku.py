import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from test_v2_vision import observation


class RepairSkuTests(unittest.TestCase):
    def records(self):
        rows=[]
        for n in range(3):
            item=dict(id='IMG_'+str(n),sha256=str(n)*64,image_type='MAIN',evidence_ids=['S'])
            rows.append(dict(sha256=item['sha256'],url='https://fake/'+str(n),image_id=item['id'],
                observation=observation(item,angle=['FRONT','FRONT','SIDE'][n]),decision='KEEP',width=800,height=800))
        return rows

    def test_no_box_distinct_angles_and_actual_id_single_reference(self):
        from mye_c_automation.sku_assignment import select_v2
        result=select_v2({'skus':[{'skuId':'real1','skuName':'Without Box'}]},self.records())
        self.assertEqual([r['sha256'][0] for r in result['selected_sku_images']],['0','2'])
        self.assertEqual(result['assignments'],{'real1':'https://fake/0'})
        self.assertIn('SITE_SINGLE_IMAGE_REFERENCE',result['reason_codes'])

    def test_missing_id_no_snapshot_row_substitution(self):
        from mye_c_automation.sku_assignment import select_v2
        result=select_v2({'skus':[{'skuName':'Without Box'}]},self.records())
        self.assertFalse(result['assignments']);self.assertIn('SKU_MAPPING_UNRESOLVED',result['reason_codes'])

    def test_box_prefers_ai_toy_photo_flag_without_class_or_confidence_ranking(self):
        from mye_c_automation.sku_assignment import select_v2
        rows=self.records()
        for n,row in enumerate(rows[:2]):
            row['observation'].update(visual_class=['RETAIL_BOX_ONLY','TOY_WITH_RETAIL_BOX'][n],retail_box_status='PRESENT',box_relation='SAME_PRODUCT',retail_box_bbox=[.2,.2,.8,.8],retail_box_confidence=.8)
            row['observation']['sku_suitability'].update(is_retail_box_photo=True,is_toy_photo=n==1)
        result=select_v2({'skus':[{'id':4,'name':'With Retail Box'}]},rows)
        self.assertEqual(result['assignments'],{'4':'https://fake/1'})

    def test_uncertain_preserves_mapping_and_shortage_not_duplicated(self):
        from mye_c_automation.sku_assignment import select_v2
        rows=self.records()[:1]
        result=select_v2({'skus':[{'id':4}]},rows)
        self.assertEqual(len(result['selected_sku_images']),1);self.assertIn('SKU_IMAGE_SHORTAGE=1_OF_2',result['reason_codes'])
        rows[0]['decision']='REVIEW';rows[0]['observation']['retail_box_status']='UNCERTAIN'
        self.assertFalse(select_v2({'skus':[{'id':4}]},rows)['assignments'])

    def test_mask_repair_preserves_outside_and_original(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';im=Image.new('RGB',(800,800),'white')
            ImageDraw.Draw(im).text((20,740),'STORE',fill='red');im.save(source);original=source.read_bytes()
            item=dict(id='I',sha256='a'*64,image_type='MAIN',evidence_ids=['S'])
            mark=dict(kind='STORE_WATERMARK',bbox=[.02,.92,.12,.95],confidence=.95,preserve_overlap_risk='LOW')
            obs=observation(item,'REMOVE_TEXT',watermarks=[mark])
            result=remove_text(source,obs,root/'out',rights='OWNED_OR_LICENSED')
            mask=np.array(Image.open(result['mask_path']))>0
            before=np.array(Image.open(source));after=np.array(Image.open(result['output_path']))
            self.assertTrue(np.array_equal(before[~mask],after[~mask]));self.assertFalse(np.array_equal(before,after))
            self.assertEqual(source.read_bytes(),original)
            with self.assertRaisesRegex(ValueError,'RIGHTS'):
                remove_text(source,obs,root/'unknown',rights='RIGHTS_UNKNOWN')
            obs['preserve_regions']=[dict(kind='PRODUCT_PRINT',bbox=mark['bbox'])]
            with self.assertRaisesRegex(ValueError,'PROTECTED'):
                remove_text(source,obs,root/'protected',rights='OWNED_OR_LICENSED',processing_policy={'protection_overlap_trial':False})

    def test_large_complex_requires_configured_lama(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'s.png';Image.new('RGB',(800,800),'white').save(p)
            item=dict(id='I',sha256='a'*64,image_type='MAIN',evidence_ids=['S'])
            obs=observation(item,'REMOVE_TEXT',background_complexity='COMPLEX',watermarks=[dict(kind='STORE_WATERMARK',bbox=[.05,.05,.35,.35],confidence=.95,preserve_overlap_risk='LOW')])
            with self.assertRaisesRegex(ValueError,'LAMA_UNAVAILABLE'):remove_text(p,obs,root/'out',rights='OWNED_OR_LICENSED')

    def test_ai_suitability_controls_candidates_not_class_whitelist_or_box_relation(self):
        from mye_c_automation.sku_assignment import select_v2
        for visual_class in ('ACCESSORY','PART_OR_COMPONENT','INFO_GRAPHIC','LIFESTYLE_OR_SCENE','OTHER','UNKNOWN','RETAIL_BOX_ONLY'):
            with self.subTest(visual_class=visual_class):
                rows=self.records()[:1];rows[0]['observation']['visual_class']=visual_class
                result=select_v2({'skus':[{'id':'real'}]},rows)
                self.assertTrue(result['selected_sku_images']);self.assertTrue(result['assignments'])
                rows[0]['observation']['sku_suitability'].update(is_toy_photo=False,is_retail_box_photo=False)
                result=select_v2({'skus':[{'id':'real'}]},rows)
                self.assertFalse(result['selected_sku_images']);self.assertFalse(result['assignments'])
        rows=self.records()[:1];rows[0]['observation'].update(retail_box_status='PRESENT',box_relation='UNRELATED',retail_box_bbox=[.1,.1,.2,.2])
        self.assertEqual(select_v2({'skus':[{'id':'real'}]},rows)['sku_packaging_decision'],'WITH_RETAIL_BOX')

    def test_same_sha_different_urls_not_two_images_and_ambiguous_ids_not_guessed(self):
        from mye_c_automation.sku_assignment import select_v2
        rows=self.records()[:1];other=copy.deepcopy(rows[0]);other['url']='https://fake/duplicate';rows.append(other)
        result=select_v2({'skus':[{'id':'A'},{'id':'B'}]},rows)
        self.assertEqual(len(result['selected_sku_images']),1);self.assertFalse(result['assignments'])

    def test_fake_lama_is_distinct_from_real_model_validation(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=root/'s.png';Image.new('RGB',(800,800),'gray').save(p)
            item=dict(id='I',sha256='a'*64,image_type='MAIN',evidence_ids=['S'])
            obs=observation(item,'REMOVE_TEXT',background_complexity='COMPLEX',watermarks=[dict(kind='STORE_WATERMARK',bbox=[.05,.05,.35,.35],confidence=.95,preserve_overlap_risk='LOW')])
            def fake_lama(image,mask):image[mask>0]=200;return image
            result=remove_text(p,obs,root/'out',rights='OWNED_OR_LICENSED',lama=fake_lama)
            self.assertEqual(result['algorithm'],'LAMA_INPAINT');self.assertNotEqual(result['input_sha256'],result['output_sha256'])

    def test_blank_and_transparent_candidates_are_rejected(self):
        from mye_c_automation.image_repairs_v2 import deterministic_quality
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);before=root/'before.png';out=root/'after.png'
            im=Image.new('RGB',(800,800),'white');ImageDraw.Draw(im).rectangle((20,20,50,50),fill='red');im.save(before)
            for mode,color in [('RGB','white'),('RGBA',(10,20,30,0))]:
                Image.new(mode,(800,800),color).save(out)
                self.assertFalse(deterministic_quality(before,out)['ok'])


if __name__=='__main__':unittest.main()
