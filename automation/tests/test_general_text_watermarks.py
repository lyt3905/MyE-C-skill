import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageFont


def text_fixture(root,*,large=False,multiple=False,alpha=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    w,h=(640,400) if large else (480,320)
    clean=Image.new('RGB',(w,h),(32,38,44) if large else (240,240,240))
    ImageDraw.Draw(clean).rectangle((int(w*.74),int(h*.77),int(w*.9),int(h*.94)),fill=(25,95,160))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',74 if large else 30)
    places=[(18,70,'WATERMARK\nSAMPLE 42')] if large else [(30,35,'ALPHA 73')]
    if multiple:places+=[(265,145,'ALPHA 73'),(35,245,'VIOLET 8')]
    layer=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(layer);marks=[]
    for i,(x,y,text) in enumerate(places):
        ink=(180,75,145,75 if large else 180);draw.text((x,y),text,font=font,fill=ink,spacing=8)
        b=draw.textbbox((x,y),text,font=font,spacing=8);pad=6
        marks.append(dict(kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',action='REMOVE_TEXT',repair_mode='REGION',
            watermark_id='text-'+str(i),group_id='a' if i<2 else 'b',content_type='TEXT',arrangement='REPEATED' if multiple else 'SINGLE',
            bbox=[max(0,b[0]-pad)/w,max(0,b[1]-pad)/h,min(w,b[2]+pad)/w,min(h,b[3]+pad)/h],
            confidence=0.,preserve_overlap_risk='HIGH',opacity=ink[3]/255,subject_overlap=False))
    source=Image.alpha_composite(clean.convert('RGBA'),layer)
    if alpha:
        source.putalpha(Image.fromarray(np.tile(np.arange(w,dtype=np.uint16)%256,(h,1)).astype(np.uint8)))
    else:source=source.convert('RGB')
    path=root/'original.png';source.save(path)
    request=dict(schema_version='watermark-processing.v1',image_path=str(path),image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        image_width=w,image_height=h,decision='REMOVE_TEXT',authorization_status='OWNED_OR_LICENSED',watermarks=marks,
        preserve_regions=[],background_complexity='COMPLEX' if large else 'SMOOTH')
    return request,np.array(layer)[:,:,3]>32,np.array(clean)


class GeneralTextWatermarkTests(unittest.TestCase):
    @staticmethod
    def restore_plain_background(image,mask):
        image[mask>0]=[240,240,240]
        return image

    def process(self,request,out,**kw):
        from mye_c_automation.watermark_processing import process_watermarks
        return process_watermarks(request,out,**kw)

    def test_single_text_selects_its_own_glyphs_without_a_manual_sample(self):
        with tempfile.TemporaryDirectory() as d:
            r,truth,_=text_fixture(Path(d)/'input')
            result=self.process(r,Path(d)/'out',lama=self.restore_plain_background)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            plans=result.get('mask_plans',[]);self.assertTrue(plans)
            self.assertEqual(plans[0]['strategy'],'AUTO_TEXT_GLYPHS')
            mask=np.array(Image.open(result['mask_paths'][0]))>0
            self.assertGreater(np.count_nonzero(mask&truth)/np.count_nonzero(truth),.98)
            box=r['watermarks'][0]['bbox'];w,h=r['image_width'],r['image_height']
            self.assertLess(mask.sum(),.65*(box[2]-box[0])*(box[3]-box[1])*w*h)
            self.assertNotIn('glyph_template_bbox',r['watermarks'][0])

    def test_uniform_background_removes_inpaint_shadows_only_within_auto_glyph_mask(self):
        with tempfile.TemporaryDirectory() as d:
            r,_,clean=text_fixture(Path(d)/'input',large=True)
            def tinted_backend(image,mask):image[mask>0]=[80,65,75];return image
            result=self.process(r,Path(d)/'out',lama=tinted_backend)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            output=np.array(Image.open(result['output_path']))
            self.assertTrue(np.array_equal(output,clean))
            self.assertGreater(result.get('uniform_background_cleanup_components',0),0)

    def test_multiple_texts_and_different_groups_keep_independent_source_regions(self):
        with tempfile.TemporaryDirectory() as d:
            r,truth,_=text_fixture(Path(d)/'input',multiple=True)
            before=copy.deepcopy(r);result=self.process(r,Path(d)/'out',lama=self.restore_plain_background)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(len(result.get('mask_plans',[])),3)
            self.assertEqual(r,before)
            mask=np.array(Image.open(result['mask_paths'][0]))>0
            self.assertGreater(np.count_nonzero(mask&truth)/np.count_nonzero(truth),.98)
            self.assertEqual({p['group_id'] for p in result['mask_plans']},{'a','b'})

    def test_same_group_can_supply_a_reference_when_own_background_is_not_uniform(self):
        with tempfile.TemporaryDirectory() as d:
            r,truth,_=text_fixture(Path(d)/'input',multiple=True)
            source=np.array(Image.open(r['image_path']));b=r['watermarks'][0]['bbox'];h,w=source.shape[:2]
            x0,y0,x1,y1=0,0,210,h
            perturb=((np.arange(x1-x0)%17)/16*90).astype(np.int16)
            source[y0:y1,x0:x1]=np.clip(source[y0:y1,x0:x1].astype(np.int16)-perturb[None,:,None],0,255).astype(np.uint8)
            Image.fromarray(source).save(r['image_path']);r['image_sha256']=hashlib.sha256(Path(r['image_path']).read_bytes()).hexdigest()
            result=self.process(r,Path(d)/'out',lama=self.restore_plain_background)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            first=result['mask_plans'][0]
            self.assertEqual(first['strategy'],'AUTO_TEXT_GLYPHS')
            self.assertEqual(first['sample_instance_id'],'text-1')
            self.assertTrue(first['sample_failures'])

    def test_overlapping_tiles_blend_estimates_instead_of_using_last_tile(self):
        from watermark_module_fixtures import sample
        with tempfile.TemporaryDirectory() as d:
            r=sample(Path(d)/'input',boxes=[[.02,.4,.98,.44]],complexity='COMPLEX');r['watermarks'][0]['content_type']='GRAPHIC';calls=[]
            def backend(image,mask):
                calls.append(True);image[mask>0]=20 if len(calls)%2 else 220;return image
            result=self.process(r,Path(d)/'out',lama=backend,policy=dict(max_roi_area=.045,context_pixels=8,tile_overlap_pixels=8))
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            mask=np.array(Image.open(result['mask_paths'][0]))>0;output=np.array(Image.open(result['output_path']))
            self.assertTrue(np.any((output[mask,0]>20)&(output[mask,0]<220)))

    def test_large_translucent_text_uses_sparse_mask_and_bounded_lama_tiles(self):
        with tempfile.TemporaryDirectory() as d:
            r,truth,_=text_fixture(Path(d)/'input',large=True);calls=[]
            def backend(image,mask):calls.append(image.shape);image[mask>0]=[32,38,44];return image
            result=self.process(r,Path(d)/'out',lama=backend,policy=dict(max_roi_area=.16,context_pixels=12,tile_overlap_pixels=16))
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertGreater(len(calls),1);self.assertEqual(result['algorithm_used'],['LAMA_INPAINT'])
            self.assertTrue(all(row['routing_reason']['roi_area']<=.16 for row in result['regions']))
            mask=np.array(Image.open(result['mask_paths'][0]))>0
            self.assertGreater(np.count_nonzero(mask&truth)/np.count_nonzero(truth),.98)
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')

    def test_large_instance_is_tiled_without_silently_raising_roi_limit(self):
        from watermark_module_fixtures import sample
        with tempfile.TemporaryDirectory() as d:
            r=sample(Path(d)/'input',boxes=[[.02,.4,.98,.44]],complexity='COMPLEX')
            r['watermarks'][0]['content_type']='GRAPHIC';calls=[]
            def backend(image,mask):calls.append(image.shape);image[:]=[97,101,105];return image
            result=self.process(r,Path(d)/'out',lama=backend,policy=dict(max_roi_area=.045,context_pixels=8,tile_overlap_pixels=8))
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertGreater(len(calls),1)
            self.assertTrue(all(row['routing_reason']['roi_area']<=.045 for row in result['regions']))
            output=np.array(Image.open(result['output_path']));source=np.array(Image.open(r['image_path']))
            mask=np.array(Image.open(result['mask_paths'][0]))>0
            self.assertTrue(np.array_equal(source[~mask],output[~mask]))
            self.assertTrue(np.all(output[mask]==[97,101,105]))

    def test_no_valid_text_reference_falls_back_without_changing_ai_labels(self):
        from watermark_module_fixtures import sample
        with tempfile.TemporaryDirectory() as d:
            r=sample(Path(d)/'input');before=copy.deepcopy(r)
            result=self.process(r,Path(d)/'out')
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(result.get('mask_plans',[{}])[0].get('strategy'),'BOUNDED_REGION_FALLBACK')
            self.assertTrue(result['mask_plans'][0]['sample_failures'])
            self.assertEqual(r,before)

    def test_region_strategy_can_be_explicitly_retained(self):
        with tempfile.TemporaryDirectory() as d:
            r,_,_=text_fixture(Path(d)/'input')
            result=self.process(r,Path(d)/'out',lama=self.restore_plain_background,policy=dict(auto_text_masks=False))
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(result['mask_plans'][0]['strategy'],'EXPLICIT_REGION')

    def test_auto_text_preserves_alpha_and_actual_protected_pixels(self):
        with tempfile.TemporaryDirectory() as d:
            r,_,_=text_fixture(Path(d)/'input',alpha=True)
            result=self.process(r,Path(d)/'out',lama=self.restore_plain_background)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            source=np.array(Image.open(r['image_path']));output=np.array(Image.open(result['output_path']))
            self.assertTrue(np.array_equal(source[:,:,3],output[:,:,3]))
            r['preserve_regions']=[dict(kind='MANUFACTURER_LOGO',bbox=r['watermarks'][0]['bbox'])]
            blocked=self.process(r,Path(d)/'protected',lama=lambda *_:self.fail('Protection bypass'))
            self.assertEqual(blocked['processing_status'],'BLOCKED',blocked)

    def test_unachievable_tile_context_and_mask_limit_remain_explicit_failures(self):
        with tempfile.TemporaryDirectory() as d:
            r,_,_=text_fixture(Path(d)/'input',large=True)
            for i,policy in enumerate([dict(max_roi_area=.0001),dict(max_mask_area=.0001)]):
                result=self.process(r,Path(d)/str(i),lama=lambda *_:self.fail('Limit bypass'),policy=policy)
                self.assertEqual(result['processing_status'],'BLOCKED',result)

    def test_tile_and_auto_settings_reject_unrecognized_or_invalid_values(self):
        from mye_c_automation.watermark_processing.contracts import policy_options
        self.assertTrue(policy_options()['auto_text_masks'])
        for value in [dict(tile_overlap_pixels=-1),dict(auto_text_masks='true'),dict(tile_large_regions='true')]:
            with self.assertRaises(ValueError):policy_options(value)

    def test_tiled_backend_failure_does_not_count_partly_processed_instance(self):
        from watermark_module_fixtures import sample
        with tempfile.TemporaryDirectory() as d:
            r=sample(Path(d)/'input',boxes=[[.02,.4,.98,.44]],complexity='COMPLEX');r['watermarks'][0]['content_type']='GRAPHIC';calls=[]
            def backend(image,mask):
                calls.append(True)
                if len(calls)==2:raise RuntimeError('second tile failed')
                image[mask>0]=255;return image
            result=self.process(r,Path(d)/'out',lama=backend,policy=dict(max_roi_area=.045,context_pixels=8,tile_overlap_pixels=8))
            self.assertEqual(len(calls),2);self.assertEqual(result['processing_status'],'FAILED')
            self.assertEqual(result['watermark_instances_processed'],0)
            self.assertIsNone(result['output_path'])

    def test_current_job_freezes_auto_text_and_tiling_settings(self):
        from mye_c_automation.job_manager import JobManager
        with tempfile.TemporaryDirectory() as d:
            options=dict(auto_text_masks=True,tile_large_regions=True,tile_overlap_pixels=20)
            job=JobManager(Path(d)/'jobs').create(1,7,{},image_workflow='v2',image_options=dict(watermark_processing=options))
            self.assertEqual(job['image_options']['watermark_processing']['tile_overlap_pixels'],20)

    def test_native_workflow_uses_automatic_masks_and_actual_quality_gate(self):
        from unittest.mock import patch
        from test_v2_workflow import V2WorkflowTests
        for quality in [False,'identity']:
            with self.subTest(quality=quality),tempfile.TemporaryDirectory() as d:
                root=Path(d);r,_,_=text_fixture(root/'fixture');model=root/'fake.pt';model.write_bytes(b'Fake backend')
                def transform(row,item):
                    if row['decision']=='REMOVE_TEXT':row.update(watermarks=copy.deepcopy(r['watermarks']),preserve_regions=[],background_complexity='SMOOTH')
                    return row
                with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=self.restore_plain_background):
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:r['image_path']},
                        observation_transform=transform,image_options=dict(lama_model_path=str(model),watermark_processing=dict(auto_text_masks=True)),quality_fail=quality)
                self.assertGreaterEqual(result['calls'].count('image_quality_v2'),1)
                self.assertEqual(result['writer'].uploads,0 if quality else 1)
                import json
                receipt=next(result['root'].glob('v2_candidates/**/processing-result.json'))
                plans=json.loads(receipt.read_text(encoding='utf-8'))['mask_plans']
                self.assertEqual(plans[0]['strategy'],'AUTO_TEXT_GLYPHS')
                quality_rows=json.loads((result['root']/'v2_quality.json').read_text(encoding='utf-8'))
                self.assertEqual(quality_rows['items'][0]['repair']['execution_observation']['watermarks'][0]['repair_mode'],'TEMPLATE_GLYPHS')
