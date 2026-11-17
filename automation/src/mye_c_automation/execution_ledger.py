"""Account/PID idempotency survives job IDs, output roots and process restarts."""
import hashlib
import json
from pathlib import Path
import sqlite3
from mye_c_automation.account_coordination import DEFAULT_DIRECTORY

def operation_digest(plan):
    post=dict(plan.get('post_actions') or {})
    if post.get('uploads'):
        post['uploads']=[{k:v for k,v in row.items() if k!='path'} for row in post['uploads']]
    value={'desired':plan['desired'],'post_actions':post}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class ExecutionLedger:
    def __init__(self,path=None):
        path=Path(path or DEFAULT_DIRECTORY.parent/'mye_c_automation.execution_ledger.sqlite');path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None)
        self.db.execute('CREATE TABLE IF NOT EXISTS executions (account TEXT, shop INTEGER, pid INTEGER, job TEXT, before_hash TEXT, operation TEXT, state TEXT, PRIMARY KEY(account,shop,pid))')
        self.db.execute('CREATE TABLE IF NOT EXISTS execution_job_locations (job TEXT PRIMARY KEY, directory TEXT NOT NULL)')

    def register_job(self,job,directory):
        directory=str(Path(directory).resolve())
        previous=self.db.execute('SELECT directory FROM execution_job_locations WHERE job=?',(job,)).fetchone()
        if previous and previous[0]!=directory:raise ValueError('EXECUTION_JOB_LOCATION_CHANGED')
        self.db.execute('INSERT OR IGNORE INTO execution_job_locations VALUES (?,?)',(job,directory))

    def latest(self,account,shop,pid):
        row=self.db.execute('SELECT job,before_hash,operation,state FROM executions WHERE account=? AND shop=? AND pid=?',(account,shop,pid)).fetchone()
        if not row:return None
        value=dict(zip(('job_id','before_hash','operation','state'),row))
        location=self.db.execute('SELECT directory FROM execution_job_locations WHERE job=?',(row[0],)).fetchone()
        value['directory']=location[0] if location else None
        return value

    def claim(self,account,shop,pid,job,before_hash,operation):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.db.execute('SELECT job,before_hash,operation,state FROM executions WHERE account=? AND shop=? AND pid=?',(account,shop,pid)).fetchone()
            if previous:
                if previous[3] in {'RESERVED','APPLY_UNKNOWN','CONTENT_REVIEW_REQUIRED','TRANSLATION_PENDING'}:
                    self.db.execute('COMMIT')
                    return {'ok':False,'status':previous[3],'previous_job_id':previous[0],'retry_save_allowed':False}
                if previous[3]!='PREWRITE_FAILED' and previous[1:3]==(before_hash,operation):
                    self.db.execute('COMMIT')
                    return {'ok':False,'status':'DEFERRED','previous_job_id':previous[0],'reason':'DUPLICATE_OPERATION','retry_save_allowed':False}
            self.db.execute('INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?)',(account,shop,pid,job,before_hash,operation,'RESERVED'))
            self.db.execute('COMMIT')
            return {'ok':True}
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def begin_side_effect(self,account,shop,pid,job):
        changed=self.db.execute("UPDATE executions SET state='APPLY_UNKNOWN' WHERE account=? AND shop=? AND pid=? AND job=? AND state='RESERVED'",(account,shop,pid,job))
        if changed.rowcount!=1:raise ValueError('EXECUTION_LEDGER_RESERVATION_REQUIRED')

    def claim_after_rejected_upload(self,account,shop,pid,job,before_hash,operation,*,source_directory,proof_path,authorization_id):
        """Fresh explicit continuation only after the first upload was rejected.

        Keep the prior unknown journal and append its ledger state to history.
        A save-stage marker, timeout, partial upload or state drift stays blocked.
        """
        from mye_c_automation.job_manager import atomic_json
        source=Path(source_directory).resolve();proof_path=Path(proof_path).resolve()
        if not isinstance(authorization_id,str) or not authorization_id.strip():raise ValueError('NEW_AUTHORIZATION_REQUIRED')
        if proof_path.is_relative_to(source):raise ValueError('PROOF_MUST_NOT_CHANGE_SOURCE')
        previous_job,previous_plan,files=_rejected_upload_source(source)
        if (previous_job.get('account_fingerprint'),previous_job['shop_id'],previous_job['pid'],previous_job['input_state_sha256'])!=(account,shop,pid,before_hash):raise ValueError('REJECTED_UPLOAD_CONTEXT_OR_STATE_MISMATCH')
        if job==previous_job['job_id']:raise ValueError('FRESH_JOB_REQUIRED')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.db.execute('SELECT job,before_hash,operation,state FROM executions WHERE account=? AND shop=? AND pid=?',(account,shop,pid)).fetchone()
            if previous!=(previous_job['job_id'],before_hash,operation_digest(previous_plan),'APPLY_UNKNOWN'):
                self.db.execute('COMMIT');return dict(ok=False,status='PREVIOUS_REJECTED_UPLOAD_BINDING_MISMATCH',retry_save_allowed=False)
            if proof_path.exists():raise ValueError('CONTINUATION_PROOF_ALREADY_EXISTS')
            atomic_json(proof_path,dict(schema='rejected-first-upload-followup/v1',source_directory=str(source),files=files,next_job=job,authorization_id=authorization_id,previous_state='APPLY_UNKNOWN',product_save_attempted=False))
            self.db.execute('CREATE TABLE IF NOT EXISTS execution_rejected_upload_followups (account TEXT,shop INTEGER,pid INTEGER,job TEXT,before_hash TEXT,operation TEXT,state TEXT,next_job TEXT,proof_sha256 TEXT,authorization_id TEXT)')
            self.db.execute('INSERT INTO execution_rejected_upload_followups VALUES (?,?,?,?,?,?,?,?,?,?)',(account,shop,pid,*previous,job,hashlib.sha256(proof_path.read_bytes()).hexdigest(),authorization_id))
            self.db.execute('INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?)',(account,shop,pid,job,before_hash,operation,'RESERVED'))
            self.db.execute('COMMIT');return dict(ok=True,previous_job_id=previous_job['job_id'],previous_state='APPLY_UNKNOWN',scope='FIRST_UPLOAD_HTTP400_NO_SAVE_STAGE',proof_path=str(proof_path))
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def claim_followup(self,account,shop,pid,job,before_hash,operation,*,proof_path,authorization_id):
        """New authorized work after a proven partial write; never release unknown saves."""
        from mye_c_automation.workflow_runner import validate_partial_followup
        proof=validate_partial_followup(proof_path)
        if not isinstance(authorization_id,str) or not authorization_id.strip():raise ValueError('FOLLOWUP_NEW_AUTHORIZATION_REQUIRED')
        if (proof['account'],str(proof['shop']),proof['pid'],proof['current_state_sha256'])!=(account,str(shop),pid,before_hash):raise ValueError('FOLLOWUP_CONTEXT_OR_STATE_MISMATCH')
        if job==proof['previous_job_id'] or operation==proof['previous_operation']:raise ValueError('FOLLOWUP_CANNOT_REPLAY_OLD_OPERATION')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.db.execute('SELECT job,before_hash,operation,state FROM executions WHERE account=? AND shop=? AND pid=?',(account,shop,pid)).fetchone()
            if not previous or previous[0]!=proof['previous_job_id'] or previous[2]!=proof['previous_operation'] or previous[3]!='CONTENT_REVIEW_REQUIRED':
                self.db.execute('COMMIT');return dict(ok=False,status=previous[3] if previous else 'FOLLOWUP_PREVIOUS_BINDING_MISSING',retry_save_allowed=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS execution_followups (account TEXT,shop INTEGER,pid INTEGER,job TEXT,before_hash TEXT,operation TEXT,state TEXT,next_job TEXT,proof_sha256 TEXT,authorization_id TEXT)')
            self.db.execute('INSERT INTO execution_followups VALUES (?,?,?,?,?,?,?,?,?,?)',(account,shop,pid,*previous,job,hashlib.sha256(Path(proof_path).read_bytes()).hexdigest(),authorization_id))
            self.db.execute('INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?)',(account,shop,pid,job,before_hash,operation,'RESERVED'))
            self.db.execute('COMMIT');return dict(ok=True,previous_job_id=previous[0],previous_business_status='INCOMPLETE',verified_scope='PREVIOUS_WRITE_KNOWN_UNREAD_UNCHANGED_REFERENCES_REMAIN')
        except BaseException:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def prewrite_failed(self,account,shop,pid,job):
        changed=self.db.execute("UPDATE executions SET state='PREWRITE_FAILED' WHERE account=? AND shop=? AND pid=? AND job=? AND state='RESERVED'",(account,shop,pid,job))
        if changed.rowcount!=1:raise ValueError('EXECUTION_LEDGER_SIDE_EFFECT_OR_BINDING_MISMATCH')

    def state(self,account,shop,pid,job):
        row=self.db.execute('SELECT state FROM executions WHERE account=? AND shop=? AND pid=? AND job=?',(account,shop,pid,job)).fetchone()
        return row[0] if row else None

    def finish(self,account,shop,pid,job,state):
        changed=self.db.execute('UPDATE executions SET state=? WHERE account=? AND shop=? AND pid=? AND job=?',(state,account,shop,pid,job))
        if changed.rowcount!=1:raise ValueError('EXECUTION_LEDGER_BINDING_MISMATCH')

    def close(self):self.db.close()


def _rejected_upload_source(source):
    from mye_c_automation.job_manager import JobManager
    from mye_c_automation.plan_v2 import validate_plan,plan_hash
    from mye_c_automation.product_state import canonical_state_hash
    if any((source/n).exists() for n in ('save_attempt.json','expected_after.json','apply_receipt.json')):raise ValueError('SAVE_STAGE_EVIDENCE_PRESENT')
    read=lambda n:json.loads((source/n).read_text(encoding='utf-8'))
    job=JobManager(source.parent).load(source.name);plan=validate_plan(read('plan.v2.json'))
    journal=read('local_execution.json');uploads=read('upload_receipts.json')
    if (plan['schema']!='token-opt-plan/v3' or job.get('image_workflow')!='v2' or
        (plan['job_id'],plan['pid'],plan['shop'])!=(job['job_id'],job['pid'],job['shop_id']) or
        plan['precondition']!={'state_sha256':job['input_state_sha256'],'account_fingerprint':job.get('account_fingerprint')} or
        canonical_state_hash(read('audit_product.json'))!=job['input_state_sha256'] or
        any(journal.get(k)!=v for k,v in dict(confirmed=True,job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],plan_sha256=plan_hash(plan),state='APPLY_UNKNOWN',error='RuntimeError').items())):
        raise ValueError('REJECTED_UPLOAD_BINDING_MISMATCH')
    if (not plan['post_actions'].get('uploads') or uploads.get('schema')!='upload-receipts/v1' or
        any(uploads.get(k)!=v for k,v in dict(job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],state='UPLOAD_UNKNOWN',upload_calls=1,uploads=[]).items()) or
        str(uploads.get('error','')).strip()!='HTTPError: HTTP Error 400:'):
        raise ValueError('NOT_REJECTED_FIRST_UPLOAD')
    names={'job.json','binding.json','plan.v2.json','audit_product.json','local_execution.json','upload_receipts.json'}
    names.update(r['path'] for r in plan['evidence_refs']+plan['ai_judgement_refs'])
    files={}
    for name in sorted(names):
        path=(source/name).resolve()
        if not path.is_relative_to(source):raise ValueError('UNSAFE_REJECTED_UPLOAD_EVIDENCE')
        files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    for ref in plan['evidence_refs']+plan['ai_judgement_refs']:
        if files[ref['path']]!=ref['sha256']:raise ValueError('REJECTED_UPLOAD_EVIDENCE_CHANGED')
    return job,plan,files


def verify_rejected_upload_proof(proof_path):
    """Revalidate immutable source evidence immediately before a new save."""
    proof=json.loads(Path(proof_path).read_text(encoding='utf-8'))
    if proof.get('schema')!='rejected-first-upload-followup/v1' or not proof.get('authorization_id') or proof.get('product_save_attempted') is not False:raise ValueError('INVALID_REJECTED_UPLOAD_PROOF')
    job,plan,files=_rejected_upload_source(Path(proof['source_directory']).resolve())
    if files!=proof['files']:raise ValueError('REJECTED_UPLOAD_SOURCE_CHANGED')
    return dict(account=job['account_fingerprint'],shop=job['shop_id'],pid=job['pid'],previous_job_id=job['job_id'],next_job=proof['next_job'],before_hash=job['input_state_sha256'])
