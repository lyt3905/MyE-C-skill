"""Build a review-only, secret-free source synchronization bundle."""
import hashlib,json,zipfile,argparse
from pathlib import Path

def bundle(source,output):
 source=Path(source).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 files=[]
 for directory in ('scripts','tests','reports','templates','references'):
  for path in sorted((source/directory).rglob('*')):
   if path.is_file() and not any(part in {'__pycache__','.cache','work','local'} for part in path.relative_to(source).parts) and path.suffix.lower() in {'.py','.json','.md','.jsonl','.ps1','.png','.jpg','.jpeg','.txt','.log'}:
    files.append(path)
 for name in ('README.md','SKILL.md','requirements-auto.txt','requirements-dev.txt'):
  if (source/name).is_file():files.append(source/name)
 manifest=[{'path':p.relative_to(source).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in files]
 target=output/'workflow-sync-review.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
  for p in files:archive.write(p,p.relative_to(source).as_posix())
  archive.writestr('SYNC-MANIFEST.json',json.dumps(manifest,indent=2))
 with zipfile.ZipFile(target) as archive:
  for row in manifest:
   if hashlib.sha256(archive.read(row['path'])).hexdigest()!=row['sha256']:raise ValueError('bundle inconsistency')
 (output/'sync-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 return manifest
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
 print(len(bundle(Path(__file__).resolve().parents[1],args.output)))
