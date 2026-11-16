"""Record a fresh follow-up baseline without overwriting extraction evidence."""
import hashlib,json,subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=root/'reports/readiness-20261116'
out.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={p.relative_to(root).as_posix():sha(p) for folder in ('src','tests','scripts','docs','models') for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.pt'} }
manifest.update({n:sha(root/n) for n in ('README.md','pyproject.toml','.gitignore')})
target=out/'before.json'
with target.open('x',encoding='utf-8') as f:json.dump(manifest,f,indent=2)
git={c:subprocess.check_output(['git',*c.split()],cwd=root).decode('utf-8',errors='replace') for c in ('rev-parse HEAD','status --short --branch','diff','diff --cached')}
with (out/'git-before.json').open('x',encoding='utf-8') as f:json.dump(git,f,ensure_ascii=False,indent=2)
print(json.dumps({'files':len(manifest),'evidence':str(out)}))
