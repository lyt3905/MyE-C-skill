"""Local configuration bootstrap and offline checks using existing V2 validators."""
import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from mye_c_automation.paths import config_root
from mye_c_automation.resources import resource_path,validate_resource_json
from mye_c_automation.model_resources import file_sha256

FILES=('site.local.json','model.local.json','automation.local.json','image-options.local.json','download.local.json')

def model_api_key(directory):
    """Read only the independent program's key; callers must never serialize it."""
    value=os.environ.get('VLM_API_KEY')
    if value:return value
    try:
        value=json.loads((Path(directory)/'model-key.local.json').read_text(encoding='utf-8-sig')).get('VLM_API_KEY')
        return value if isinstance(value,str) and value.strip() else None
    except (OSError,ValueError,TypeError,AttributeError):return None

def initialize_config(directory=None):
    directory=config_root(directory);directory.mkdir(parents=True,exist_ok=True)
    examples={FILES[0]:dict(base='',user='',pwd='')}
    for filename,resource in zip(FILES[1:],('model.gateway8788.example.json','automation.v2.example.json','image-options.v2.example.json')):
        examples[filename]=json.loads(resource_path('config/'+resource).read_text(encoding='utf-8'))
    from mye_c_automation.download_manager import DEFAULT_DOWNLOAD_OPTIONS
    examples['download.local.json']=dict(DEFAULT_DOWNLOAD_OPTIONS)
    created=[];preserved=[]
    for filename,value in examples.items():
        try:
            with (directory/filename).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
            created.append(filename)
        except FileExistsError:preserved.append(filename)
    return dict(status='INITIALIZED',directory=str(directory),created=created,preserved=preserved,network_calls=0,live_verification='NOT_RUN')

def load_image_options(path):
    path=Path(path).expanduser().resolve()
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(value,dict):value={'rights':'RIGHTS_UNKNOWN','max_mask_area':.25,**value}
    validate_resource_json(value,'image-options.v2.schema.json')
    if value.get('lama_model_path'):
        source=Path(value['lama_model_path']).expanduser()
        value['lama_model_path']=str((source if source.is_absolute() else path.parent/source).resolve())
    if value.get('image_edit') and isinstance(value['image_edit'],dict) and value['image_edit'].get('adapter_path'):
        source=Path(value['image_edit']['adapter_path']).expanduser()
        value['image_edit']['adapter_path']=str((source if source.is_absolute() else path.parent/source).resolve())
    return value

def bind_lama(directory,model_path,expected_sha256):
    directory=config_root(directory);model_path=Path(model_path).resolve()
    if not model_path.is_file() or file_sha256(model_path)!=expected_sha256:raise ValueError('LAMA_CHECKSUM_MISMATCH')
    path=directory/'image-options.local.json';options=load_image_options(path)
    if options.get('lama_model_path') and (options['lama_model_path']!=str(model_path) or options.get('lama_model_sha256')!=expected_sha256):
        raise ValueError('LAMA_ALREADY_CONFIGURED')
    options.update(lama_model_path=str(model_path),lama_model_sha256=expected_sha256)
    from mye_c_automation.job_manager import atomic_json
    atomic_json(path,options)
    return dict(status='BOUND',image_options=str(path),model_path=str(model_path),sha256=expected_sha256,rights=options['rights'],inference='NOT_RUN')

def check_configuration(directory=None,*,shop=None,pid=None):
    from mye_c_automation.automation_policy import AutomationPolicy
    from mye_c_automation.model_config import load_config,review_models
    directory=config_root(directory);blockers=[];warnings=[];checks={}
    def failure(code):
        if code not in blockers:blockers.append(code)
    try:
        value=json.loads((directory/FILES[0]).read_text(encoding='utf-8-sig'))
        valid=isinstance(value,dict) and all(isinstance(value.get(k),str) and value[k].strip() for k in ('base','user','pwd'))
        if valid:
            parsed=urlsplit(value['base']);valid=parsed.scheme=='https' and bool(parsed.hostname) and not any((parsed.username,parsed.password,parsed.query,parsed.fragment))
        if not valid:raise ValueError('site configuration')
        checks['site']='CONFIGURED_NOT_CONNECTED'
    except (OSError,ValueError,TypeError):failure('SITE_CONFIG_INCOMPLETE');checks['site']='INCOMPLETE'
    try:
        profile=load_config(directory/FILES[1]);models=review_models(profile['models'])
        checks['model']=dict(status='CONFIGURED_NOT_CONNECTED',models=list(models))
    except (OSError,ValueError,TypeError):failure('MODEL_CONFIG_INVALID');checks['model']='INVALID'
    key=bool(model_api_key(directory));checks['model_api_key_present']=key
    if not key:failure('MODEL_API_KEY_MISSING')
    try:
        from mye_c_automation.download_manager import load_download_options
        checks['downloads']=load_download_options(directory)
    except (OSError,ValueError,TypeError):failure('DOWNLOAD_CONFIG_INVALID')
    policy=None
    try:
        policy=AutomationPolicy.load(directory/FILES[2])
        checks['automation']=dict(enabled=policy.config['enabled'],replace_twin=policy.permits('REPLACE_TWIN'))
        if not policy.permits('REPLACE_TWIN'):warnings.append('REPLACE_TWIN_DISABLED')
    except (OSError,ValueError,TypeError):failure('AUTOMATION_CONFIG_INVALID')
    try:
        options=load_image_options(directory/FILES[3]);checks['rights']=options['rights']
        if options['rights']!='OWNED_OR_LICENSED':warnings.append('LOCAL_REPAIR_RIGHTS_NOT_CONFIRMED')
        if options.get('lama_model_path'):
            model=Path(options['lama_model_path']);expected=options.get('lama_model_sha256')
            if not model.is_file():failure('LAMA_MODEL_MISSING')
            elif not expected:failure('LAMA_CHECKSUM_MISSING')
            elif file_sha256(model)!=expected:failure('LAMA_CHECKSUM_MISMATCH')
            else:checks['lama']='BYTES_VERIFIED_INFERENCE_NOT_RUN'
            if importlib.util.find_spec('torch') is None:warnings.append('LAMA_TORCH_DEPENDENCY_MISSING')
        else:checks['lama']='NOT_CONFIGURED';warnings.append('LAMA_NOT_CONFIGURED')
        if options.get('image_edit'):
            from mye_c_automation.image_repairs_v2 import freeze_image_edit_config
            freeze_image_edit_config(options['image_edit']);checks['image_edit']='ADAPTER_PINNED_SERVICE_NOT_TESTED'
        else:checks['image_edit']='NOT_CONFIGURED'
    except (OSError,ValueError,TypeError):failure('IMAGE_OPTIONS_INVALID')
    # Validate the packaged legacy template without using it for V2 semantics.
    try:
        import numpy as np
        spec=json.loads(resource_path('config/template.red-store.screening.example.json').read_text())['templates'][0]
        template=(resource_path('config')/spec['path']).resolve()
        meta=json.loads(template.with_suffix('.json').read_text(encoding='utf-8'))
        if file_sha256(template)!=meta['sha256']:raise ValueError('template checksum')
        np.load(template,allow_pickle=False)
        checks['legacy_template']='PACKAGED_BYTES_VERIFIED_V2_SEMANTICS_UNUSED'
    except (OSError,ValueError,KeyError,TypeError):failure('PACKAGED_TEMPLATE_INVALID')
    if (shop is None)!=(pid is None) or any(type(v) is not int or v<=0 for v in (shop,pid) if v is not None):failure('SHOP_PID_REQUIRED_TOGETHER')
    command=None
    if shop is not None and pid is not None and 'SHOP_PID_REQUIRED_TOGETHER' not in blockers:
        command=[sys.executable,'-m','mye_c_automation','workflow','--','full-audit','--shop',str(shop),'--pid',str(pid),
            '--site-config',str(directory/FILES[0]),'--model-config',str(directory/FILES[1]),'--image-options',str(directory/FILES[3])]
    return dict(status='CONFIG_READY' if not blockers else 'NEEDS_CONFIGURATION',directory=str(directory),ready_for_readonly=not blockers,
        ready_for_write=False,configuration_only=True,checks=checks,blockers=blockers,warnings=warnings,network_calls=0,
        live_verification='NOT_RUN',suggested_readonly_command=command)
