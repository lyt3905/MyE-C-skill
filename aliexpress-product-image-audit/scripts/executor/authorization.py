"""HMAC tickets and SQLite atomic nonce consumption. Keep secret outside Agent access."""
from contextlib import closing
import hashlib
import hmac
import json
import sqlite3
import time
import math
from copy import deepcopy
from product_state import canonical_json
from plan_v2 import plan_hash

def sign(payload, secret):
    if len(secret) < 32:
        raise ValueError('secret must be at least 32 bytes')
    return {'payload':deepcopy(payload), 'signature':hmac.new(secret,canonical_json(payload).encode(),hashlib.sha256).hexdigest()}

class Authorization:
    def __init__(self, secret, nonce_database):
        if len(secret) < 32:
            raise ValueError('secret too short')
        self.secret = secret
        self.database = str(nonce_database)
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY)')

    def consume(self, ticket, plan):
        if type(ticket) is not dict or set(ticket) != {'payload','signature'} or type(ticket['payload']) is not dict or type(ticket['signature']) is not str:
            raise ValueError('invalid ticket')
        payload = deepcopy(ticket['payload'])
        expiry = payload.get('expires_at')
        if type(expiry) not in (int,float) or not math.isfinite(expiry):
            raise ValueError('invalid expiration')
        if type(payload.get('max_site_saves')) is not int or any(type(payload.get(k)) is not int for k in ('pid','shop')):
            raise ValueError('invalid ticket limits')
        expected = sign(payload,self.secret)['signature']
        if not hmac.compare_digest(expected,ticket['signature']):
            raise ValueError('invalid signature')
        for field in ('job_id','pid','shop'):
            if payload.get(field) != plan[field]:
                raise ValueError('identity mismatch')
        if payload.get('plan_sha256') != plan_hash(plan) or payload.get('expires_at',0) <= time.time():
            raise ValueError('expired or changed plan')
        post = plan['post_actions'] or {}
        required = {'site_save'} | ({'upload'} if post.get('uploads') else set()) | ({'translate_title'} if post.get('translate_title') else set())
        if set(payload.get('allowed_operations',[])) != required or payload.get('max_site_saves') != 1 or type(payload.get('max_translate_calls',0)) is not int or not 0 <= payload.get('max_translate_calls',0) <= 2 or (post.get('translate_title') and payload.get('max_translate_calls',0) < 1) or type(payload.get('max_upload_calls',0)) is not int or payload.get('max_upload_calls',0) < len(post.get('uploads',[])):
            raise ValueError('unsupported authority')
        nonce = payload.get('nonce')
        if not isinstance(nonce,str) or len(nonce) < 16:
            raise ValueError('invalid nonce')
        try:
            with closing(sqlite3.connect(self.database)) as conn, conn:
                conn.execute('INSERT INTO nonces VALUES (?)',(nonce,))
        except sqlite3.IntegrityError as exc:
            raise ValueError('ticket already consumed') from exc
