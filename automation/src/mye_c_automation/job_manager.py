"""Atomic job metadata and fixed workflow transitions (not a security boundary)."""
import hashlib
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

STATES = 'CREATED PREFLIGHT AUDITED AI_PENDING AI_RESOLVED PLAN_READY VALIDATED DRY_RUN_PASSED APPLY_AUTHORIZED APPLIED APPLY_MATCHED STRUCTURE_CHECKED CONTENT_REVIEWED VERIFIED'.split()
TERMINAL = {'NEEDS_REVIEW', 'FAILED', 'CANCELLED', 'BUDGET_EXCEEDED', 'STATE_DRIFT'}

def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)

class JobManager:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, pid, shop, budget, mode='read_only', templates_required=False, model_config=None, model_budget=None, image_workflow=None, image_options=None):
        if type(pid) is not int or type(shop) is not int or min(pid, shop) <= 0:
            raise ValueError('positive PID/shop required')
        if mode not in {'read_only','audit','dry_run','apply','auto_apply'}:
            raise ValueError('unsupported workflow mode')
        if type(templates_required) is not bool: raise ValueError('invalid template requirement')
        if model_config is not None:
            from mye_c_automation.model_config import validate_config
            model_config=validate_config(model_config)
        job = {'templates_required':templates_required,'job_id': 'JOB_' + uuid.uuid4().hex, 'pid': pid, 'shop_id': shop,
               'workflow_version': 'token-opt-v2', 'policy_version': 'v2',
               'created_at': datetime.now(timezone.utc).isoformat(), 'mode': mode,
               'budget': dict(budget), 'input_state_sha256': None}
        if model_config is not None:job['model_config']=model_config
        if model_budget is not None:job['model_budget']=json.loads(json.dumps(model_budget,allow_nan=False))
        if image_workflow is not None:
            if image_workflow!='v2':raise ValueError('UNKNOWN_IMAGE_WORKFLOW')
            options={'rights':'RIGHTS_UNKNOWN','max_mask_area':.25}
            options.update(image_options or {})
            if set(options)-{'rights','max_mask_area','lama_model_path','lama_model_sha256','image_edit'} or options['rights'] not in {'OWNED_OR_LICENSED','RIGHTS_UNKNOWN','THIRD_PARTY_ATTRIBUTION'} or type(options['max_mask_area']) not in (int,float) or not 0<options['max_mask_area']<=.25:raise ValueError('INVALID_IMAGE_OPTIONS')
            if options.get('lama_model_path'):
                path=Path(options['lama_model_path']).resolve();options['lama_model_path']=str(path)
                if path.is_file():
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    if options.get('lama_model_sha256',digest)!=digest:raise ValueError('LAMA_MODEL_CHANGED')
                    options['lama_model_sha256']=digest
            if 'image_edit' in options:
                from mye_c_automation.image_repairs_v2 import freeze_image_edit_config
                options['image_edit']=freeze_image_edit_config(options['image_edit'])
            from mye_c_automation.resources import validate_resource_json
            validate_resource_json(options,'image-options.v2.schema.json')
            job.update(image_workflow='v2',image_options=options)
        directory = self.root / job['job_id']
        directory.mkdir()
        atomic_json(directory / 'job.json', job)
        atomic_json(directory / 'binding.json', {'sha256': hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()})
        atomic_json(directory / 'state.json', {'state': 'CREATED'})
        return job

    def automatic_plan_ready(self, job_id, result):
        """Explicit migration from audit review to an independently compiled auto plan."""
        self.load(job_id)
        path=self.directory(job_id)/'state.json'
        previous=json.loads(path.read_text(encoding='utf-8'))['state']
        if previous not in {'NEEDS_REVIEW','PLAN_READY','AI_RESOLVED'} or not result.get('ok'):
            raise ValueError('automatic plan not ready')
        atomic_json(path,{'state':'PLAN_READY','checkpoint':previous,'automatic':True})

    def finish_automatic(self, job_id, status):
        self.load(job_id)
        if status not in {'CLEAN','DEFERRED','RESERVED','PREWRITE_FAILED','BLOCKED_FATAL','AUTO_VERIFIED','PARTIALLY_AUTO_FIXED','TRANSLATION_PENDING','APPLY_UNKNOWN','CONTENT_REVIEW_REQUIRED'}:
            raise ValueError('invalid automatic outcome')
        path=self.directory(job_id)/'state.json'
        previous=json.loads(path.read_text(encoding='utf-8'))['state']
        atomic_json(path,{'state':status,'checkpoint':previous,'automatic':True})

    def bind_full_audit(self,job_id):
        job=self.load(job_id);job['audit_scope']='full'
        directory=self.directory(job_id)
        atomic_json(directory/'job.json',job)
        atomic_json(directory/'binding.json',{'sha256':hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest()})
        return job

    def bind_account(self,job_id,fingerprint):
        import re
        if type(fingerprint) is not str or not re.fullmatch('[a-f0-9]{64}',fingerprint):raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
        job=self.load(job_id)
        if job.get('account_fingerprint') not in (None,fingerprint):raise ValueError('ACCOUNT_MISMATCH')
        job['account_fingerprint']=fingerprint
        directory=self.directory(job_id)
        atomic_json(directory/'job.json',job)
        atomic_json(directory/'binding.json',{'sha256':hashlib.sha256(json.dumps(job,sort_keys=True).encode()).hexdigest()})
        return job

    def bind_input(self, job_id, product):
        from mye_c_automation.product_state import canonical_state_hash
        job = self.load(job_id)
        for key,expected in (('id',job['pid']),('pid',job['pid']),('shopId',job['shop_id']),('shop_id',job['shop_id'])):
            if key in product and str(product[key]) != str(expected): raise ValueError('product binding mismatch')
        digest = canonical_state_hash(product)
        if job['input_state_sha256'] not in (None, digest):
            raise ValueError('STATE_DRIFT')
        job['input_state_sha256'] = digest
        directory = self.directory(job_id)
        atomic_json(directory / 'job.json', job)
        atomic_json(directory / 'binding.json', {'sha256': hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()})
        return job

    def directory(self, job_id):
        if not job_id.startswith('JOB_') or not job_id[4:].isalnum():
            raise ValueError('invalid job id')
        return self.root / job_id

    def transition(self, job_id, target):
        path = self.directory(job_id) / 'state.json'
        current = json.loads(path.read_text(encoding='utf-8'))['state']
        if current in TERMINAL or current == 'VERIFIED':
            raise ValueError('terminal job')
        if target not in TERMINAL and (target not in STATES or STATES.index(target) != STATES.index(current) + 1):
            raise ValueError('invalid state transition')
        atomic_json(path, {'state': target, 'checkpoint': current})

    def resolve_review(self, job_id, result):
        directory = self.directory(job_id)
        state = json.loads((directory/'state.json').read_text(encoding='utf-8'))
        if state['state'] != 'NEEDS_REVIEW':
            raise ValueError('job is not awaiting review')
        target = 'PLAN_READY' if result.get('ok') else 'NEEDS_REVIEW'
        atomic_json(directory/'state.json', {'state':target,'checkpoint':'AI_RESOLVED','review_transitions':['MANUAL_REVIEWED','POLICY_RESOLVED',target]})
        path=directory/'review.json'
        review=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        review.update(status=target,plan_validation=result)
        atomic_json(path,review)
        from mye_c_automation.render_token_report import render
        (directory/'report.md').write_text(render(directory,self.load(job_id)['pid'])+'\nState: '+target+'\n',encoding='utf-8')

    def load(self, job_id):
        directory = self.directory(job_id)
        job = json.loads((directory / 'job.json').read_text(encoding='utf-8'))
        binding = json.loads((directory / 'binding.json').read_text(encoding='utf-8'))
        if job['job_id'] != job_id or hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest() != binding['sha256']:
            raise ValueError('job identity or budget changed')
        return job

    def recover(self, job_id):
        self.load(job_id)
        path = self.directory(job_id) / 'state.json'
        state = json.loads(path.read_text(encoding='utf-8'))
        lock = self.root / ('pid_' + str(self.load(job_id)['pid']) + '.lock')
        if lock.exists():
            owner = json.loads(lock.read_text(encoding='utf-8'))
            if owner.get('job_id') != job_id:
                raise ValueError('lock owned by another job')
            import ctypes
            if os.name == 'nt':
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                handle = kernel.OpenProcess(0x1000, False, owner['pid'])
                if handle:
                    kernel.CloseHandle(ctypes.c_void_p(handle))
                    raise ValueError('job process still alive')
                if ctypes.get_last_error() != 87:  # Only invalid PID proves absence.
                    raise ValueError('cannot establish lock owner exit')
            else:
                try:
                    os.kill(owner['pid'], 0)
                except ProcessLookupError:
                    pass
                else:
                    raise ValueError('job process still alive')
            lock.unlink()
        if state['state'] == 'FAILED':
            atomic_json(path, {'state': state['checkpoint']})
        elif state['state'] in TERMINAL:
            raise ValueError('manual resolution required')
