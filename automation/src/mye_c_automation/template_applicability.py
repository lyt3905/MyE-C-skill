"""Explicit template applicability; missing required configuration never means clean."""
import hashlib,json
from pathlib import Path

def resolve(directory,shop,required=False,templates=None):
    root=Path(directory);config=root/'template_config.json'
    if not config.exists():config=Path(__file__).parent/'config'/'template_config.json'
    data=json.loads(config.read_text(encoding='utf-8-sig')) if templates is None and config.exists() else {'templates':templates or []}
    required_shops=data.get('required_shop_ids',[]);none_shops=data.get('no_applicable_shop_ids',[])
    if not isinstance(required_shops,list) or not isinstance(none_shops,list) or any(type(v) is not int or v<=0 for v in required_shops+none_shops) or set(required_shops)&set(none_shops):raise ValueError('TEMPLATE_CONFIG_CONFLICT')
    specs=data.get('templates',[])
    if not isinstance(specs,list):raise ValueError('INVALID_TEMPLATE_CONFIG')
    normalized=[]
    for row in specs:
        if not isinstance(row,dict) or type(row.get('shop_id')) is not int or row['shop_id']<=0 or not isinstance(row.get('path'),str) or not row['path'].strip():raise ValueError('INVALID_TEMPLATE_SPEC')
        if row.get('projection','gray') not in ('gray','red_excess'):raise ValueError('INVALID_TEMPLATE_PROJECTION')
        path=Path(row['path'])
        if not path.is_absolute():path=(config.parent if templates is None and config.exists() else root)/path
        normalized.append(dict(row,path=str(path.resolve())))
    applicable=[r for r in normalized if r.get('shop_id')==shop]
    status='COMPLETE' if applicable else 'NO_APPLICABLE_TEMPLATE' if shop in none_shops or not required and shop not in required_shops else 'REQUIRED_TEMPLATE_MISSING'
    source={'source':str(config.resolve()),'sha256':hashlib.sha256(config.read_bytes()).hexdigest(),'kind':'template_config'} if templates is None and config.exists() else None
    return {'status':status,'templates':normalized,'configuration':dict(data,templates=normalized),'source':source}

def snapshot(source,directory):
    from mye_c_automation.job_manager import atomic_json
    source=Path(source).resolve();data=json.loads(source.read_text(encoding='utf-8-sig'))
    for row in data.get('templates',[]):
        path=Path(row['path'])
        if not path.is_absolute():row['path']=str((source.parent/path).resolve())
    atomic_json(Path(directory)/'template_config.json',data)
