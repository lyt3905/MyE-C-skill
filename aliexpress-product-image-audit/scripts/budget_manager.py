"""Persistent atomic budgets; failed attempts remain charged."""
import json
import sqlite3
from pathlib import Path
from threading import Lock, local
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timezone
import uuid

class BudgetExceeded(RuntimeError):
    pass

class BudgetManager:
    def __init__(self, limits, path=None):
        if any(type(v) is not int or v < 0 for v in limits.values()):
            raise ValueError('invalid budget')
        self._limits = dict(limits)
        self._lock = Lock()
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path) if path else ':memory:', timeout=30, check_same_thread=False, isolation_level=None)
        self._model_path=Path(path) if path else None
        self._model_failed=bool(self._model_path and self._model_path.with_suffix('.model-failed').exists())
        self._model_policy=None
        self._dispatch=local()
        self._db.execute('PRAGMA synchronous=FULL')
        self._db.execute('CREATE TABLE IF NOT EXISTS token_usage (id INTEGER PRIMARY KEY, actual INTEGER, known INTEGER)')
        self._db.execute('INSERT OR IGNORE INTO token_usage VALUES (1,0,1)')
        self._db.execute('CREATE TABLE IF NOT EXISTS token_calls (id INTEGER PRIMARY KEY, calls INTEGER)')
        self._db.execute('INSERT OR IGNORE INTO token_calls VALUES (1,0)')
        self._db.execute('CREATE TABLE IF NOT EXISTS budgets (resource TEXT PRIMARY KEY, cap INTEGER, used INTEGER)')
        with self._transaction():
            existing = dict(self._db.execute('SELECT resource, cap FROM budgets'))
            if existing and existing != limits:
                raise ValueError('persisted budget limits changed')
            for resource, cap in limits.items():
                self._db.execute('INSERT OR IGNORE INTO budgets VALUES (?, ?, 0)', (resource, cap))

    def configure_model_budget(self, config, job_id):
        """Freeze an explicit, new-Job controlled policy into the existing ledger."""
        if isinstance(config,dict) and config.get('mode')=='RECORD_ONLY':
            return self._configure_record_only(config,job_id)
        if not isinstance(config,dict) or config.get('mode')!='CONTROLLED_CANARY':
            raise BudgetExceeded('PREFLIGHT_BLOCKED: STRICT provider capability unverified')
        required={'mode','enabled','authorization_id','max_requests','max_products','max_images',
                  'max_images_per_request','max_output_tokens','token_soft_limit','reserve_tokens','usd_stop',
                  'models','endpoints','max_in_flight','retries','usage_source','price'}
        if not required<=set(config) or config['enabled'] is not True or not config['authorization_id'] or not job_id:
            raise BudgetExceeded('MODEL_BUDGET_AUTHORIZATION_REQUIRED')
        for key in ('max_requests','max_products','max_images','max_images_per_request','max_output_tokens','token_soft_limit','reserve_tokens'):
            if type(config[key]) is not int or config[key]<=0:raise BudgetExceeded('INVALID_MODEL_BUDGET:'+key)
        if type(config['max_in_flight']) is not int or config['max_in_flight']!=1 or type(config['retries']) is not int or config['retries']!=0:
            raise BudgetExceeded('SERIAL_NO_RETRY_REQUIRED')
        if config['reserve_tokens']<config['max_output_tokens']:raise BudgetExceeded('INVALID_TOKEN_RESERVATION')
        for key in ('models','endpoints'):
            if not isinstance(config[key],list) or not config[key] or any(not isinstance(v,str) or not v for v in config[key]):
                raise BudgetExceeded('MODEL_ROUTE_WHITELIST_REQUIRED')
        if config['usage_source'] not in {'GATEWAY_REPORTED_UNVERIFIED','CLIENT_ESTIMATE'}:
            # A caller's boolean cannot prove provider billing provenance.
            raise BudgetExceeded('USAGE_PROVENANCE_UNVERIFIED')
        price=config['price']
        try:
            valid=(isinstance(price,dict) and price['source'] and price['currency']=='USD'
                   and price['endpoint'] in config['endpoints'] and set(price['models'])==set(config['models'])
                   and date.fromisoformat(price['valid_until'])>=date.today()
                   and price['image_included'] is True and price['cache_included'] is True)
        except (KeyError,ValueError,TypeError):valid=False
        if not valid:raise BudgetExceeded('PRICE_UNKNOWN_OR_EXPIRED')
        for value in (config['usd_stop'],price.get('input_per_million'),price.get('output_per_million')):
            self._money(value)
        frozen=json.dumps(config,sort_keys=True,allow_nan=False)
        with self._lock,self._transaction():
            self._db.execute('CREATE TABLE IF NOT EXISTS model_scope (job TEXT, policy TEXT, status TEXT)')
            self._db.execute('CREATE TABLE IF NOT EXISTS model_calls (id TEXT PRIMARY KEY, state TEXT, reserved INTEGER, reserved_usd TEXT, actual INTEGER, usd TEXT, usage TEXT, metadata TEXT)')
            rows=self._db.execute('SELECT job,policy FROM model_scope').fetchall()
            if rows and rows!=[(job_id,frozen)]:raise BudgetExceeded('MODEL_BUDGET_SCOPE_CHANGED')
            if not rows:self._db.execute('INSERT INTO model_scope VALUES (?,?,?)',(job_id,frozen,'ACTIVE'))
            if self._db.execute("SELECT count(*) FROM model_calls WHERE state IN ('RESERVED','DISPATCHED')").fetchone()[0]:
                self._db.execute("UPDATE model_calls SET state='UNKNOWN' WHERE state IN ('RESERVED','DISPATCHED')")
                self._db.execute("UPDATE model_scope SET status='UNKNOWN'")
        self._model_policy=json.loads(frozen)
        self._model_job_id=job_id

    def _configure_record_only(self,config,job_id):
        config=dict(config,usage_source=config.get('usage_source','GATEWAY_REPORTED_UNVERIFIED'))
        frozen=json.dumps(config,sort_keys=True,allow_nan=False)
        with self._lock,self._transaction():
            self._db.execute('CREATE TABLE IF NOT EXISTS model_scope (job TEXT, policy TEXT, status TEXT)')
            self._db.execute('CREATE TABLE IF NOT EXISTS model_calls (id TEXT PRIMARY KEY, state TEXT, reserved INTEGER, reserved_usd TEXT, actual INTEGER, usd TEXT, usage TEXT, metadata TEXT)')
            rows=self._db.execute('SELECT job,policy FROM model_scope').fetchall()
            if rows and rows!=[(job_id,frozen)]:raise ValueError('MODEL_RECORD_SCOPE_CHANGED')
            if not rows:self._db.execute('INSERT INTO model_scope VALUES (?,?,?)',(job_id,frozen,'RECORD_ONLY'))
        self._model_policy=json.loads(frozen);self._model_job_id=job_id

    @property
    def record_only(self):
        if self._model_policy is None and self._model_path:
            job_path=self._model_path.parent/'job.json'
            if job_path.is_file():
                from job_manager import JobManager
                job=JobManager(job_path.parent.parent).load(job_path.parent.name)
                if (job.get('model_budget') or {}).get('mode')=='RECORD_ONLY':
                    self.configure_model_budget(job['model_budget'],job['job_id'])
                    self._model_pid=job['pid']
        return bool(self._model_policy and self._model_policy.get('mode')=='RECORD_ONLY')

    def _record_only_call(self,model,endpoint,pid,images,output_limit,metadata,transport):
        request_id=uuid.uuid4().hex
        record=dict(metadata,model=model,endpoint=endpoint,pid=pid,images=images,output_limit=output_limit,
                    created_at=datetime.now(timezone.utc).isoformat(),usage_source=self._model_policy['usage_source'])
        with self._lock,self._transaction():
            self._db.execute('INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?)',(request_id,'DISPATCHED',0,'0',None,None,None,json.dumps(record)))
        self._dispatch.active=True
        raw=None
        try:
            raw=transport()
            return raw
        finally:
            self._dispatch.active=False
            usage=raw.get('usage') if isinstance(raw,dict) else None
            valid=(isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens'))
                   and usage['prompt_tokens']+usage['completion_tokens']==usage['total_tokens'])
            record.update(raw_response=raw,completed_at=datetime.now(timezone.utc).isoformat(),usage_source=self._model_policy['usage_source'] if valid else 'MISSING')
            with self._lock,self._transaction():
                self._db.execute('UPDATE model_calls SET state=?,actual=?,usage=?,metadata=? WHERE id=?',
                    ('SETTLED' if valid else 'UNKNOWN',usage['total_tokens'] if valid else None,json.dumps(usage),json.dumps(record),request_id))
                self._db.execute('UPDATE token_calls SET calls=calls+1 WHERE id=1')
                if valid:self._db.execute('UPDATE token_usage SET actual=actual+? WHERE id=1',(usage['total_tokens'],))
                else:self._db.execute('UPDATE token_usage SET known=0 WHERE id=1')

    @staticmethod
    def _money(value):
        if isinstance(value,bool) or value is None:raise BudgetExceeded('PRICE_OR_USD_UNKNOWN')
        try:result=Decimal(str(value))
        except (InvalidOperation,ValueError):raise BudgetExceeded('PRICE_OR_USD_UNKNOWN') from None
        if not result.is_finite() or result<=0:raise BudgetExceeded('PRICE_OR_USD_UNKNOWN')
        return result

    def _load_model_budget(self):
        if self._model_failed:raise BudgetExceeded('MODEL_LEDGER_FAILED')
        if self._model_policy is not None:return
        # The Job binding is authoritative; no environment-budget fallback.
        path=Path(self._db.execute('PRAGMA database_list').fetchone()[2])
        job_path=path.parent/'job.json'
        if not job_path.is_file():raise BudgetExceeded('MODEL_BUDGET_AUTHORIZATION_REQUIRED')
        from job_manager import JobManager
        job=JobManager(path.parent.parent).load(path.parent.name)
        if (job.get('model_budget') or {}).get('mode')!='RECORD_ONLY' and job['mode'] not in {'audit','dry_run'}:raise BudgetExceeded('CANARY_READ_ONLY_REQUIRED')
        self.configure_model_budget(job.get('model_budget'),job['job_id'])
        self._model_pid=job['pid']

    def assert_model_dispatch(self):
        if not getattr(self._dispatch,'active',False):raise BudgetExceeded('UNRESERVED_MODEL_DISPATCH')

    def model_snapshot(self):
        if self.record_only:
            rows=self._db.execute('SELECT state,actual FROM model_calls').fetchall()
            unknown=any(value is None for state,value in rows)
            return dict(mode='RECORD_ONLY',status='RECORD_ONLY',requests=len(rows),known_tokens=sum(v for state,v in rows if v is not None),
                        total_tokens=None if unknown else sum(v for state,v in rows),reserved_tokens=0,known_usd=None,committed_usd=None,
                        usage_source='MISSING' if unknown else self._model_policy['usage_source'],SPEND_CAP_GUARANTEED=False)
        if self._db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise BudgetExceeded('MODEL_LEDGER_CORRUPT')
        scope=self._db.execute('SELECT job,policy,status FROM model_scope').fetchall()
        if len(scope)!=1 or scope[0][:2]!=(self._model_job_id,json.dumps(self._model_policy,sort_keys=True,allow_nan=False)):
            raise BudgetExceeded('MODEL_BUDGET_SCOPE_CHANGED')
        rows=self._db.execute('SELECT state,reserved,reserved_usd,actual,usd,metadata FROM model_calls').fetchall()
        if any(s not in {'RESERVED','DISPATCHED','UNKNOWN','SETTLED'} or type(b) is not int or b<=0 or
               (s=='SETTLED' and (type(a) is not int or a<0 or c is None)) for s,b,u,a,c,m in rows):
            raise BudgetExceeded('MODEL_LEDGER_CORRUPT')
        price=self._model_policy['price']
        for state,bound,held,actual,cost,raw_usage in self._db.execute('SELECT state,reserved,reserved_usd,actual,usd,usage FROM model_calls'):
            expected_held=Decimal(bound)*max(self._money(price['input_per_million']),self._money(price['output_per_million']))/Decimal(1000000)
            if bound!=self._model_policy['reserve_tokens'] or Decimal(held)!=expected_held or state!='SETTLED' and actual is not None:
                raise BudgetExceeded('MODEL_LEDGER_CORRUPT')
            if state=='SETTLED':
                try:
                    usage=json.loads(raw_usage)
                    valid=(all(type(usage[k]) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens','total_tokens')) and
                           usage['prompt_tokens']+usage['completion_tokens']==usage['total_tokens']==actual)
                    expected_cost=(Decimal(usage['prompt_tokens'])*self._money(price['input_per_million'])+Decimal(usage['completion_tokens'])*self._money(price['output_per_million']))/Decimal(1000000)
                    valid=valid and Decimal(cost)==expected_cost
                except (ValueError,KeyError,TypeError,InvalidOperation):valid=False
                if not valid:raise BudgetExceeded('MODEL_LEDGER_CORRUPT')
        known=sum(a for s,b,u,a,c,m in rows if s=='SETTLED')
        reserved=sum(b for s,b,u,a,c,m in rows if s!='SETTLED')
        usd=sum((Decimal(c) for s,b,u,a,c,m in rows if s=='SETTLED'),Decimal(0))
        committed=usd+sum((Decimal(u) for s,b,u,a,c,m in rows if s!='SETTLED'),Decimal(0))
        return dict(status=scope[0][2],requests=len(rows),known_tokens=known,reserved_tokens=reserved,
                    total_tokens=None if reserved else known,known_usd=str(usd),committed_usd=str(committed),
                    usage_source='MISSING' if reserved else self._model_policy['usage_source'],
                    configured_usage_source=self._model_policy['usage_source'],SPEND_CAP_GUARANTEED=False,
                    products=sorted({json.loads(m).get('pid') for s,b,u,a,c,m in rows if json.loads(m).get('pid') is not None}),
                    images=sorted({i for s,b,u,a,c,m in rows for i in json.loads(m).get('images',[])}))

    def model_call(self, *args, **kwargs):
        try:return self._model_call(*args,**kwargs)
        except sqlite3.Error:
            self._model_failed=True
            if self._model_path:
                try:self._model_path.with_suffix('.model-failed').write_text('MODEL_LEDGER_IO_FAILED\n',encoding='utf-8')
                except OSError:pass
            raise BudgetExceeded('MODEL_LEDGER_IO_FAILED') from None

    def _model_call(self, model, endpoint, pid, images, output_limit, metadata, transport):
        """One durable reservation and one dispatch. Unknown retains its charge."""
        self._load_model_budget();p=self._model_policy
        if self.record_only:return self._record_only_call(model,endpoint,pid,images,output_limit,metadata,transport)
        if (getattr(self,'_model_pid',pid)!=pid or model not in p['models'] or endpoint not in p['endpoints'] or endpoint!=p['price']['endpoint'] or
                type(pid) is not int or pid<=0 or type(output_limit) is not int or not 0<output_limit<=p['max_output_tokens'] or
                not isinstance(images,list) or len(images)>p['max_images_per_request'] or
                any(not isinstance(v,str) or len(v)!=64 for v in images)):
            raise BudgetExceeded('MODEL_REQUEST_OUT_OF_SCOPE')
        bound=p['reserve_tokens'];price=p['price']
        reserved_usd=Decimal(bound)*max(self._money(price['input_per_million']),self._money(price['output_per_million']))/Decimal(1000000)
        request_id=uuid.uuid4().hex
        record=dict(metadata,created_at=datetime.now(timezone.utc).isoformat(),pid=pid,images=images,model=model,endpoint=endpoint,output_limit=output_limit,
                    usage_source=p['usage_source'],reservation_algorithm='configured_total_token_soft_reservation_v1',
                    TOKEN_CAP_PROVEN=False,SPEND_CAP_GUARANTEED=False)
        with self._lock,self._transaction():
            s=self.model_snapshot()
            if s['status']!='ACTIVE' or s['reserved_tokens']:raise BudgetExceeded('MODEL_BUDGET_STOPPED_OR_IN_FLIGHT')
            if (s['requests']>=p['max_requests'] or s['known_tokens']+bound>p['token_soft_limit'] or
                    Decimal(s['committed_usd'])+reserved_usd>self._money(p['usd_stop']) or
                    len(set(s['products'])|{pid})>p['max_products'] or len(set(s['images'])|set(images))>p['max_images']):
                raise BudgetExceeded('MODEL_BUDGET_LIMIT')
            self._db.execute('INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?)',
                             (request_id,'RESERVED',bound,str(reserved_usd),None,None,None,json.dumps(record,allow_nan=False)))
        try:
            with self._lock,self._transaction():
                self._db.execute("UPDATE model_calls SET state='DISPATCHED' WHERE id=?",(request_id,))
            self._dispatch.active=True
            raw=transport()
            if isinstance(raw,dict) and raw.get('model',model)!=model:raise BudgetExceeded('RESPONSE_MODEL_CHANGED')
            usage=raw.get('usage') if isinstance(raw,dict) else None
            record.update(raw_response=raw,observed_at=datetime.now(timezone.utc).isoformat())
            with self._lock,self._transaction():
                self._db.execute('UPDATE model_calls SET usage=?,metadata=? WHERE id=?',(json.dumps(usage,allow_nan=False),json.dumps(record,allow_nan=False),request_id))
            if (not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('prompt_tokens','completion_tokens','total_tokens')) or
                    usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']):
                raise BudgetExceeded('MODEL_USAGE_MISSING_OR_INVALID')
            cost=(Decimal(usage['prompt_tokens'])*self._money(price['input_per_million'])+
                  Decimal(usage['completion_tokens'])*self._money(price['output_per_million']))/Decimal(1000000)
            with self._lock,self._transaction():
                self._db.execute("UPDATE model_calls SET state='SETTLED',actual=?,usd=?,usage=? WHERE id=?",
                                 (usage['total_tokens'],str(cost),json.dumps(usage,allow_nan=False),request_id))
                snap=self.model_snapshot()
                breach=(usage['total_tokens']>bound or snap['known_tokens']>=p['token_soft_limit'] or Decimal(snap['known_usd'])>=self._money(p['usd_stop']))
                if breach:self._db.execute("UPDATE model_scope SET status='STOPPED'")
            if breach:raise BudgetExceeded('MODEL_SOFT_BUDGET_REACHED_OR_RESERVATION_EXCEEDED')
            return raw
        except BaseException:
            try:
                with self._lock,self._transaction():
                    changed=self._db.execute("UPDATE model_calls SET state='UNKNOWN' WHERE id=? AND state!='SETTLED'",(request_id,))
                    if changed.rowcount:self._db.execute("UPDATE model_scope SET status='UNKNOWN'")
            except BaseException:
                self._model_policy=None
            raise
        finally:self._dispatch.active=False

    def _transaction(self):
        from contextlib import contextmanager
        @contextmanager
        def transaction():
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise
        return transaction()

    def reserve(self, resource, amount=1):
        if type(amount) is not int or amount <= 0:
            raise ValueError('positive reservation required')
        with self._lock, self._transaction():
            result = self._db.execute('UPDATE budgets SET used=used+? WHERE resource=? AND used+?<=cap', (amount, resource, amount))
            if result.rowcount != 1:
                raise BudgetExceeded(resource)

    def reserve_tokens(self, amount):
        if type(amount) is not int or amount <= 0:
            raise ValueError('positive reservation required')
        with self._lock, self._transaction():
            known = self._db.execute('SELECT known FROM token_usage WHERE id=1').fetchone()[0]
            if not known:
                raise BudgetExceeded('token usage UNKNOWN')
            result = self._db.execute("UPDATE budgets SET used=used+? WHERE resource='total_tokens' AND used+?<=cap", (amount, amount))
            if result.rowcount != 1:
                raise BudgetExceeded('total_tokens')
        return amount

    def reserve_call(self,token_cost=None,image_count=0):
        """Admit images, tokens and one request in a single rollbackable transaction."""
        if type(image_count) is not int or image_count<0 or (token_cost is not None and (type(token_cost) is not int or token_cost<=0)):
            raise ValueError('invalid call reservation')
        if self.record_only:
            with self._lock,self._transaction():
                self._db.execute("UPDATE budgets SET used=used+1 WHERE resource='ai_requests'")
                self._db.execute("UPDATE budgets SET used=used+? WHERE resource='full_resolution_images'",(image_count,))
            return None
        with self._lock,self._transaction():
            if token_cost is not None and not self._db.execute('SELECT known FROM token_usage WHERE id=1').fetchone()[0]:
                raise BudgetExceeded('token usage UNKNOWN')
            reservations=[]
            if image_count:reservations.append(('full_resolution_images',image_count))
            if token_cost is not None:reservations.append(('total_tokens',token_cost))
            reservations.append(('ai_requests',1))
            for resource,amount in reservations:
                changed=self._db.execute('UPDATE budgets SET used=used+? WHERE resource=? AND used+?<=cap',(amount,resource,amount))
                if changed.rowcount!=1:raise BudgetExceeded(resource)
        return token_cost

    def release_tokens(self, reserved):
        if type(reserved) is not int or reserved <= 0: raise ValueError('invalid reservation')
        with self._lock, self._transaction():
            changed=self._db.execute("UPDATE budgets SET used=used-? WHERE resource='total_tokens' AND used>=?",(reserved,reserved))
            if changed.rowcount != 1: raise ValueError('missing reservation')

    def settle_tokens(self, reserved, usage):
        if type(reserved) is not int or reserved <= 0:
            raise ValueError('invalid token reservation')
        self._db.execute('UPDATE token_calls SET calls=calls+1 WHERE id=1')
        if usage is None:
            self.mark_tokens_unknown()
            return
        if type(usage) is not int or usage < 0:
            raise ValueError('invalid actual tokens')
        with self._lock, self._transaction():
            row = self._db.execute("SELECT used,cap FROM budgets WHERE resource='total_tokens'").fetchone()
            if row is None or row[0] < reserved:
                raise ValueError('missing token reservation')
            self._db.execute("UPDATE budgets SET used=used-?+? WHERE resource='total_tokens'", (reserved, usage))
            self._db.execute('UPDATE token_usage SET actual=actual+? WHERE id=1', (usage,))
            exceeded = row[0]-reserved+usage > row[1]
        if exceeded:
            raise BudgetExceeded('total_tokens')

    def mark_tokens_unknown(self):
        with self._lock:
            self._db.execute('UPDATE token_usage SET known=0 WHERE id=1')

    def snapshot(self):
        with self._lock:
            rows = list(self._db.execute('SELECT resource, cap, used FROM budgets'))
            actual, known = self._db.execute('SELECT actual,known FROM token_usage WHERE id=1').fetchone()
            return {'limits': {r: c for r,c,u in rows}, 'used': {r:u for r,c,u in rows}, 'actual_tokens': actual if known else None, 'token_status': ('UNKNOWN' if not known else ('NOT_CALLED' if not self._db.execute('SELECT calls FROM token_calls WHERE id=1').fetchone()[0] else ('ACTUAL_ZERO' if actual == 0 else 'ACTUAL_REPORTED')))}

    def close(self):
        self._db.close()
