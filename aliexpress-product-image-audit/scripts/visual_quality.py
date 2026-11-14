"""Three-pass OCR, residual/template evidence and independent dual-model review."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from job_manager import atomic_json
from candidate_quality import sha256

class VisualQualityInspector:
    def __init__(self,directory,job,judge=None,ocr_engine=None):
        self.root=Path(directory);self.job=job;self.engine=ocr_engine;self.budget=None
        import uuid
        self.metrics_phase=uuid.uuid4().hex
        if judge is None:
            from budget_manager import BudgetManager
            from ai_judge import JudgeClient
            self.budget=BudgetManager(job['budget'],self.root/'budget.sqlite')
            model_options={'config':job['model_config']} if 'model_config' in job else {}
            judge=JudgeClient(self.budget,self.root.parent/'shared_judge_cache',**model_options)
        self.judge=judge
        self.evidence=self.root/'quality_evidence';self.evidence.mkdir(exist_ok=True)

    def close(self):
        if self.budget: self.budget.close()

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
        ok=result.get('status')=='CLEAN' and len(rows)==2 and all(r.get('decision')=='MATCH' and not r.get('abstain') and r.get('confidence',0)>=.9 for r in rows)
        atomic_json(self.evidence/(item_id+'.json'),result)
        return {'ok':ok,'evidence_ids':[item_id]}

    def inspect_deletion(self,source,context,comparison=None):
        purpose='DELETE_REF_'+sha256(comparison)[:16] if comparison is not None else 'DELETE'
        item=self._item('deletion_quality',source,purpose)
        if comparison is not None:
            item['purpose']='EXACT_DUPLICATE_WITH_RETAINED_REFERENCE'
            item['extra_images']=[{'path':str(comparison),'image_id':'RETAINED_REFERENCE','sha256':sha256(comparison)}]
            item['evidence_ids'].append('RETAINED_REFERENCE')
        result=self.judge.classify('deletion_quality',item,context)
        rows=result.get('results',[])
        agrees=result.get('status')=='CLEAN' and len(rows)==2 and all(r.get('decision')=='MATCH' and r.get('confidence',0)>=.9 and not r.get('abstain') for r in rows)
        category=rows[0].get('category') if agrees and rows[0].get('category')==rows[1].get('category') else 'UNCERTAIN'
        observed={'ok':agrees and (category in {'DECORATION','STORE_BANNER'} or comparison is not None and category=='REDUNDANT'),
                  'is_box':False if agrees and all(r.get('is_box') is False for r in rows) else None,
                  'is_official':False if agrees and all(r.get('is_official') is False for r in rows) else None,
                  'category':category,'information_preserved':agrees and all(r.get('information_preserved') is True for r in rows),'evidence_ids':[item['id']]}
        observed['ok']=observed['ok'] and observed['is_box'] is False and observed['is_official'] is False and observed['information_preserved'] is True
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
        from audit_one import run_ocr
        from residcheck import resid
        candidate=Path(candidate);source=Path(source)
        image=cv2.imdecode(np.frombuffer(candidate.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError('CANDIDATE_DECODE_FAILED')
        if self.engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self.engine=RapidOCR()
        ocr,hits,classifiers=run_ocr(self.engine,image,title_text=str(context.get('title') or ''))
        item=self._item('remedy_quality',candidate,'QUALITY')
        binding=hashlib.sha256(json.dumps([sha256(source),context],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
        item['id']+='_'+binding
        item['image_id']=item['id'];item['evidence_ids']=[item['id']]
        visual,score=resid(image)
        residual=self.evidence/(item['id']+'_residual.png')
        cv2.imencode('.png',visual)[1].tofile(str(residual))
        from template_applicability import resolve
        applicability=resolve(self.root,self.job['shop_id'],self.job.get('templates_required',False))
        specs=applicability['templates']
        applicable=[s for s in specs if s.get('shop_id')==self.job['shop_id']]
        template_ok=applicability['status'] in {'COMPLETE','NO_APPLICABLE_TEMPLATE'}
        scans=[]
        from wm_tpl import scan,VERSION
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
        agrees=judgement.get('status')=='CLEAN' and len(rows)==2 and all(not r.get('abstain') and r.get('confidence',0)>=.9 and r.get('decision')=='MATCH' for r in rows)
        flags=('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe','model_match','packaging_match','official_source')
        result={key:agrees and all(r.get('checks',{}).get(key) is True for r in rows) for key in flags}
        result.update(ocr_pass=not bool(hits),template_pass=template_ok,evidence_ids=[item['id']])
        for field in ('image_type','model','color'):
            if agrees and rows[0].get(field)==rows[1].get(field): result[field]=rows[0].get(field)
        record={'candidate_sha256':sha256(candidate),'source_sha256':sha256(source),'ocr':ocr,'ocr_hits':hits,'classifiers':classifiers,'residual_score':score,'template_scans':scans,'judgement':judgement,'result':result}
        atomic_json(self.evidence/(item['id']+'.json'),record)
        return result
