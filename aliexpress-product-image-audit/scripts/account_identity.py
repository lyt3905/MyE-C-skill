"""Server-observed principal binding; usernames and shop selection are not identities."""
import hashlib
import json
from urllib.parse import urlsplit

def fingerprint(base,response):
    endpoint=urlsplit(base)
    if endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        raise ValueError('ACCOUNT_SERVER_UNVERIFIED')
    data=response.get('data') if isinstance(response,dict) else None
    if not isinstance(data,dict):raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
    nested=data.get('user') if isinstance(data.get('user'),dict) else {}
    values=[v for v in (data.get('id'),data.get('userId'),nested.get('id')) if v is not None]
    if not values or any(type(v) not in (str,int) or not str(v).strip() or type(v) is int and v<=0 for v in values):
        raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
    ids={str(v).strip() for v in values}
    if len(ids)!=1:raise ValueError('ACCOUNT_PRINCIPAL_CONFLICT')
    server=endpoint.scheme+'://'+endpoint.netloc.lower()+endpoint.path.rstrip('/')
    return hashlib.sha256(json.dumps({'server':server,'principal_id':next(iter(ids))},sort_keys=True).encode()).hexdigest()
