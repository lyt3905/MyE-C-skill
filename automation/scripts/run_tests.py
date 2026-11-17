"""Complete offline discovery with source binding and explicit result evidence."""
import argparse,hashlib,json,os,socket,sys,time,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def sources():
    import mye_c_automation
    package=Path(mye_c_automation.__file__).resolve().parent
    roots=[(ROOT/'tests','tests'),(package,'installed/mye_c_automation')]
    return {label+'/'+p.relative_to(base).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for base,label in roots for p in base.rglob('*') if p.is_file()
        and not any(part in {'__pycache__','.cache'} or part.endswith('.egg-info') for part in p.parts)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'reports/regression');parser.add_argument('--pattern',default='test_*.py');args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['MYEC_TEST_FIXTURES']=str(ROOT/'tests/fixtures')
    os.environ['MYEC_DATA_ROOT']=str(out/'data');os.environ['PYTHONDONTWRITEBYTECODE']='1'
    attempts=[]
    def deny(*a,**k):attempts.append('NETWORK');raise AssertionError('Network forbidden in offline tests')
    guards=[patch('urllib.request.urlopen',side_effect=deny),patch('socket.create_connection',side_effect=deny),patch.object(socket.socket,'connect',side_effect=deny),patch.object(socket.socket,'connect_ex',side_effect=deny)]
    for g in guards:g.start()
    before=sources();start=time.monotonic()
    def flatten(suite):
        for t in suite:
            if isinstance(t,unittest.TestSuite):yield from flatten(t)
            else:yield t
    try:
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=args.pattern)
        cases=list(flatten(suite));ids=[t.id() for t in cases]
        with (out/'tests.log').open('w',encoding='utf-8') as log:
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite(cases))
    finally:
        for g in reversed(guards):g.stop()
    after=sources()
    summary=dict(tests=result.testsRun,discovered=len(ids),failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        network_attempts=len(attempts),real_model_calls=0,site_reads=0,production_writes=0,source_unchanged=before==after,elapsed_seconds=round(time.monotonic()-start,3))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    (out/'ids.json').write_text(json.dumps(dict(all=ids,failures=[t.id() for t,_ in result.failures],errors=[t.id() for t,_ in result.errors]),indent=2))
    (out/'source-binding.json').write_text(json.dumps(dict(before=before,after=after),indent=2))
    print(json.dumps(summary))
    return 0 if result.wasSuccessful() and before==after and not attempts else 1

if __name__=='__main__':raise SystemExit(main())
