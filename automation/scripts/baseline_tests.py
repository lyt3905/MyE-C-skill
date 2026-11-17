"""Run unchanged baseline discovery in a temporary source mirror (source stays read-only)."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'aliexpress-product-image-audit'

def main():
    temp=Path(tempfile.mkdtemp(prefix='myec-baseline-'))
    for folder in ('scripts','tests','prompts'):
        shutil.copytree(SOURCE/folder,temp/folder,ignore=shutil.ignore_patterns('__pycache__','.cache','work'))
    (temp/'work').mkdir()
    (temp/'references').mkdir()
    shutil.copy2(SOURCE/'references/SOP-商品标题重写.md',temp/'references/SOP-商品标题重写.md')
    # Relocation only: archived fixture readers use original sealed evidence read-only.
    p=temp/'scripts/run_8788_real_validation.py'
    p.write_text(p.read_text(encoding='utf-8-sig').replace('ROOT = Path(__file__).resolve().parents[1]',f'ROOT = Path({str(SOURCE)!r})'),encoding='utf-8')
    harness=(SOURCE/'work/v2-visual-versions-20261116/run_offline_tests.py').read_text(encoding='utf-8')
    harness=harness.replace("'__pycache__' not in p.parts", "not any(part in {'__pycache__','.cache','work'} for part in p.parts)")
    (temp/'run.py').write_text(harness,encoding='utf-8')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    python=ROOT.parent/'ae-img-audit/.venv/Scripts/python.exe'
    with (ROOT/'reports/baseline-tests.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(python),'-B',str(temp/'run.py')],cwd=temp,env=env,stdout=log,stderr=subprocess.STDOUT)
    for name in ('tests-status.json','test-ids.json','test-source-manifest.json'):
        if (temp/name).exists():shutil.copy2(temp/name,ROOT/'reports'/('baseline-'+name))
    (ROOT/'reports/baseline-test-report.md').write_text(f'# Baseline regression\n\nBaseline: 68e168f. Full original discovery, no filters.\n\nCommand: `{python} -B <temporary-mirror>/run.py`\n\nMirror: {temp}\n\nOnly archived fixture ROOT relocated to original read-only source. Network denied; bytecode disabled; default ledgers redirected by baseline harness. Source mirror bindings and test IDs retained in baseline JSON evidence.\n\nExit code: {result.returncode}. Details: `baseline-tests.log`, `baseline-tests-status.json`. Historical 931 result is not reused as a new result.\n',encoding='utf-8')
    print(json.dumps({'exit_code':result.returncode,'mirror':str(temp)}))
    return result.returncode

if __name__=='__main__':raise SystemExit(main())
