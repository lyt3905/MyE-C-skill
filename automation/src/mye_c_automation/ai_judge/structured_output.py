"""Canonical V2 structure checks and protocol utilities, not an AI client.

Responses builders describe a requested contract. They never certify that a
gateway enforces it. Current deployment uses explicit JSON + local validation.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator,SchemaError

SCHEMA_PATH=Path(__file__).resolve().parents[1]/'config/schemas/image-action-decision.v2.schema.json'
SCHEMA_NAME='myec_image_action_decision_v2'
CODES={'API_ERROR','EMPTY_OUTPUT','INVALID_JSON','SCHEMA_VALIDATION_FAILED','BUSINESS_VALIDATION_FAILED',
       'RESPONSE_INCOMPLETE','MAX_OUTPUT_TOKENS','GATEWAY_UNSUPPORTED'}


def _check_schema(schema):
    try:Draft202012Validator.check_schema(schema)
    except SchemaError as exc:raise ValueError('SCHEMA_COMPATIBILITY:INVALID_SCHEMA') from exc


def load_v2_schema():
    schema=json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    _check_schema(schema)
    return schema


def schema_sha256():return hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()


def _transform(schema,visit):
    if isinstance(schema,bool):return schema
    result=deepcopy(schema)
    for key,value in list(result.items()):
        if key in {'properties','patternProperties','$defs','definitions','dependentSchemas'}:
            result[key]={name:_transform(child,visit) for name,child in value.items()}
        elif key in {'allOf','anyOf','oneOf','prefixItems'}:result[key]=[_transform(child,visit) for child in value]
        elif key in {'items','additionalProperties','contains','if','then','else','not','propertyNames','unevaluatedProperties','unevaluatedItems'} and isinstance(value,(dict,bool)):
            result[key]=_transform(value,visit)
    return visit(result)


def schema_keywords(schema):
    found=set()
    _transform(schema,lambda node:(found.update(node.keys()) or node))
    return sorted(found)


def _canonical_api(schema):
    def visit(node):
        for key in ('$schema','$id','title','description','$comment','examples','default'):node.pop(key,None)
        if 'const' in node:
            constant=node.pop('const')
            if 'enum' in node and constant not in node['enum']:raise ValueError('SCHEMA_COMPATIBILITY:CONTRADICTORY_CONST')
            node['enum']=[constant]
        return node
    return _transform(schema,visit)


def assert_schema_equivalent(original,derived):
    _check_schema(original);_check_schema(derived)
    if _canonical_api(original)!=_canonical_api(derived):raise ValueError('SCHEMA_COMPATIBILITY:BUSINESS_SEMANTICS_CHANGED')


def api_compatible_schema(schema=None,*,supported_keywords=None):
    schema=load_v2_schema() if schema is None else deepcopy(schema)
    _check_schema(schema);derived=_canonical_api(schema)
    _check_schema(derived);assert_schema_equivalent(schema,derived)
    if supported_keywords is not None:
        unknown=set(schema_keywords(derived))-set(supported_keywords)
        if unknown:raise ValueError('GATEWAY_UNSUPPORTED:SCHEMA_KEYWORDS:'+','.join(sorted(unknown)))
    return derived


def require_schema_capability(capability):
    if not isinstance(capability,dict) or capability.get('schema_enforced') is not True:
        raise ValueError('GATEWAY_UNSUPPORTED:JSON_SCHEMA_NOT_VERIFIED')


def responses_request(chat_body,*,schema=None):
    """Build a diagnostic/verified-provider request. Never send guessed strict."""
    content=[]
    for message in chat_body.get('messages',[]):
        parts=[]
        for part in message.get('content',[]):
            if part.get('type')=='text':parts.append(dict(type='input_text',text=part['text']))
            elif part.get('type')=='image_url':
                value=part['image_url'];parts.append(dict(type='input_image',image_url=value['url'],detail='original'))
        content.append(dict(role=message['role'],content=parts))
    return dict(model=chat_body['model'],reasoning=dict(effort='none'),max_output_tokens=chat_body['max_tokens'],
        text=dict(format=dict(type='json_schema',name=SCHEMA_NAME,schema=api_compatible_schema(schema))),input=content)


def responses_text(raw):
    if not isinstance(raw,dict) or raw.get('error') or raw.get('status')=='failed':raise ValueError('API_ERROR:RESPONSES')
    if raw.get('status')=='incomplete':
        reason=(raw.get('incomplete_details') or {}).get('reason')
        raise ValueError('MAX_OUTPUT_TOKENS' if reason=='max_output_tokens' else 'RESPONSE_INCOMPLETE')
    if raw.get('status')!='completed':raise ValueError('RESPONSE_INCOMPLETE')
    text=[]
    for item in raw.get('output',[]):
        if item.get('type')!='message':continue
        if item.get('status') not in {None,'completed'}:raise ValueError('RESPONSE_INCOMPLETE')
        for part in item.get('content',[]):
            if part.get('type')=='refusal':raise ValueError('API_ERROR:REFUSAL')
            if part.get('type')=='output_text':text.append(part.get('text') or '')
    output=''.join(text)
    if not output.strip():raise ValueError('EMPTY_OUTPUT')
    return output


def chat_text(raw):
    if not isinstance(raw,dict) or raw.get('error'):raise ValueError('API_ERROR:CHAT')
    if raw.get('object')=='response':return responses_text(raw)
    choices=raw.get('choices')
    if not isinstance(choices,list) or not choices:raise ValueError('EMPTY_OUTPUT')
    choice=choices[0]
    if choice.get('finish_reason')=='length':raise ValueError('MAX_OUTPUT_TOKENS')
    if choice.get('finish_reason') in {'content_filter','tool_calls'}:raise ValueError('RESPONSE_INCOMPLETE')
    message=choice.get('message') or {}
    if message.get('refusal'):raise ValueError('API_ERROR:REFUSAL')
    output=message.get('content')
    if not isinstance(output,str) or not output.strip():raise ValueError('EMPTY_OUTPUT')
    return output


def validate_v2_schema(row):
    schema=load_v2_schema();errors=sorted(Draft202012Validator(schema).iter_errors(row),key=lambda e:str(list(e.absolute_path)))
    if errors:
        details=['/'.join(str(p) for p in e.absolute_path)+':'+str(e.validator) for e in errors[:16]]
        raise ValueError('SCHEMA_VALIDATION_FAILED:'+';'.join(details))
    return row


def protected_removal_conflict(row):
    if not isinstance(row,dict) or row.get('decision')!='REMOVE_TEXT':return False
    from .image_action_decision import mark_disposition,mark_owner
    for mark in row.get('watermarks',[]) if isinstance(row.get('watermarks'),list) else []:
        if not isinstance(mark,dict) or not mark.get('kind'):continue
        if mark_disposition(mark)!='REMOVABLE':continue
        if mark_owner(mark) in {'MANUFACTURER','PRODUCT','PACKAGING','CREATOR'} or mark['kind'] in {'MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','MODEL_TEXT','CREATOR_CREDIT','NORMAL_PHOTO_TEXT'}:return True
    return False


def validate_v2_business(row,item):
    from .image_action_decision import validate
    from mye_c_automation.watermark_processing.contracts import check_polygon
    try:
        checked=validate(row,item)
        if protected_removal_conflict(checked):raise ValueError('PROTECTED_REMOVAL_CONFLICT')
        for region in checked['watermarks']+checked['preserve_regions']:check_polygon(region)
        return checked
    except (ValueError,KeyError,TypeError) as exc:raise ValueError('BUSINESS_VALIDATION_FAILED:'+str(exc)) from exc


def failure_code(exc):
    prefix=str(exc).split(':',1)[0]
    if prefix in CODES:return prefix
    if prefix=='SCHEMA_COMPATIBILITY':return 'SCHEMA_VALIDATION_FAILED'
    if isinstance(exc,json.JSONDecodeError):return 'INVALID_JSON'
    if isinstance(exc,(OSError,TimeoutError)):return 'API_ERROR'
    return 'BUSINESS_VALIDATION_FAILED'


def retry_allowed(code,row=None):
    return code in {'API_ERROR','EMPTY_OUTPUT','INVALID_JSON','SCHEMA_VALIDATION_FAILED'} and not protected_removal_conflict(row)
