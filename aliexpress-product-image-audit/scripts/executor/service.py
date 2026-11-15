"""Pure service boundary. Production transport and ACL deployment are external."""
from copy import deepcopy
from pathlib import Path
import hashlib
import tempfile
import json
import time
from final_state import simulate_final_snapshot, validate_final_snapshot, pre_apply_validate
from plan_v2 import validate_plan,planned_upload_count
from product_state import canonical_state_hash,saved_state_matches

class ExecutorService:
    def __init__(self, authorization, writer, evidence_root, budget=None, automation_policy=None, before_remote_write=None):
        self.authorization, self.writer = authorization, writer
        self.budget=budget
        self.automation_policy=automation_policy
        self.before_remote_write=before_remote_write
        self.root = Path(evidence_root).resolve()

    def execute(self, plan, ticket=None, dry_run=True):
        started=time.perf_counter()
        # Private executor-owned snapshots live only for this request.
        with tempfile.TemporaryDirectory(prefix="audit-evidence-", dir=self.root) as snapshots:
            result=self._execute(plan, ticket, dry_run, Path(snapshots))
            result['elapsed_ms']=round((time.perf_counter()-started)*1000,3)
            return result

    def _execute(self, plan, ticket, dry_run, snapshots):
        plan = deepcopy(plan)
        if type(dry_run) is not bool:
            raise ValueError('dry_run must be boolean')
        plan = validate_plan(plan)
        if plan['schema']=='token-opt-plan/v3' and not dry_run:
            policy=self.automation_policy
            if policy is None or plan['automation']['policy_sha256']!=policy.sha256:
                raise ValueError('AUTOMATION_POLICY_CHANGED_OR_MISSING')
            if (plan.get('post_actions') or {}).get('sku_row_assignments') and policy.config.get('allow_snapshot_sku_rows') is not True:
                raise ValueError('SNAPSHOT_SKU_ASSIGNMENT_NOT_AUTHORIZED')
            policy.authorize(plan['pid'],plan['shop'],plan['automation']['actions'],uploads=planned_upload_count(plan))
        for ref in plan['evidence_refs'] + plan['ai_judgement_refs']:
            if set(ref) != {'path','sha256'}:
                raise ValueError('invalid evidence reference')
            path = (self.root / ref['path']).resolve()
            if not path.is_relative_to(self.root) or hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('evidence changed')
        manifest_path=self.root/'evidence_manifest.json'
        if manifest_path.exists():
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            for ref in manifest.get('sources',[]):
                if hashlib.sha256(Path(ref['source']).read_bytes()).hexdigest()!=ref['sha256']:
                    raise ValueError('manifest source changed')
        if plan['desired'] and not plan['evidence_refs']:
            raise ValueError('missing evidence')
        post = plan['post_actions'] or {}
        upload_paths = []
        for ref in post.get('uploads',[]):
            path = (self.root / ref['path']).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError('upload evidence changed')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != ref['sha256']:
                raise ValueError('upload evidence changed')
            from PIL import Image
            import io
            try:
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                    if image.format not in {'PNG','JPEG','WEBP'} or min(image.size)<json.loads((Path(__file__).parents[1]/'config'/'policy.v2.json').read_text(encoding='utf-8'))['image_min_short_side'] or len(data)>20*1024*1024:
                        raise ValueError('image format, dimensions or size rejected')
                    expected={'PNG':{'.png'},'JPEG':{'.jpg','.jpeg'},'WEBP':{'.webp'}}[image.format]
                    if path.suffix.lower() not in expected: raise ValueError('MIME extension mismatch')
            except Exception as exc:
                raise ValueError('invalid replacement image') from exc
            # Never reopen the mutable producer path after validation.
            snapshot = snapshots / (str(len(upload_paths)) + path.suffix)
            snapshot.write_bytes(data)
            pool = plan['desired'].get('images',{}).get(ref['pool'],[])
            if ref['pool']=='description':
                from description_images import body_image_nodes
                product=json.loads((self.root/'audit_product.json').read_text(encoding='utf-8'))
                pool={r['index']:r['url'] for r in body_image_nodes(product.get('descriptionJson'))}
                if ref['index'] not in pool:raise ValueError('description upload target missing')
            elif ref['index'] >= len(pool):
                raise ValueError('upload target missing')
            upload_paths.append(snapshot)
        if dry_run:
            return {'dry_run':True,'site_save_calls':0,'upload_calls':0}
        if ticket is None:
            raise ValueError('authorization required')
        self.authorization.consume(ticket,plan)
        before = deepcopy(self.writer.product(plan['pid']))
        self._identity(before, plan)
        if canonical_state_hash(before) != plan['precondition']['state_sha256']:
            raise ValueError('STATE_DRIFT')
        validation = pre_apply_validate(before, plan)
        if not validation['ok']:
            raise ValueError('PRE_APPLY_VALIDATION: ' + repr(validation['errors']))
        desired = simulate_final_snapshot(before, plan)
        if not upload_paths and canonical_state_hash(before)==canonical_state_hash(desired):
            return {'dry_run':False,'site_save_calls':0,'upload_calls':0,'translate_calls':0,'status_calls':0,'verification_ok':True,'status':'NO_ACTION'}
        if self.budget is not None: self.budget.reserve('site_save')
        uploaded = []
        upload_cache={};upload_calls=0;receipts=[]
        from job_manager import atomic_json
        def persist_uploads(state,error=None):
            atomic_json(self.root/'upload_receipts.json',{'schema':'upload-receipts/v1','job_id':plan['job_id'],'pid':plan['pid'],'shop':plan['shop'],'state':state,'upload_calls':upload_calls,'uploads':receipts,'error':error})
        try:
            for ref,path in zip(post.get('uploads',[]),upload_paths):
                if self.automation_policy:self.automation_policy.verify_current()
                reused=ref['sha256'] in upload_cache
                if reused:url=upload_cache[ref['sha256']]
                else:
                    if self.budget is not None and 'uploads' in self.budget.snapshot()['limits']: self.budget.reserve('uploads')
                    upload_calls+=1;persist_uploads('UPLOADING')
                    from upload_rate import UploadRateLimiter
                    with UploadRateLimiter().slot():
                        if self.before_remote_write:self.before_remote_write()
                        url = self.writer.upload(path)
                uploaded.append(url)
                receipt=dict(ref,url=url,reused=reused);receipts.append(receipt)
                if not isinstance(url,str) or not url.strip():
                    raise ValueError('UPLOAD_URL_EMPTY')
                if plan['schema']=='token-opt-plan/v3' and not reused:
                    received=hashlib.sha256(self.writer.fetch_image(url)).hexdigest()
                    receipt.update(received_sha256=received,sha256_verified=received==ref['sha256'])
                    if received!=ref['sha256']:raise ValueError('UPLOAD_HASH_MISMATCH')
                upload_cache[ref['sha256']]=url
                persist_uploads('UPLOADING')
                desired = simulate_final_snapshot(before, plan, uploaded)
        except Exception as exc:
            persist_uploads('UPLOAD_UNKNOWN',type(exc).__name__+': '+str(exc))
            if isinstance(exc,ValueError) and str(exc) in {'UPLOAD_HASH_MISMATCH','UPLOAD_URL_EMPTY'}:raise
            raise RuntimeError('upload failed; possible orphan resources: ' + repr(uploaded)) from exc
        persist_uploads('UPLOADED')
        validation = validate_final_snapshot(desired, context={'before':before,'plan':plan})
        if not validation['ok']:
            raise ValueError('UPLOAD_PARTIAL: ' + repr(validation['errors']))
        current = self.writer.product(plan['pid'])
        self._identity(current, plan)
        if canonical_state_hash(current) != plan['precondition']['state_sha256']:
            raise ValueError('STATE_DRIFT_BEFORE_SAVE')
        from job_manager import atomic_json
        persist_uploads('UPLOADED')
        if self.automation_policy:self.automation_policy.verify_current()
        atomic_json(self.root/'expected_after.json',desired)
        if self.before_remote_write:self.before_remote_write()
        atomic_json(self.root/'save_attempt.json',{'site_save_calls':1,'state':'APPLY_UNKNOWN','expected_state_sha256':canonical_state_hash(desired)})
        scope={}
        if post.get('content_groups'):
            from image_content_plan import save_scope
            deleted,replaced=save_scope(before,plan,desired)
            scope=dict(description_image_deletions=deleted,description_image_replacements=replaced)
        self.writer.save(plan['pid'],deepcopy(desired),expected_state_sha256=plan['precondition']['state_sha256'],**scope)
        atomic_json(self.root/'save_attempt.json',{'site_save_calls':1,'state':'SAVED_RESPONSE_RECEIVED','expected_state_sha256':canonical_state_hash(desired)})
        after = self.writer.product(plan['pid'])
        if not saved_state_matches(desired,after,source=before):
            raise ValueError('post-write verification failed')
        translation_status='NOT_REQUIRED';translate_calls=0
        if post.get('translate_title') and before.get('titleEn')!=desired.get('titleEn'):
            try:
                if self.budget is not None: self.budget.reserve('translate_title')
                translate_calls=1
                self.writer.translate(plan['pid'],desired.get('titleEn',''))
                translated = self.writer.product(plan['pid'])
                expected = deepcopy(desired)
                expected['titleTranslationZh'] = translated.get('titleTranslationZh')
                if not translated.get('titleTranslationZh') or not saved_state_matches(expected,translated,source=before):
                    raise ValueError('translation verification failed')
                translation_status='TRANSLATED'
            except Exception as exc:
                translation_status='TRANSLATION_PENDING'
                atomic_json(self.root/'translation_pending.json',{'pid':plan['pid'],'titleEn':desired.get('titleEn'),'error':type(exc).__name__,'retry_save_allowed':False})
        return {'dry_run':False,'site_save_calls':1,'upload_calls':upload_calls,'verification_ok':True,'translate_calls':translate_calls,'translation_status':translation_status,'status_calls':0}


    def _identity(self, product, plan):
        expected_account=plan.get('precondition',{}).get('account_fingerprint')
        if plan.get('schema')=='token-opt-plan/v3' and expected_account is None and callable(getattr(type(self.writer),'account_fingerprint',None)):
            raise ValueError('ACCOUNT_BINDING_REQUIRED')
        if expected_account is not None:
            probe=getattr(self.writer,'account_fingerprint',None)
            if not callable(probe):raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
            if probe()!=expected_account:raise ValueError('ACCOUNT_MISMATCH')
        if not any(k in product for k in ('id','pid','productId')): raise ValueError('PID_UNVERIFIED')
        if not any(k in product for k in ('shopId','shop_id','shop')) and not callable(getattr(type(self.writer),'current_shop',None)): raise ValueError('SHOP_UNVERIFIED')
        for key in ('id','pid','productId'):
            if key in product and str(product[key]) != str(plan['pid']):
                raise ValueError('PID_MISMATCH')
        for key in ('shopId','shop_id','shop'):
            if key in product and str(product[key]) != str(plan['shop']):
                raise ValueError('SHOP_MISMATCH')
        probe=getattr(self.writer,'current_shop',None)
        if callable(getattr(type(self.writer),'current_shop',None)) and str(probe()) != str(plan['shop']):
            raise ValueError('SHOP_MISMATCH')
