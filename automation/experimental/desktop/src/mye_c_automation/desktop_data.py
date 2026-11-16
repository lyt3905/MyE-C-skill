"""Presentation helpers for local files and existing CLI commands; no new workflow."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from mye_c_automation.model_resources import file_sha256
from mye_c_automation.model_config import validate_config
from mye_c_automation.job_manager import atomic_json

def cli_python():
    path=Path(sys.executable)
    return str(path.with_name('python.exe')) if path.name.lower()=='pythonw.exe' else sys.executable

def fake_command(scenario,data_directory):
    if scenario not in {'twin','frame','repair','keep'}:raise ValueError('UNKNOWN_FAKE_SCENARIO')
    return [cli_python(),'-u','-m','mye_c_automation','fake','--scenario',scenario,'--data-root',str(Path(data_directory).resolve())]

def worker_environment(api_key=''):
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    if api_key:env['VLM_API_KEY']=api_key
    return env

def load_connection_form(directory):
    root=Path(directory).resolve();site=root/'site.local.json';model=root/'model.local.json'
    a=json.loads(site.read_text(encoding='utf-8-sig'));b=json.loads(model.read_text(encoding='utf-8-sig'))
    return dict(base=a.get('base',''),user=a.get('user',''),pwd=a.get('pwd',''),gateway=b.get('base_url',''),
        revisions={p.name:file_sha256(p) for p in (site,model)})

def save_connection_form(directory,values,revisions):
    root=Path(directory).resolve();site=root/'site.local.json';model=root/'model.local.json'
    for p in (site,model):
        if revisions.get(p.name)!=file_sha256(p):raise ValueError('CONFIG_CHANGED: 请重新加载配置')
    base=values['base'].strip();parsed=urlsplit(base)
    if base and (parsed.scheme!='https' or not parsed.hostname or any((parsed.username,parsed.password,parsed.query,parsed.fragment))):raise ValueError('后台地址必须是 HTTPS 地址')
    original_site=json.loads(site.read_text(encoding='utf-8-sig'));original_model=json.loads(model.read_text(encoding='utf-8-sig'))
    original_site.update({k:values[k] for k in ('base','user','pwd')})
    original_model['base_url']=values['gateway'].strip();original_model=validate_config(original_model)
    # Validate both files and both revision bindings before changing either.
    for p in (site,model):
        if revisions.get(p.name)!=file_sha256(p):raise ValueError('CONFIG_CHANGED: 请重新加载配置')
    atomic_json(site,original_site);atomic_json(model,original_model)
    return dict(status='SAVED_LOCAL',revisions={p.name:file_sha256(p) for p in (site,model)},network_calls=0)

def _read(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).is_file() else default

def _job_path(data_directory,job_id):
    if not isinstance(job_id,str) or not re.fullmatch(r'JOB_[A-Za-z0-9]+',job_id):raise ValueError('INVALID_JOB_ID')
    root=(Path(data_directory)/'jobs').resolve();path=(root/job_id).resolve()
    if not path.is_relative_to(root):raise ValueError('JOB_OUTSIDE_DATA_ROOT')
    return path

def status_label(status):
    return {'AUTO_VERIFIED':'验证通过','PARTIALLY_AUTO_FIXED':'部分完成，仍有待复核项','APPLY_UNKNOWN':'保存结果未知，须先回读',
        'DEFERRED':'暂缓处理','CONTENT_REVIEW_REQUIRED':'内容需要复核','REVIEW_REQUIRED':'需要复核','CREATED':'已创建',
        'PREFLIGHT':'准备检查','AUDITED':'已采集','AI_PENDING':'审核中','AI_RESOLVED':'审核结束','PLAN_READY':'计划已生成',
        'DRY_RUN_PASSED':'预演通过','FAILED':'失败','EVIDENCE_ERROR':'任务证据无法读取'}.get(status,status or '状态未知')

def list_jobs(data_directory):
    root=Path(data_directory)/'jobs';rows=[]
    if not root.is_dir():return rows
    for folder in sorted(root.glob('JOB_*'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not folder.is_dir():continue
        try:
            job=load_job(data_directory,folder.name)
            rows.append(dict(job_id=folder.name,pid=job['job'].get('pid'),shop=job['job'].get('shop_id'),state=job['state'].get('state'),path=str(folder)))
        except (OSError,ValueError,TypeError):rows.append(dict(job_id=folder.name,pid=None,shop=None,state='EVIDENCE_ERROR',path=str(folder)))
    return rows

def load_job(data_directory,job_id):
    root=_job_path(data_directory,job_id)
    job=_read(root/'job.json')
    if not isinstance(job,dict) or job.get('job_id')!=job_id:raise ValueError('JOB_BINDING_INVALID')
    return dict(path=str(root),job=job,state=_read(root/'state.json',{}),result=_read(root/'automatic_result.json'),
        summary=_read(root/'fake_summary.json'),report=_read(root/'report_data.json'))

def image_pairs(job_directory):
    root=Path(job_directory).resolve();inventory=_read(root/'full_inventory.json',{}).get('contents',{})
    decisions=_read(root/'auto_decisions.json',{}).get('items',[]);pairs=[];seen=set()
    def bound_file(filename,digest):
        if not filename:return None
        path=Path(filename);path=(path if path.is_absolute() else root/path).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('IMAGE_OUTSIDE_JOB_OR_MISSING')
        if file_sha256(path)!=digest:raise ValueError('IMAGE_BYTES_CHANGED')
        return str(path)
    for row in decisions:
        source=row.get('source') or {};a=source.get('original_sha256');b=source.get('sha256');action=row.get('action')
        if not a or (a,b,action) in seen:continue
        seen.add((a,b,action));before=bound_file(inventory.get(a,{}).get('file'),a)
        asset=row.get('candidate_asset') or {}
        after=bound_file(asset.get('path'),asset.get('sha256')) if asset else bound_file(inventory.get(b,{}).get('file'),b) if action=='REPLACE_TWIN' else None
        pairs.append(dict(action=action,decision=row.get('decision'),before=before,after=after,source_sha256=a,candidate_sha256=b))
    return pairs
