"""Install a wheel in a disposable venv and deny all reads of the source checkout.

Interpreter audit hooks are inherited by every child Python process. This is a
dependency-isolation test, not an adversarial native-code security sandbox.
"""
import argparse,hashlib,json,os,shutil,subprocess,tempfile,venv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

GUARD='''import atexit,json,os,sys,time
from pathlib import Path
denied=[os.path.normcase(os.path.abspath(p)) for p in json.loads(os.environ['MYEC_DENY_PATHS'])]
attempts=[]
def guard(event,args):
    if event in {'open','os.listdir','os.scandir','os.chdir'} and args and isinstance(args[0],(str,bytes,os.PathLike)):
        path=os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        if any(path==root or path.startswith(root+os.sep) for root in denied):
            attempts.append(dict(event=event,path=path));raise PermissionError('SOURCE_CHECKOUT_INACCESSIBLE')
    if event in {'socket.connect','socket.getaddrinfo'}:
        attempts.append(dict(event=event,path='NETWORK'));raise PermissionError('NETWORK_FORBIDDEN')
sys.addaudithook(guard)
def finish():
    dest=Path(os.environ['MYEC_GUARD_LOGS']);dest.mkdir(parents=True,exist_ok=True)
    (dest/(str(os.getpid())+'-'+str(time.time_ns())+'.json')).write_text(json.dumps(attempts),encoding='utf-8')
atexit.register(finish)
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wheelhouse',type=Path,default=ROOT/'dist/wheelhouse');parser.add_argument('--output',type=Path,default=ROOT/'reports/isolation');parser.add_argument('--wheel',type=Path);args=parser.parse_args()
    work=Path(tempfile.mkdtemp(prefix='myec-independent-'))
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    venv.EnvBuilder(with_pip=True).create(work/'venv')
    python=work/'venv/Scripts/python.exe'
    wheel=args.wheel.resolve() if args.wheel else max((ROOT/'dist').glob('mye_c_automation-*.whl'),key=lambda p:p.stat().st_mtime_ns)
    wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest()
    install=[str(python),'-m','pip','install','--no-index','--find-links',str(args.wheelhouse.resolve()),str(wheel)+'[lama,legacy-ocr]']
    with (output/'install.log').open('w',encoding='utf-8') as log:
        subprocess.run(install,stdout=log,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(ROOT/'tests',work/'tests',ignore=shutil.ignore_patterns('__pycache__'))
    (work/'scripts').mkdir();shutil.copy2(ROOT/'scripts/run_tests.py',work/'scripts/run_tests.py')
    site=work/'venv/Lib/site-packages';(site/'sitecustomize.py').write_text(GUARD,encoding='utf-8')
    env=dict(os.environ,MYEC_DENY_PATHS=json.dumps([str(ROOT.parent/'aliexpress-product-image-audit'),str(ROOT)]),
        MYEC_GUARD_LOGS=str(work/'guard-logs'),MYEC_DATA_ROOT=str(work/'data'),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    env.pop('PYTHONPATH',None)
    checks=[]
    def run(name,argv):
        p=subprocess.run([str(python),'-B',*argv],cwd=work,env=env,text=True,encoding='utf-8',capture_output=True)
        (output/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        checks.append(dict(name=name,exit_code=p.returncode,command=argv))
        return p
    # Prove the guard is active, including in an independent child interpreter.
    denied=str(ROOT.parent/'aliexpress-product-image-audit'/'SKILL.md')
    probe="from pathlib import Path\ntry: Path("+repr(denied)+").read_bytes()\nexcept PermissionError: print('SOURCE_DENIED')\nelse: raise AssertionError('source accessible')"
    probe_result=run('guard-self-test',['-c',probe])
    if probe_result.returncode or 'SOURCE_DENIED' not in probe_result.stdout:raise RuntimeError('Isolation guard failed')
    run('help',['-m','mye_c_automation','--help'])
    run('doctor',['-m','mye_c_automation','doctor'])
    run('configure-init',['-m','mye_c_automation','configure','init','--directory',str(work/'local')])
    # Missing credentials are expected. Keep the expected exit separate from
    # actual command failure so a skipped setup cannot pass as a live check.
    p=run('configure-check',['-m','mye_c_automation','configure','check','--directory',str(work/'local')])
    checks[-1]['expected_exit_code']=2
    checks[-1]['configuration_not_ready']=not json.loads(p.stdout)['ready_for_readonly'] if p.stdout.strip() else False
    run('deployment-review',['-m','mye_c_automation','deploy','review','--install-root',str(work/'install'),'--output',str(work/'deployment')])
    for scenario in ('twin','frame','repair','keep'):
        run('fake-'+scenario,['-m','mye_c_automation','fake','--scenario',scenario,'--data-root',str(work/'data'/scenario)])
    run('regression',[str(work/'scripts/run_tests.py'),'--output',str(work/'reports/regression')])
    if (work/'reports/regression').exists():shutil.copytree(work/'reports/regression',output/'regression',dirs_exist_ok=True,ignore=shutil.ignore_patterns('data'))
    attempts=[]
    for p in (work/'guard-logs').glob('*.json'):attempts.extend(json.loads(p.read_text()))
    expected=[a for a in attempts if a['event']=='open' and a['path']==os.path.normcase(denied)]
    unexpected=[a for a in attempts if a not in expected]
    manifest={p.relative_to(work/'data').as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (work/'data').rglob('*') if p.is_file()}
    report=dict(isolation_root=str(work),wheel_sha256=wheel_sha256,wheel_unchanged=hashlib.sha256(wheel.read_bytes()).hexdigest()==wheel_sha256,checks=checks,expected_guard_probes=len(expected),unexpected_forbidden_access=unexpected,
        data_files=manifest,method='Independent wheel venv; original Skill and new source checkout denied by inherited interpreter audit hooks',native_os_container=False,
        passed=all(c['exit_code']==c.get('expected_exit_code',0) and c.get('configuration_not_ready',True) for c in checks) and not unexpected and hashlib.sha256(wheel.read_bytes()).hexdigest()==wheel_sha256)
    (output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'data_files','checks'}},ensure_ascii=False))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
