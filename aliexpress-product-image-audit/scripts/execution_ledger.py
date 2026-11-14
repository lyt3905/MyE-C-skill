"""Account/PID idempotency survives job IDs, output roots and process restarts."""
import hashlib
import json
from pathlib import Path
import sqlite3
from account_coordination import DEFAULT_DIRECTORY

def operation_digest(plan):
    post=dict(plan.get('post_actions') or {})
    if post.get('uploads'):
        post['uploads']=[{k:v for k,v in row.items() if k!='path'} for row in post['uploads']]
    value={'desired':plan['desired'],'post_actions':post}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class ExecutionLedger:
    def __init__(self,path=None):
        path=Path(path or DEFAULT_DIRECTORY.parent/'execution_ledger.sqlite');path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None)
        self.db.execute('CREATE TABLE IF NOT EXISTS executions (account TEXT, shop INTEGER, pid INTEGER, job TEXT, before_hash TEXT, operation TEXT, state TEXT, PRIMARY KEY(account,shop,pid))')

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
