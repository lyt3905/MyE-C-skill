"""Three-pass OCR, residual/template evidence and independent dual-model review."""
from mye_c_automation.policy_engine import MODEL_CONFIDENCE_MIN
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.candidate_quality import sha256

class VisualQualityInspector:
    def __init__(self,directory,job,judge=None,ocr_engine=None):
        self.root=Path(directory);self.job=job;self.engine=ocr_engine;self.budget=None
        import uuid
        self.metrics_phase=uuid.uuid4().hex
        if judge is None:
            from mye_c_automation.budget_manager import BudgetManager
            from mye_c_automation.ai_judge import JudgeClient
            self.budget=BudgetManager(job['budget'],self.root/'budget.sqlite')
            model_options={'config':job['model_config']} if 'model_config' in job else {}
            judge=JudgeClient(self.budget,self.root.parent/'shared_judge_cache',**model_options)
        self.judge=judge
        self.evidence=self.root/'quality_evidence';self.evidence.mkdir(exist_ok=True)

    def close(self):
        if self.budget: self.budget.close()

    def inspect_v2(self,source,candidate,context,action,mask=None,*,observation=None):
        """Vision-only semantics plus deterministic bytes; no legacy inspector."""
        from mye_c_automation.image_repairs_v2 import deterministic_quality
        from mye_c_automation.ai_judge.client import safe_payload
        checked=deterministic_quality(source,candidate,mask)
        if not checked['ok']:return dict(checked,quality_status='FAIL_UNKNOWN')
        item=self._item('image_quality_v2',candidate,'V2_QUALITY')
        item['purpose']=action
        item['extra_images']=[dict(path=str(source),image_id='SOURCE',sha256=sha256(source))]
        item['evidence_ids'].append('SOURCE')
        if observation is not None:
            item['repair_observation']={k:observation[k] for k in ('schema_version','decision','watermarks','preserve_regions','background_complexity') if k in observation}
        if mask is not None:
            from PIL import Image
            from mye_c_automation.watermark_processing.regions import visualization
            with Image.open(source) as photo:source_pixels=np.array(photo.convert('RGB'))
            with Image.open(mask) as mask_photo:mask_pixels=np.array(mask_photo.convert('L'))
            preview=self.evidence/(item['id']+'-mask-overlay.png')
            Image.fromarray(visualization(source_pixels,mask_pixels)).save(preview)
            item['extra_images'].append(dict(path=str(preview),image_id='MASK_VISUALIZATION',sha256=sha256(preview)))
            item['evidence_ids'].append('MASK_VISUALIZATION')
        from mye_c_automation.image_repairs_v2 import known_pattern_residuals
        guard=known_pattern_residuals(source,candidate,observation)
        if guard['status']=='REMAINS':
            from PIL import Image
            matches=[m for pattern in guard['patterns'] for m in pattern['matches']]
            with Image.open(candidate) as photo:
                for index,match in enumerate(matches[:3]):
                    x0,y0,x1,y1=match['bbox_pixels'];box=(max(0,x0-4),max(0,y0-4),min(photo.width,x1+4),min(photo.height,y1+4))
                    crop=photo.crop(box).convert('RGB');crop=crop.resize((crop.width*2,crop.height*2))
                    path=self.evidence/(item['id']+'-detail-'+str(index)+'.png');crop.save(path)
                    label='CANDIDATE_DETAIL_'+str(index);item['extra_images'].append(dict(path=str(path),image_id=label,sha256=sha256(path)))
                    item['evidence_ids'].append(label)
            item['reason']='Additional CANDIDATE_DETAIL crops show unchanged candidate pixels at numerical matches of the source-approved pattern. Verify them visually; the numerical match is not a new ownership/content label. Do not assume the image is clean because local repair ran.'
        from mye_c_automation.image_repairs_v2 import protected_region_comparison
        comparison=protected_region_comparison(source,candidate,observation,mask)
        comparison_directory=self.evidence/'protection_comparisons';comparison_directory.mkdir(exist_ok=True)
        comparison_path=comparison_directory/(item['id']+'.json')
        atomic_json(comparison_path,comparison)
        if comparison['regions'] and comparison['mask_overlap_pixels']:
            from PIL import Image,ImageDraw
            from mye_c_automation.ai_judge.image_action_decision import region
            with Image.open(source) as photo:protected_preview=photo.convert('RGB')
            draw=ImageDraw.Draw(protected_preview);w,h=protected_preview.size
            for entry in comparison['regions']:
                points=[(min(w-1,round(x*w)),min(h-1,round(y*h))) for x,y in region(entry['annotation'])]
                draw.line(points+[points[0]],fill=(20,225,190),width=2)
                draw.text(points[0],entry['id'],fill=(20,225,190))
            protected_path=self.evidence/(item['id']+'-protected-regions.png');protected_preview.save(protected_path)
            item['extra_images'].append(dict(path=str(protected_path),image_id='PROTECTED_REGIONS',sha256=sha256(protected_path)))
            item['evidence_ids'].append('PROTECTED_REGIONS')
        summary={k:comparison[k] for k in ('source_sha256','candidate_sha256','mask_sha256','source_protection_sha256','changed_pixels','mask_overlap_pixels')}
        summary['regions']=[{k:r[k] for k in ('id','changed_pixels','changed_fraction','mask_overlap_pixels')} for r in comparison['regions']]
        item['reason']=(item.get('reason') or '')+'\nprotected_region_comparison (pixel measurements, not a quality verdict): '+json.dumps(summary,sort_keys=True)
        from mye_c_automation.model_config import review_models
        models=review_models(self.judge.models)
        staged=(observation or {}).get('schema_version')=='image-review.staged-v1'
        if staged:
            try:
                response=self.judge.request_vision_phase('quality',item,safe_payload({},context)['context'])
                row=dict(response['result'],task_type='image_quality_v2',item_id=item['id'],evidence_ids=item['evidence_ids'])
                result=dict(status='CLEAN' if row['decision']=='MATCH' and not row['abstain'] else 'NEEDS_REVIEW',results=[row],models=list(models),staged_evidence=response)
            except (ValueError,OSError,TypeError,KeyError) as exc:result=dict(status='NEEDS_REVIEW',results=[],models=list(models),error=str(exc))
        else:result=self.judge.classify('image_quality_v2',item,safe_payload({},context)['context'],models=models,attempts=1)
        rows=result.get('results',[])
        ok=(result.get('status')=='CLEAN' and len(rows)==1 and result.get('models')==list(models) and all(r.get('decision')=='MATCH' and not r.get('abstain') and all(r['checks'].values()) for r in rows))
        status='PASS' if ok else 'FAIL_UNKNOWN'
        if not ok and len(rows)==1 and all(r and not r.get('abstain') and 'checks' in r for r in rows):
            if any(not all(r['checks'][k] for k in ('identity_preserved','packaging_preserved','protected_print_preserved')) for r in rows):status='FAIL_IDENTITY'
            elif any(not r['checks']['overlay_removed'] for r in rows):status='FAIL_WATERMARK_REMAINS'
            elif any(not r['checks']['no_new_artifacts'] for r in rows):status='FAIL_RETRYABLE'
        if guard['status']=='REMAINS':
            ok=False
            if status!='FAIL_IDENTITY':status='FAIL_WATERMARK_REMAINS'
        elif guard['status']=='UNRESOLVED':ok=False;status='FAIL_UNKNOWN'
        output=dict(checked,ok=ok,quality_status=status,judgement=result,pixel_residual_guard=guard,confidence_policy='NOT_REQUESTED' if staged else 'RECORD_ONLY',evidence_ids=item['evidence_ids'])
        output.update(protected_region_comparison=comparison,protection_review_status='PASS' if ok else 'NOT_PASSED',
            protection_comparison_path=str(comparison_path),protection_comparison_sha256=sha256(comparison_path))
        atomic_json(self.evidence/(item['id']+'.json'),output)
        return output

    def observe_image(self,path,context):
        result=self.inspect(path,path,context)
        return dict(result,verified=all(result.get(k) is True for k in ('source_clean','product_identity_match','ocr_pass','residual_pass','template_pass')),clean=result.get('source_clean') is True,sha256=sha256(path))

    def validate_title(self,product,generated):
        """User-selected title path: SOP/field checks and one translation, no VLM review."""
        proposed=generated.get('titleEn')
        ok=generated.get('ok') is True and isinstance(proposed,str) and bool(proposed.strip()) and len(proposed)<=120
        if generated.get('verify_translation'):
            translated=product.get('titleTranslationZh')
            ok=ok and product.get('titleEn')==proposed and isinstance(translated,str) and bool(translated.strip())
        item_id='TITLE_RULES_'+hashlib.sha256(json.dumps(generated,sort_keys=True).encode()).hexdigest()[:16]
        record={'ok':ok,'review_status':'NOT_REVIEWED','method':'SOP_RULES_AND_TRANSLATION_PRESENCE',
                'scope':'title_structure_and_single_translation_no_model_review','evidence_ids':[item_id]}
        atomic_json(self.evidence/(item_id+'.json'),record)
        return record

    def validate_brand(self,product,generated):
        """Brand authorization keeps its existing independent model gate."""
        item_id='TITLE_'+hashlib.sha256(json.dumps(generated,sort_keys=True).encode()).hexdigest()[:16]
        item={'id':item_id,'task_type':'title_semantics','image_id':item_id,'proposed_title':generated['titleEn'],
              'purpose':'verify_bilingual_translation' if generated.get('verify_translation') else 'validate_generated_title',
              'evidence_ids':[item_id]}
        result=self.judge.classify('title_semantics',item,product)
        rows=result.get('results',[])
        ok=result.get('status')=='CLEAN' and len(rows)==2 and all(r.get('decision')=='MATCH' and not r.get('abstain') and r.get('confidence',0)>=MODEL_CONFIDENCE_MIN for r in rows)
        atomic_json(self.evidence/(item_id+'.json'),result)
        return {'ok':ok,'evidence_ids':[item_id]}

    def inspect_deletion(self,source,context,comparison=None,*,decorated_refs=None):
        purpose='DELETE_REF_'+sha256(comparison)[:16] if comparison is not None else 'DELETE'
        item=self._item('deletion_quality',source,purpose)
        if decorated_refs is not None:
            item['purpose']='AUTHORIZED_DECORATED_COMPOSITE_REMOVAL'
            item['extra_images']=[]
            for index,reference in enumerate(decorated_refs):
                path=Path(reference['file'])
                if not path.is_absolute():path=Path(__file__).parent/path
                image_id='RETAINED_'+str(index)
                item['extra_images'].append({'path':str(path),'image_id':image_id,'sha256':sha256(path)})
                item['evidence_ids'].append(image_id)
        if comparison is not None:
            item['purpose']='EXACT_DUPLICATE_WITH_RETAINED_REFERENCE'
            item['extra_images']=[{'path':str(comparison),'image_id':'RETAINED_REFERENCE','sha256':sha256(comparison)}]
            item['evidence_ids'].append('RETAINED_REFERENCE')
        result=self.judge.classify('deletion_quality',item,context)
        rows=result.get('results',[])
        agrees=result.get('status')=='CLEAN' and len(rows)==2 and all(r.get('decision')=='MATCH' and r.get('confidence',0)>=MODEL_CONFIDENCE_MIN and not r.get('abstain') for r in rows)
        category=rows[0].get('category') if agrees and rows[0].get('category')==rows[1].get('category') else 'UNCERTAIN'
        observed={'ok':agrees and (category in {'DECORATION','STORE_BANNER'} or comparison is not None and category=='REDUNDANT'),
                  'is_box':False if agrees and all(r.get('is_box') is False for r in rows) else None,
                  'is_official':False if agrees and all(r.get('is_official') is False for r in rows) else None,
                  'category':category,'information_preserved':agrees and all(r.get('information_preserved') is True for r in rows),'evidence_ids':[item['id']]}
        if decorated_refs is not None:
            decorated=agrees and bool(decorated_refs) and category=='DECORATION' and all(r.get('is_decorated_composite') is True and r.get('retained_packaging_verified') is True for r in rows)
            observed.update(decorated_composite=decorated,retained_packaging_verified=decorated,
                            is_box=rows[0].get('is_box') if agrees and rows[0].get('is_box')==rows[1].get('is_box') else None)
            observed['ok']=decorated and observed['is_official'] is False and observed['information_preserved'] is True
        else:observed['ok']=observed['ok'] and observed['is_box'] is False and observed['is_official'] is False and observed['information_preserved'] is True
        if comparison is not None:
            observed['reference_sha256']=sha256(comparison)
            observed['evidence_ids']=sorted({item['id']}|{ref for row in rows for ref in row.get('evidence_ids',[])})
        atomic_json(self.evidence/(item['id']+'.json'),{'judgement':result,'observation':observed,'source_sha256':sha256(source)})
        return observed

    def _item(self,task,path,purpose):
        digest=sha256(path);item_id=purpose+'_'+digest[:16]
        return {'id':item_id,'task_type':task,'local':str(path),'sha256':digest,
                'image_id':item_id,'evidence_ids':[item_id],'purpose':purpose}

    def propose(self,source,context):
        item=self._item('remedy_geometry',source,'GEOMETRY')
        image=cv2.imdecode(np.frombuffer(Path(source).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        item['dimensions']=[image.shape[1],image.shape[0]]
        judgement=self.judge.classify('remedy_geometry',item,context)
        rows=judgement.get('results',[])
        atomic_json(self.evidence/(item['id']+'.json'),judgement)
        if judgement.get('status')!='CLEAN' or len(rows)!=2: return {}
        if any(r.get('abstain') or r.get('decision')!='MATCH' for r in rows): return {}
        if any(rows[0].get(k)!=rows[1].get(k) for k in ('crop_box','subject_box','erase_box')): return {}
        return {k:rows[0].get(k) for k in ('crop_box','subject_box','erase_box')}

    def inspect(self,source,candidate,context):
        from mye_c_automation.audit_one import run_ocr
        from mye_c_automation.residcheck import resid
        candidate=Path(candidate);source=Path(source)
        image=cv2.imdecode(np.frombuffer(candidate.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError('CANDIDATE_DECODE_FAILED')
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine=RapidOCR()
        ocr,hits,classifiers=run_ocr(self.engine,image,title_text=str(context.get('title') or ''))
        item=self._item('remedy_quality',candidate,'QUALITY')
        if context.get('_image_repair'):
            item['purpose']=json.dumps(context['_image_repair'],ensure_ascii=False,sort_keys=True)
        binding=hashlib.sha256(json.dumps([sha256(source),context],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
        item['id']+='_'+binding
        item['image_id']=item['id'];item['evidence_ids']=[item['id']]
        visual,score=resid(image)
        residual=self.evidence/(item['id']+'_residual.png')
        cv2.imencode('.png',visual)[1].tofile(str(residual))
        from mye_c_automation.template_applicability import resolve
        applicability=resolve(self.root,self.job['shop_id'],self.job.get('templates_required',False))
        specs=applicability['templates']
        applicable=[s for s in specs if s.get('shop_id')==self.job['shop_id']]
        template_ok=applicability['status'] in {'COMPLETE','NO_APPLICABLE_TEMPLATE'}
        scans=[]
        from mye_c_automation.wm_tpl import scan, VERSION
        for spec in applicable:
            path=Path(spec['path'])
            if not path.is_absolute(): path=self.root/path
            projection=spec.get('projection','gray')
            value=scan(str(candidate),np.load(path,allow_pickle=False),projection=projection)
            scans.append({'template_sha256':sha256(path),'ncc':value,'algorithm':VERSION,'projection':projection,'variance_window':'top_left_aligned'})
            if value is None or value>.65:template_ok=False
        item['extra_images']=[{'path':str(source),'image_id':'SOURCE','sha256':sha256(source)},
                              {'path':str(residual),'image_id':'RESIDUAL','sha256':sha256(residual)}]
        judgement=self.judge.classify('remedy_quality',item,context)
        rows=judgement.get('results',[])
        agrees=judgement.get('status')=='CLEAN' and len(rows)==2 and all(not r.get('abstain') and r.get('confidence',0)>=MODEL_CONFIDENCE_MIN and r.get('decision')=='MATCH' for r in rows)
        flags=('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe','model_match','packaging_match','official_source')
        result={key:agrees and all(r.get('checks',{}).get(key) is True for r in rows) for key in flags}
        result.update(ocr_pass=not bool(hits),template_pass=template_ok,evidence_ids=[item['id']])
        for field in ('image_type','model','color'):
            if agrees and rows[0].get(field)==rows[1].get(field): result[field]=rows[0].get(field)
        record={'candidate_sha256':sha256(candidate),'source_sha256':sha256(source),'ocr':ocr,'ocr_hits':hits,'classifiers':classifiers,'residual_score':score,'template_scans':scans,'judgement':judgement,'result':result}
        atomic_json(self.evidence/(item['id']+'.json'),record)
        return result
