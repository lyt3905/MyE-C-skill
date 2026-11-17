import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from watermark_module_fixtures import sample, varied_sample


class WatermarkModuleTests(unittest.TestCase):
    def test_plain_background_after_removal_is_pending_not_a_content_verdict(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d)
            image=Image.new('RGB',(320,240),'white');from PIL import ImageDraw
            ImageDraw.Draw(image).rectangle((16,36,60,52),fill='red');image.save(r['image_path'])
            r['image_sha256']=hashlib.sha256(Path(r['image_path']).read_bytes()).hexdigest()
            def backend(im,mask):return np.full_like(im,255)
            result=api.process_watermarks(r,Path(d)/'out',lama=backend,algorithm='LAMA_INPAINT')
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')
            from mye_c_automation.visual_quality import VisualQualityInspector
            inspector=VisualQualityInspector(Path(d),{},judge=object())
            checked=inspector.inspect_v2(r['image_path'],result['output_path'],{},'REMOVE_TEXT',result['mask_paths'][0],observation=r)
            self.assertFalse(checked['ok']);self.assertEqual(checked['quality_status'],'FAIL_UNKNOWN')

    def test_non_rectangular_polygon_preserves_pixels_in_bounding_box_corners(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);m=r['watermarks'][0];m.pop('bbox');m.update(region_type='POLYGON',polygon=[[.04,.1],[.2,.18],[.18,.23],[.02,.15]])
            result=api.process_watermarks(r,Path(d)/'out',policy=dict(dilation=0))
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            mask=np.array(Image.open(result['mask_paths'][0]));self.assertEqual(mask[24,63],0);self.assertEqual(mask[38,31],255)

    def test_all_explicit_factory_and_structure_regions_remain_protected(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for kind in ['MANUFACTURER_LOGO','PRODUCT_PRINT','MODEL_TEXT','PACKAGING_PRINT','MECHANICAL_STRUCTURE','ACCESSORY']:
                r=sample(Path(d)/kind);r['preserve_regions']=[dict(kind=kind,bbox=r['watermarks'][0]['bbox'])]
                result=api.process_watermarks(r,Path(d)/(kind+'-out'))
                self.assertEqual(result['processing_status'],'BLOCKED');self.assertIn('PROTECTED',result['failure_reason'])

    def test_supplemental_union_is_revalidated_and_uses_original_context(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,complexity='COMPLEX');seen=[]
            def backend(im,mask):seen.append(im.copy());im[mask>0]=0;return im
            first=api.process_watermarks(r,Path(d)/'first',lama=backend)
            r2=copy.deepcopy(r);r2['watermarks'][0]['bbox']=[.72,.6,.84,.67]
            second=api.process_watermarks(r2,Path(d)/'second',lama=backend,mask_source=first['output_path'],prior_mask=first['mask_paths'][0])
            self.assertEqual(second['processing_status'],'PROCESSED',second)
            before=np.array(Image.open(r['image_path']).convert('RGB'))
            for record,image in zip(second['regions'],seen[1:]):
                x0,y0,x1,y1=record['roi'];self.assertTrue(np.array_equal(image,before[y0:y1,x0:x1]))
            m1=np.array(Image.open(first['mask_paths'][0]));m2=np.array(Image.open(second['mask_paths'][0]));self.assertTrue(np.all(m2[m1>0]>0))

    def test_failed_second_region_retains_actual_execution_records(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.12,.2],[.74,.6,.9,.7]],complexity='COMPLEX');calls=[]
            def backend(image,mask):
                calls.append(image.shape)
                if len(calls)==2:raise RuntimeError('second ROI failed')
                image[mask>0]=0;return image
            result=api.process_watermarks(r,Path(d)/'out',lama=backend)
            self.assertEqual(result['processing_status'],'FAILED')
            self.assertEqual([x['status'] for x in result['regions']],['PROCESSED','FAILED'])
            self.assertIn('second ROI failed',result['regions'][-1]['failure_reason'])

    def test_cached_roi_reuses_existing_cache_and_tamper_recomputes(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=sample(root,complexity='COMPLEX');calls=[]
            def backend(image,mask):calls.append(image.shape);image[mask>0]=0;return image
            backend.model_sha256='1'*64
            first=api.process_watermarks(r,root/'one',lama=backend,cache_dir=root/'cache')
            second=api.process_watermarks(r,root/'two',lama=backend,cache_dir=root/'cache')
            self.assertEqual(len(calls),1);self.assertTrue(second['regions'][0]['cache_hit'])
            self.assertEqual(first['output_sha256'],second['output_sha256'])
            next((root/'cache').glob('*.json')).write_text('{}')
            third=api.process_watermarks(r,root/'three',lama=backend,cache_dir=root/'cache')
            self.assertEqual(len(calls),2);self.assertEqual(third['processing_status'],'PROCESSED')

    def test_output_schema_and_outside_mask_changes_are_checked(self):
        api=self.module()
        from mye_c_automation.resources import validate_resource_json
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);result=api.process_watermarks(r,Path(d)/'out')
            validate_resource_json(result,'watermark-processing-output.v1.schema.json')
            path=Path(result['output_path']);im=Image.open(path).convert('RGB');im.putpixel((319,239),(1,2,3));im.save(path)
            result['output_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            checked=api.WatermarkQualityChecker().check(r,result)
            self.assertFalse(checked['ok']);self.assertEqual(checked['reason'],'OUTSIDE_MASK_CHANGED')

    def module(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('mye_c_automation.watermark_processing'),'Generic API missing')
        from mye_c_automation import watermark_processing
        return watermark_processing

    def test_contract_path_bytes_binding_and_zero_confidence(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);before=copy.deepcopy(r)
            a=api.WatermarkInputParser().parse(r)
            self.assertEqual(a.sha256,r['image_sha256']);self.assertEqual(a.instances[0]['confidence'],0)
            raw=Path(r.pop('image_path')).read_bytes();r['image_bytes']=raw
            b=api.WatermarkInputParser().parse(r)
            self.assertTrue(np.array_equal(a.pixels,b.pixels));self.assertEqual(before['watermarks'],r['watermarks'])

    def test_parser_rejects_wrong_sha_size_ambiguous_input_and_duplicate_ids(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.12,.2],[.7,.6,.8,.7]])
            cases=[]
            for key,value in [('image_sha256','a'*64),('image_width',321),('schema_version','other'),('image_height',True)]:
                x=copy.deepcopy(r);x[key]=value;cases.append(x)
            x=copy.deepcopy(r);x['image_bytes']=Path(r['image_path']).read_bytes();cases.append(x)
            x=copy.deepcopy(r);x['watermarks'][1]['watermark_id']=x['watermarks'][0]['watermark_id'];cases.append(x)
            x=copy.deepcopy(r);x['descriptionJson']='not an image input';cases.append(x)
            for x in cases:
                with self.subTest(keys=x.keys()),self.assertRaises(ValueError):api.WatermarkInputParser().parse(x)

    def test_bad_polygon_bbox_and_self_intersection_block_before_backend(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for region in [dict(polygon=[[0,0],[1,1],[0,1],[1,0]]),dict(polygon=[[0,0],[.9,.9],[0,.8],[.8,0],[1,1]]),dict(bbox=[-.1,0,.2,.2]),dict(bbox=[.3,.3,.1,.4]),dict()]:
                r=sample(Path(d)/str(len(list(Path(d).iterdir()))));m=r['watermarks'][0];m.pop('bbox');m.pop('region_type');m.update(region)
                backend=lambda *_:self.fail('Invalid geometry reached inference')
                result=api.process_watermarks(r,Path(d)/('out'+str(len(list(Path(d).iterdir())))),lama=backend)
                self.assertEqual(result['processing_status'],'BLOCKED');self.assertEqual(result['quality_status'],'REVIEW')

    def test_region_manager_separates_distant_same_group_and_preserves_ids(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.10,.16],[.105,.10,.18,.16],[.76,.65,.9,.72]])
            result=api.process_watermarks(r,Path(d)/'out')
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(len(result['regions']),2)
            self.assertEqual(sorted(i for g in result['regions'] for i in g['instance_ids']),['instance-0','instance-1','instance-2'])
            self.assertEqual(result['watermark_instances_processed'],3)
            mask=np.array(Image.open(result['mask_paths'][0]));self.assertFalse(mask[100,160])

    def test_adjacent_different_groups_are_not_merged(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.10,.16],[.105,.10,.18,.16]])
            r['watermarks'][1]['group_id']='different'
            result=api.process_watermarks(r,Path(d)/'out');self.assertEqual(len(result['regions']),2)

    def test_configurable_roi_and_mask_area_limits_are_not_silently_relaxed(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d)
            for policy in [dict(max_mask_area=.001),dict(max_roi_area=.001),dict(dilation=-1),dict(unknown=1)]:
                result=api.process_watermarks(r,Path(d)/('o'+str(len(list(Path(d).iterdir())))),policy=policy)
                self.assertEqual(result['processing_status'],'BLOCKED',result)

    def test_protection_rights_and_ai_semantic_conflicts_stop(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for n,mode in enumerate(['RIGHTS_UNKNOWN','THIRD_PARTY_ATTRIBUTION','protect','manufacturer','unknown','risk']):
                r=sample(Path(d)/str(n))
                if mode in {'RIGHTS_UNKNOWN','THIRD_PARTY_ATTRIBUTION'}:r['authorization_status']=mode
                elif mode=='protect':r['preserve_regions'].append(dict(kind='PACKAGING_PRINT',bbox=r['watermarks'][0]['bbox']))
                elif mode=='manufacturer':r['watermarks'][0].update(kind='MANUFACTURER_LOGO',owner='MANUFACTURER')
                elif mode=='unknown':r['watermarks'][0].update(kind='UNKNOWN_TEXT',owner='UNKNOWN',action='KEEP')
                else:r['watermarks'][0]['preserve_overlap_risk']='HIGH'
                result=api.process_watermarks(r,Path(d)/('out'+str(n)),lama=lambda *_:self.fail('Guard bypass'))
                self.assertEqual(result['processing_status'],'BLOCKED',result)
                self.assertIsNone(result['output_path'])

    def test_router_uses_area_background_transparency_and_subject_information(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for i,(mode,extra,algorithm) in enumerate([('SMOOTH',{},'OPENCV_TELEA'),('COMPLEX',{},'LAMA_INPAINT'),('SMOOTH',dict(opacity=.4),'LAMA_INPAINT'),('SMOOTH',dict(subject_overlap=True),'LAMA_INPAINT')]):
                r=sample(Path(d)/str(i),complexity=mode);r['watermarks'][0].update(extra);calls=[]
                def backend(image,mask):calls.append(image.shape);image[mask>0]=255;return image
                result=api.process_watermarks(r,Path(d)/('out'+str(i)),lama=backend)
                self.assertEqual(result['algorithm_used'],[algorithm]);self.assertEqual(len(calls),int(algorithm=='LAMA_INPAINT'))
                self.assertTrue(result['regions'][0]['routing_reason'])

    def test_roi_calls_fuse_only_union_and_preserve_alpha_and_original(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,boxes=[[.02,.1,.12,.2],[.74,.6,.9,.7]],complexity='COMPLEX',alpha=True);source=Path(r['image_path']);before=source.read_bytes();calls=[]
            def backend(im,mask):calls.append((im.shape,mask.shape));return np.zeros_like(im)
            result=api.process_watermarks(r,Path(d)/'out',lama=backend)
            self.assertEqual(result['processing_status'],'PROCESSED',result);self.assertEqual(len(calls),2)
            self.assertTrue(all(shape[0]<240 and shape[1]<320 for shape,_ in calls))
            mask=np.array(Image.open(result['mask_paths'][0]))>0;original=np.array(Image.open(source).convert('RGBA'));output=np.array(Image.open(result['output_path']).convert('RGBA'))
            self.assertTrue(np.array_equal(original[~mask],output[~mask]));self.assertTrue(np.array_equal(original[:,:,3],output[:,:,3]));self.assertEqual(source.read_bytes(),before)
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW');self.assertEqual(result['output_sha256'],hashlib.sha256(Path(result['output_path']).read_bytes()).hexdigest())

    def test_eight_layouts_and_visual_variations_have_independent_sparse_masks(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for layout in ['SINGLE','REPEATED','DIAGONAL','HORIZONTAL','VERTICAL','GRID','SCATTERED','MIXED']:
                with self.subTest(layout=layout):
                    r=varied_sample(Path(d)/layout,layout,background='black' if len(layout)%2 else 'white')
                    def backend(im,mask):im[mask>0]=80;return im
                    result=api.process_watermarks(r,Path(d)/(layout+'-out'),lama=backend,policy=dict(max_mask_area=.25,max_roi_area=.55))
                    self.assertEqual(result['processing_status'],'PROCESSED',result)
                    self.assertEqual(result['watermark_instances_total'],len(r['watermarks']));self.assertEqual(result['watermark_instances_processed'],len(r['watermarks']))
                    self.assertTrue(Path(result['visualization_path']).is_file());self.assertGreaterEqual(len(result['mask_paths']),2)

    def test_missing_lama_invalid_output_and_inference_error_are_failures(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            for n,backend in enumerate([None,lambda *_:None,lambda im,m:np.zeros((1,1,3),dtype=np.uint8),lambda im,m:(_ for _ in ()).throw(RuntimeError('bad engine'))]):
                r=sample(Path(d)/str(n),complexity='COMPLEX');result=api.process_watermarks(r,Path(d)/('out'+str(n)),lama=backend)
                self.assertEqual(result['processing_status'],'FAILED',result);self.assertEqual(result['quality_status'],'FAIL');self.assertIsNone(result['output_path'])
                self.assertTrue(result['failure_reason'])

    def test_opencv_exception_and_unchanged_candidate_cannot_pass(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d)
            with patch('cv2.inpaint',side_effect=RuntimeError('opencv failed')):
                failed=api.process_watermarks(r,Path(d)/'failed')
            self.assertEqual(failed['processing_status'],'FAILED')
            with patch('cv2.inpaint',side_effect=lambda im,*_:im.copy()):
                unchanged=api.process_watermarks(r,Path(d)/'unchanged')
            self.assertEqual(unchanged['processing_status'],'FAILED');self.assertIn('UNCHANGED',unchanged['failure_reason'])

    def test_new_files_and_not_applicable_actions_preserve_existing_evidence(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);out=Path(d)/'out';first=api.process_watermarks(r,out)
            data=Path(first['output_path']).read_bytes();second=api.process_watermarks(r,out)
            self.assertEqual(second['processing_status'],'BLOCKED');self.assertEqual(Path(first['output_path']).read_bytes(),data)
            for action in ['KEEP','DELETE','REVIEW','AI_REGENERATE']:
                r['decision']=action;result=api.process_watermarks(r,Path(d)/action)
                self.assertEqual(result['processing_status'],'NOT_APPLICABLE');self.assertIsNone(result['output_path'])

    def test_quality_rejects_corrupt_mask_output_and_source_mutation(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d);result=api.process_watermarks(r,Path(d)/'out');checker=api.WatermarkQualityChecker()
            self.assertTrue(checker.check(r,result)['ok'])
            mask=Path(result['mask_paths'][0]);original=mask.read_bytes();mask.write_bytes(b'bad')
            self.assertFalse(checker.check(r,result)['ok']);mask.write_bytes(original)
            candidate=Path(result['output_path']);data=candidate.read_bytes();candidate.write_bytes(b'broken')
            self.assertFalse(checker.check(r,result)['ok']);candidate.write_bytes(data)
            source=Path(r['image_path']);source.write_bytes(b'changed');self.assertFalse(checker.check(r,result)['ok'])

    def test_model_backend_cannot_change_original_undetected(self):
        api=self.module()
        with tempfile.TemporaryDirectory() as d:
            r=sample(d,complexity='COMPLEX')
            def corrupt(image,mask):Path(r['image_path']).write_bytes(b'changed');image[mask>0]=0;return image
            result=api.process_watermarks(r,Path(d)/'out',lama=corrupt)
            self.assertEqual(result['processing_status'],'FAILED');self.assertIn('ORIGINAL_CHANGED',result['failure_reason'])
