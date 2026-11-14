"""Persistent atomic budgets; failed attempts remain charged."""
import json
import sqlite3
from pathlib import Path
from threading import Lock

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
