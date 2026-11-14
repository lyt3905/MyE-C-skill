"""Fail-closed acceptance budgets. No HTTP, model, image or site dependencies.

SQLite FULL-synchronous transactions are the authoritative ledger, not the
human-readable usage export. STRICT never trusts arbitrary numeric bounds.
FAKE is explicitly separate and cannot grant real execution authorization.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

VERSION = '8788-token-budget-v1'
MAX_REQUESTS = 24
MAX_TOKENS = 300000
TRUSTED = {'DOCUMENTED_HARD_LIMIT', 'DOCUMENTED_EXACT_COUNT', 'DOCUMENTED_UPPER_BOUND'}
CAPABILITIES = Path(__file__).parent/'config/token.capabilities.v1.json'


class BudgetError(ValueError):
    pass


def now(): return datetime.now(timezone.utc).isoformat()


def integer(value): return type(value) is int and value >= 0


def provider_capability(endpoint, model_id):
    """Local audited route record, not an inference from a model brand name."""
    try:
        profile = json.loads(CAPABILITIES.read_text(encoding='utf-8'))
        cap = next((x for x in profile['providers'] if x['model_id'] == model_id and x['endpoint'] == endpoint), None)
        if profile['schema'] != '8788-provider-capabilities/v1': cap = None
    except (OSError, ValueError, KeyError, TypeError): cap = None
    if cap is None:
        return dict(provider='UNKNOWN', model_id=model_id, route_verified=False, usage_verified=False,
                    document_version=None, valid_until=None, blockers=['UNKNOWN_PROVIDER_OR_MODEL'])
    return deepcopy(cap)


def request_upper_bound(cap, *, image_count, mode='STRICT', today=None):
    result = dict(provider=cap.get('provider'), model_id=cap.get('model_id'),
                  input_text_upper_bound=None, image_input_upper_bound=None, other_input_upper_bound=None,
                  output_token_hard_limit=None, provider_overhead_upper_bound=None,
                  request_upper_bound=None, upper_bound_status='UNKNOWN', blockers=[])
    blockers = result['blockers']
    try:
        valid_date = date.fromisoformat(cap['valid_until']) >= (today or date.today())
    except (KeyError, TypeError, ValueError): valid_date = False
    if not valid_date or not cap.get('document_version') or not cap.get('api'):
        blockers.append('CAPABILITY_DOCUMENT_MISSING_OR_EXPIRED')
    if not cap.get('route_verified'): blockers.append('PROVIDER_ROUTE_UNVERIFIED')
    if not cap.get('usage_verified'): blockers.append('USAGE_PROVENANCE_UNVERIFIED')
    if mode not in ('STRICT', 'FAKE') or (cap.get('fake') and mode != 'FAKE'):
        blockers.append('FAKE_CAPABILITY_NOT_VALID_FOR_REAL_REQUESTS')
    if type(image_count) is not int or image_count < 0: blockers.append('INVALID_IMAGE_COUNT')
    fields = (('text', 'input_text_upper_bound'), ('image_per_input', 'image_input_upper_bound'),
              ('other_input', 'other_input_upper_bound'), ('output', 'output_token_hard_limit'),
              ('overhead', 'provider_overhead_upper_bound'))
    for key, destination in fields:
        proof = cap.get(key) or {}
        value = proof.get('value')
        if proof.get('status') not in TRUSTED or not integer(value) or not proof.get('source'):
            blockers.append(key.upper()+'_BOUND_UNPROVEN')
            continue
        if destination == 'image_input_upper_bound':
            if type(image_count) is not int or image_count < 0: continue
            value *= image_count
        result[destination] = value
    if not blockers:
        result['request_upper_bound'] = sum(result[k] for _, k in fields)
        result['upper_bound_status'] = 'DOCUMENTED_UPPER_BOUND'
    return result


def plan_budget(bounds):
    known = [r.get('request_upper_bound') for r in bounds]
    complete = len(bounds) == 24 and all(type(x) is int and x > 0 for x in known)
    total = sum(known) if complete else None
    passed = complete and total <= MAX_TOKENS and not any(r.get('blockers') for r in bounds)
    return dict(state='PREFLIGHT_PASS' if passed else 'PREFLIGHT_BLOCKED',
                max_provider_requests=MAX_REQUESTS, max_total_tokens=MAX_TOKENS,
                planned_requests=len(bounds), worst_case_total_tokens=total,
                TOKEN_CAP_PROVEN=passed, SPEND_CAP_PROVEN=False,
                missing_request_bounds=sum(x is None for x in known), requests=deepcopy(bounds))


def parse_usage(provider_schema, raw):
    """Parse documented totals; cache/image/reasoning subsets are never re-added."""
    if provider_schema.startswith('workbuddy:'):
        raise BudgetError('USAGE_PROVENANCE_UNVERIFIED')
    if provider_schema not in ('deepseek-direct', 'kimi-direct', 'fake-chat'):
        raise BudgetError('UNKNOWN_USAGE_SCHEMA')
    if not isinstance(raw, dict): raise BudgetError('USAGE_UNKNOWN')
    required = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    if any(not integer(raw.get(k)) for k in required): raise BudgetError('USAGE_UNKNOWN')
    if raw['prompt_tokens'] + raw['completion_tokens'] != raw['total_tokens']:
        raise BudgetError('USAGE_TOTAL_MISMATCH')
    allowed = set(required)
    if provider_schema != 'fake-chat': allowed |= {'prompt_tokens_details', 'completion_tokens_details'}
    if provider_schema == 'deepseek-direct': allowed |= {'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'}
    if provider_schema == 'kimi-direct': allowed |= {'cached_tokens'}
    if set(raw)-allowed: raise BudgetError('USAGE_SCHEMA_CHANGED')
    prompt, completion = raw['prompt_tokens'], raw['completion_tokens']
    for field, known, total in (
        ('prompt_tokens_details', {'cached_tokens', 'cache_write_tokens'} if provider_schema == 'kimi-direct' else {'cached_tokens'}, prompt),
        ('completion_tokens_details', {'reasoning_tokens', 'safety_tokens'} if provider_schema == 'deepseek-direct' else {'reasoning_tokens'}, completion),
    ):
        if field not in raw: continue
        detail = raw[field]
        if not isinstance(detail, dict) or set(detail)-known or any(not integer(v) or v > total for v in detail.values()):
            raise BudgetError('USAGE_DETAIL_MISMATCH')
    if provider_schema == 'deepseek-direct':
        hit, miss = raw.get('prompt_cache_hit_tokens'), raw.get('prompt_cache_miss_tokens')
        if not integer(hit) or not integer(miss) or hit+miss != prompt: raise BudgetError('USAGE_CACHE_MISMATCH')
        if raw.get('prompt_tokens_details', {}).get('cached_tokens', hit) != hit: raise BudgetError('USAGE_CACHE_MISMATCH')
    if provider_schema == 'kimi-direct':
        detail = raw.get('prompt_tokens_details', {})
        cached, written = detail.get('cached_tokens', 0), detail.get('cache_write_tokens', 0)
        if cached+written > prompt or ('cached_tokens' in raw and (not integer(raw['cached_tokens']) or raw['cached_tokens'] != cached)):
            raise BudgetError('USAGE_CACHE_MISMATCH')
    return dict(total_tokens=raw['total_tokens'], input_tokens=prompt, output_tokens=completion,
                usage_source=provider_schema, raw_usage=deepcopy(raw))


class TokenLedger:
    """One request in flight, atomic reserve/settle, persistent uncertain charges."""
    def __init__(self, path, job_id):
        self.path, self.job_id = Path(path), job_id
        self.poisoned = False

    @classmethod
    def create(cls, path, job_id, *, mode):
        if mode not in ('STRICT', 'FAKE') or not isinstance(job_id, str) or not job_id: raise BudgetError('INVALID_LEDGER_SCOPE')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        except OSError: raise BudgetError('LEDGER_ALREADY_EXISTS_OR_UNWRITABLE') from None
        ledger = cls(path, job_id)
        db = None
        try:
            db = ledger._db()
            db.executescript('''
                    CREATE TABLE meta(version TEXT, job_id TEXT, mode TEXT, max_requests INTEGER, max_tokens INTEGER, status TEXT);
                    CREATE TABLE requests(request_id TEXT PRIMARY KEY, metadata TEXT NOT NULL,
                        request_upper_bound INTEGER NOT NULL, reservation_status TEXT NOT NULL,
                        actual_tokens INTEGER, actual_usage TEXT, usage_source TEXT,
                        created_at TEXT NOT NULL, completed_at TEXT, error_code TEXT);
            ''')
            db.execute('INSERT INTO meta VALUES(?,?,?,?,?,?)', (VERSION, job_id, mode, 24, 300000, 'ACTIVE' if mode == 'FAKE' else 'PREFLIGHT_BLOCKED'))
            ledger._commit(db)
        except (OSError, sqlite3.Error):
            ledger._poison(); raise BudgetError('LEDGER_WRITE_FAILED') from None
        finally:
            if db is not None: db.close()
        return ledger

    @classmethod
    def open(cls, path, job_id):
        ledger = cls(path, job_id)
        # Reopening with an outstanding request can never silently resume it.
        with ledger._transaction() as db:
            if db.execute("SELECT count(*) FROM requests WHERE reservation_status IN ('RESERVED','DISPATCHED')").fetchone()[0]:
                db.execute("UPDATE requests SET reservation_status='UNKNOWN_COMMITTED', error_code='RESTART_UNRESOLVED', completed_at=? WHERE reservation_status IN ('RESERVED','DISPATCHED')", (now(),))
                db.execute("UPDATE meta SET status='UNKNOWN_COMMITTED'")
        return ledger

    def _poison(self):
        self.poisoned = True
        try:
            with self.path.with_suffix(self.path.suffix+'.failed').open('x', encoding='utf-8') as f:
                f.write('LEDGER_IO_FAILURE\n'); f.flush(); os.fsync(f.fileno())
        except OSError: pass

    def _db(self):
        if self.poisoned or self.path.with_suffix(self.path.suffix+'.failed').exists(): raise BudgetError('LEDGER_IO_FAILURE')
        if not self.path.is_file(): raise BudgetError('LEDGER_MISSING')
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA journal_mode=DELETE')
        except BaseException:
            db.close(); raise
        return db

    def _commit(self, db):
        if db.in_transaction: db.execute('COMMIT')

    def _validate(self, db):
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',): raise BudgetError('LEDGER_CORRUPT')
        rows = db.execute('SELECT * FROM meta').fetchall()
        if len(rows) != 1: raise BudgetError('LEDGER_VERSION_OR_SCOPE_MISMATCH')
        version, job, mode, requests, tokens, status = rows[0]
        if (version, job, requests, tokens) != (VERSION, self.job_id, 24, 300000) or mode not in ('STRICT', 'FAKE'):
            raise BudgetError('LEDGER_VERSION_OR_SCOPE_MISMATCH')
        if status not in ('ACTIVE', 'PREFLIGHT_BLOCKED', 'STOPPED', 'UNKNOWN_COMMITTED', 'BUDGET_GUARD_BREACH'):
            raise BudgetError('LEDGER_CORRUPT')
        entries = db.execute('SELECT request_upper_bound,reservation_status,actual_tokens,metadata,actual_usage,usage_source FROM requests').fetchall()
        if len(entries) > 24: raise BudgetError('LEDGER_CORRUPT')
        for bound, state, actual, metadata, usage, source in entries:
            if not integer(bound) or bound <= 0 or state not in ('RESERVED','DISPATCHED','SETTLED','RELEASED','UNKNOWN_COMMITTED'):
                raise BudgetError('LEDGER_CORRUPT')
            if state == 'SETTLED' and not integer(actual): raise BudgetError('LEDGER_CORRUPT')
            if state != 'SETTLED' and actual is not None: raise BudgetError('LEDGER_CORRUPT')
            if not isinstance(json.loads(metadata), dict): raise BudgetError('LEDGER_CORRUPT')
            if usage is not None: json.loads(usage)
            if state == 'SETTLED':
                if usage is None or not isinstance(source,str) or parse_usage(source,json.loads(usage))['total_tokens'] != actual:
                    raise BudgetError('LEDGER_CORRUPT')
                if actual > bound and status != 'BUDGET_GUARD_BREACH': raise BudgetError('LEDGER_CORRUPT')
        if sum(s in ('RESERVED','DISPATCHED') for b,s,a,m,u,p in entries) > 1: raise BudgetError('LEDGER_CORRUPT')
        if any(s == 'UNKNOWN_COMMITTED' for b,s,a,m,u,p in entries) and status != 'UNKNOWN_COMMITTED':
            raise BudgetError('LEDGER_CORRUPT')
        committed = sum(a if s == 'SETTLED' else b if s in ('RESERVED','DISPATCHED','UNKNOWN_COMMITTED') else 0
                        for b,s,a,m,u,p in entries)
        if committed > MAX_TOKENS and status != 'BUDGET_GUARD_BREACH': raise BudgetError('LEDGER_CORRUPT')
        return mode, status

    @contextmanager
    def _transaction(self):
        db = None
        try:
            db = self._db(); db.execute('BEGIN IMMEDIATE'); self._validate(db)
            yield db
            self._commit(db)
        except BudgetError:
            if db is not None and db.in_transaction: db.execute('ROLLBACK')
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            if db is not None and db.in_transaction:
                try: db.execute('ROLLBACK')
                except sqlite3.Error: pass
            self._poison(); raise BudgetError('LEDGER_IO_OR_CORRUPTION_FAILURE') from None
        finally:
            if db is not None: db.close()

    def _snapshot(self, db):
        mode, status = self._validate(db)
        rows = db.execute('SELECT reservation_status,request_upper_bound,actual_tokens FROM requests').fetchall()
        actual = sum(a for s,b,a in rows if s == 'SETTLED')
        reserved = sum(b for s,b,a in rows if s in ('RESERVED','DISPATCHED'))
        unknown = sum(b for s,b,a in rows if s == 'UNKNOWN_COMMITTED')
        return dict(budget_version=VERSION, job_id=self.job_id, mode=mode, max_provider_requests=24,
                    max_total_tokens=300000, max_in_flight_requests=1, actual_tokens=actual,
                    reserved_tokens=reserved, unknown_committed_tokens=unknown,
                    committed_tokens=actual+reserved+unknown, remaining_tokens=max(0,300000-actual-reserved-unknown),
                    request_count=len(rows), total_tokens=None if unknown or reserved else actual,
                    status=status, requests=len(rows), known_total_tokens=actual,
                    usage_status='USAGE_UNKNOWN' if unknown else 'PENDING' if reserved else 'KNOWN',
                    pending_reservation=reserved+unknown or None,
                    stop_reason=None if status == 'ACTIVE' else status)

    def snapshot(self):
        with self._transaction() as db: return self._snapshot(db)

    @property
    def requests(self): return self.snapshot()['request_count']

    @property
    def stopped(self): return self.snapshot()['stop_reason']

    def reserve(self, request_id, bound, metadata):
        with self._transaction() as db:
            snap = self._snapshot(db)
            if snap['mode'] != 'FAKE':
                # No audited current provider can supply a complete bound. Do
                # not accept caller-supplied numeric claims as proof in STRICT.
                raise BudgetError('PROVIDER_CAPABILITY_UNVERIFIED')
            if type(bound) is not int or bound <= 0: raise BudgetError('TOKEN_CEILING_UNVERIFIED')
            if snap['status'] != 'ACTIVE': raise BudgetError('BUDGET_STOPPED')
            if db.execute('SELECT 1 FROM requests WHERE request_id=?',(request_id,)).fetchone(): raise BudgetError('DUPLICATE_REQUEST_ID')
            if snap['reserved_tokens']: raise BudgetError('CONCURRENT_REQUEST_FORBIDDEN')
            if snap['request_count'] >= 24: raise BudgetError('REQUEST_LIMIT')
            if snap['committed_tokens']+bound > 300000: raise BudgetError('TOKEN_LIMIT')
            required = {'provider','model_id','task_type','image_sha256','prompt_version','schema_version','request_body_sha256',
                        'input_text_upper_bound','image_input_upper_bound','other_input_upper_bound',
                        'output_token_hard_limit','provider_overhead_upper_bound','upper_bound_status','proof_source'}
            if not isinstance(request_id,str) or not request_id or not isinstance(metadata,dict) or not required<=set(metadata):
                raise BudgetError('RESERVATION_METADATA_MISSING')
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (request_id,json.dumps(metadata,allow_nan=False),bound,'RESERVED',None,None,None,now(),None,None))

    def mark_sent(self, request_id):
        with self._transaction() as db:
            if self._snapshot(db)['status'] != 'ACTIVE': raise BudgetError('BUDGET_STOPPED')
            changed = db.execute("UPDATE requests SET reservation_status='DISPATCHED' WHERE request_id=? AND reservation_status='RESERVED'",(request_id,))
            if changed.rowcount != 1: raise BudgetError('INVALID_RESERVATION_STATE')

    def settle(self, request_id, raw_usage, provider_schema):
        error = None
        with self._transaction() as db:
            row = db.execute('SELECT request_upper_bound,reservation_status FROM requests WHERE request_id=?',(request_id,)).fetchone()
            if row is None or row[1] != 'DISPATCHED': raise BudgetError('INVALID_SETTLEMENT_STATE')
            try: parsed = parse_usage(provider_schema, raw_usage)
            except BudgetError as exc:
                db.execute("UPDATE requests SET reservation_status='UNKNOWN_COMMITTED',actual_usage=?,usage_source=?,completed_at=?,error_code=? WHERE request_id=?",
                           (json.dumps(raw_usage,allow_nan=False),provider_schema,now(),str(exc),request_id))
                db.execute("UPDATE meta SET status='UNKNOWN_COMMITTED'")
                error = 'USAGE_UNKNOWN:'+str(exc)
            else:
                breach = parsed['total_tokens'] > row[0]
                db.execute("UPDATE requests SET reservation_status='SETTLED',actual_tokens=?,actual_usage=?,usage_source=?,completed_at=?,error_code=? WHERE request_id=?",
                    (parsed['total_tokens'],json.dumps(raw_usage,allow_nan=False),provider_schema,now(),'BUDGET_GUARD_BREACH' if breach else None,request_id))
                if breach:
                    db.execute("UPDATE meta SET status='BUDGET_GUARD_BREACH'"); error = 'BUDGET_GUARD_BREACH'
        if error: raise BudgetError(error)

    def mark_unknown(self, request_id, reason):
        with self._transaction() as db:
            row = db.execute('SELECT reservation_status FROM requests WHERE request_id=?',(request_id,)).fetchone()
            if row is None or row[0] not in ('RESERVED','DISPATCHED','UNKNOWN_COMMITTED'): raise BudgetError('INVALID_UNKNOWN_STATE')
            db.execute("UPDATE requests SET reservation_status='UNKNOWN_COMMITTED',completed_at=?,error_code=? WHERE request_id=?",(now(),reason,request_id))
            db.execute("UPDATE meta SET status='UNKNOWN_COMMITTED'")

    def stop(self, reason):
        with self._transaction() as db:
            db.execute("UPDATE meta SET status='STOPPED' WHERE status='ACTIVE'")

    def release(self, request_id, proof):
        with self._transaction() as db:
            if proof != 'LOCAL_NOT_SENT': raise BudgetError('RELEASE_REQUIRES_VERIFIED_NOT_SENT')
            changed = db.execute("UPDATE requests SET reservation_status='RELEASED',completed_at=?,error_code='LOCAL_NOT_SENT' WHERE request_id=? AND reservation_status='RESERVED'",(now(),request_id))
            if changed.rowcount != 1: raise BudgetError('UNSAFE_OR_DUPLICATE_RELEASE')

    def records(self):
        with self._transaction() as db:
            rows = db.execute('SELECT * FROM requests ORDER BY created_at,request_id').fetchall()
        return [dict(request_id=r[0],job_id=self.job_id,**json.loads(r[1]),request_upper_bound=r[2],
                     reservation_status=r[3],actual_tokens=r[4],actual_usage=json.loads(r[5]) if r[5] else None,
                     usage_source=r[6],created_at=r[7],completed_at=r[8],error_code=r[9]) for r in rows]


class DurableFakeBudget:
    """Compatibility facade for the existing injected-Fake runner only.

    Cached snapshots are for partial error reports. Admission always uses the
    database; an unreadable ledger never grants a request from cached balance.
    """
    def __init__(self, path, job_id):
        self.ledger = TokenLedger.create(path, job_id, mode='FAKE')
        self.cached = self.ledger.snapshot()
        self.current = None
        self.error = None
        self.io_failed = False

    @property
    def requests(self): return self.snapshot()['request_count']

    @property
    def stopped(self): return self.error or self.snapshot()['stop_reason']

    def snapshot(self):
        if not self.io_failed:
            try: self.cached = self.ledger.snapshot()
            except BudgetError:
                self.io_failed = True; self.error = 'LEDGER_IO_FAILURE'
        value = deepcopy(self.cached)
        if self.io_failed:
            value.update(total_tokens=None, usage_status='USAGE_UNKNOWN', status='LEDGER_IO_FAILURE',
                         stop_reason=self.error, ledger_readable=False)
        return value

    def reserve(self, bound, metadata):
        if self.error or self.io_failed: raise BudgetError(self.error or 'LEDGER_IO_FAILURE')
        request_id = f'R{self.requests+1:02d}'
        self.ledger.reserve(request_id, bound, metadata)
        self.current = request_id
        self.snapshot()

    def mark_sent(self):
        self.ledger.mark_sent(self.current)
        self.snapshot()

    def settle(self, raw):
        self.ledger.settle(self.current, raw, 'fake-chat')
        self.snapshot()

    def fail(self, reason):
        self.error = self.error or reason
        try:
            rows = [r for r in self.ledger.records() if r['request_id'] == self.current]
            if rows and rows[0]['reservation_status'] in ('RESERVED', 'DISPATCHED', 'UNKNOWN_COMMITTED'):
                self.ledger.mark_unknown(self.current, reason)
            else: self.ledger.stop(reason)
        except BudgetError:
            self.io_failed = True
