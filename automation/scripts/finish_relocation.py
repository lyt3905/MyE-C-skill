"""Development-only relocation corrections; no changes to V2 business decisions."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'src/mye_c_automation'
modules=json.loads((ROOT/'reports/dependency-audit.json').read_text())['modules']
for p in list(PKG.rglob('*.py'))+list((ROOT/'tests').glob('*.py')):
    s=p.read_text(encoding='utf-8')
    for name in modules:
        for q in ("'",'"'):
            # Plain dictionary keys / path segments are not import targets.
            s=s.replace(q+'mye_c_automation.'+name+q,q+name+q)
    if p.parent==ROOT/'tests':
        if "'scripts/config/" in s:
            s="from mye_c_automation.resources import resource_path\n"+s
            s=s.replace("load_config('scripts/config/model.gateway' + name + '.example.json')", "load_config(resource_path('config/model.gateway' + name + '.example.json'))")
            s=s.replace("Path('scripts/config/automation.v1.example.json')", "resource_path('config/automation.v1.example.json')")
            s=s.replace("Path('scripts/config/model.gateway8788.example.json')", "resource_path('config/model.gateway8788.example.json')")
    p.write_text(s,encoding='utf-8')

def edit(name,old,new):
    p=PKG/name;s=p.read_text(encoding='utf-8')
    if old not in s:raise ValueError((name,old))
    p.write_text(s.replace(old,new),encoding='utf-8')

data="__import__('mye_c_automation.paths',fromlist=['data_root']).data_root()"
edit('check.py','os.environ.get("AE_ROOT") or os.getcwd()',f'str({data})')
edit('audit_one.py','else ROOT / "work"',f'else {data} / "snapshots"')
edit('audit_one.py',"Path(__file__).parent/'work'/'v2'",f"{data}/'jobs'")
edit('apply_token_plan.py','ROOT / "work"',f'{data} / "snapshots"')
for name in ('imgpool.py','vlmcheck.py'):
    edit(name,'ROOT = os.path.dirname(os.path.abspath(__file__))',f'ROOT = str({data})')
edit('render_token_report.py','Path(__file__).resolve().parent / "work"',f'{data} / "jobs"')
for name in ('observed_audit.py','complete_observed_audit.py'):
    edit(name,"rv.ROOT/'work/8788-observed-audit-20261114'",f"{data}/'archived-preflight'")
edit('run_8788_real_validation.py',"ROOT/'work/8788-real-validation-20261114'",f"{data}/'archived-preflight'")
# In a wheel installation, git metadata is optional. Do not require a checkout.
p=PKG/'run_8788_real_validation.py';s=p.read_text(encoding='utf-8')
start=s.index('def git_info():');end=s.index('\n\ndef request_body',start)
s=s[:start]+'''def git_info():
    return dict(root=str(ROOT), branch='INSTALLED_PACKAGE', head='68e168f1a08c6338cb0964dffbd021bb5e484556', status='OFFLINE_ARCHIVED_CONTRACT')
'''+s[end:];p.write_text(s,encoding='utf-8')
