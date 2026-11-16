"""One-time development extraction. Explicit allowlist from dependency-audit.json."""
import ast, hashlib, io, json, re, shutil, tokenize
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'aliexpress-product-image-audit'
PKG=ROOT/'src/mye_c_automation'
MODULES=set(json.loads((ROOT/'reports/dependency-audit.json').read_text())['modules'])
PROVENANCE=[]

def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')

def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    PROVENANCE.append(dict(source=source.relative_to(SOURCE).as_posix(),target=target.relative_to(ROOT).as_posix(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))

def namespace(text):
    # Rewrite statements at their exact AST source spans, preserving surrounding code.
    lines=text.splitlines(keepends=True);offset=[0]
    for line in lines:offset.append(offset[-1]+len(line))
    edits=[]
    for node in ast.walk(ast.parse(text)):
        replacement=None
        if isinstance(node,ast.ImportFrom) and node.level==0 and node.module and node.module.split('.')[0] in MODULES:
            replacement='from mye_c_automation.'+node.module+' import '+', '.join(a.name+(' as '+a.asname if a.asname else '') for a in node.names)
        elif isinstance(node,ast.Import) and any(a.name.split('.')[0] in MODULES for a in node.names):
            statements=[]
            for a in node.names:
                head=a.name.split('.')[0]
                if head not in MODULES:statements.append('import '+a.name+(' as '+a.asname if a.asname else ''))
                elif a.asname:statements.append('import mye_c_automation.'+a.name+' as '+a.asname)
                elif '.' not in a.name:statements.append('from mye_c_automation import '+a.name)
                else:statements.extend(['from mye_c_automation import '+head,'import mye_c_automation.'+a.name])
            replacement='; '.join(statements)
        if replacement is not None:
            # AST columns are UTF-8 byte positions.
            start=offset[node.lineno-1]+len(lines[node.lineno-1].encode()[:node.col_offset].decode())
            end=offset[node.end_lineno-1]+len(lines[node.end_lineno-1].encode()[:node.end_col_offset].decode())
            edits.append((start,end,replacement))
    for start,end,value in sorted(edits,reverse=True):text=text[:start]+value+text[end:]
    tokens=[]
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type==tokenize.STRING:
            try:value=ast.literal_eval(token.string)
            except (ValueError,SyntaxError):value=None
            if isinstance(value,str):
                new=value
                if value.split('.')[0] in MODULES and re.fullmatch(r'[a-zA-Z_][\w.]*',value):new='mye_c_automation.'+value
                # Subprocess snippets and IPC module argument (not executable source paths).
                if 'from upload_rate import' in new:new=new.replace('from upload_rate import','from mye_c_automation.upload_rate import')
                if new!=value:token=token._replace(string=repr(new))
        tokens.append(token)
    text=tokenize.untokenize(tokens)
    # Remove legacy path injection; installed package imports replace it.
    text=re.sub(r'^sys\.path\.insert\([^\n]*\)\s*\n','',text,flags=re.M)
    text=text.replace("Path(__file__).resolve().parents[2]/'prompts/", "Path(__file__).resolve().parents[1]/'prompts/")
    text=text.replace("Path(__file__).resolve().parents[1]/'prompts/", "Path(__file__).resolve().parent/'prompts/") if "constraints=(Path" in text else text
    return text

def main():
    PKG.mkdir(parents=True,exist_ok=True)
    for name in sorted(MODULES):
        src=SOURCE/'scripts'/name
        files=list(src.rglob('*.py')) if src.is_dir() else [src.with_suffix('.py')]
        for source in files:
            if '__pycache__' in source.parts:continue
            target=PKG/source.relative_to(SOURCE/'scripts')
            copy(source,target);write(target,namespace(source.read_text(encoding='utf-8-sig')))
    for folder,target in [('scripts/config',PKG/'config'),('prompts',PKG/'prompts')]:
        for source in (SOURCE/folder).rglob('*'):
            if source.is_file() and source.suffix in {'.json','.md'}:copy(source,target/source.relative_to(SOURCE/folder))
    for source in (SOURCE/'tests').rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts:
            target=ROOT/'tests'/source.relative_to(SOURCE/'tests');copy(source,target)
            if source.suffix=='.py':
                text=namespace(source.read_text(encoding='utf-8-sig'))
                text=text.replace("Path(__file__).resolve().parents[1]/'scripts/config/", "__import__('mye_c_automation.resources',fromlist=['resource_path']).resource_path('config')/'")
                text=text.replace("Path(__file__).resolve().parents[1]/'scripts'/'config'", "__import__('mye_c_automation.resources',fromlist=['resource_path']).resource_path('config')")
                text=text.replace("Path(__file__).resolve().parents[1] / 'scripts/config/automation.v1.example.json'", "__import__('mye_c_automation.resources',fromlist=['resource_path']).resource_path('config/automation.v1.example.json')")
                write(target,text)
    # Runtime previously parsed a Skill SOP. Materialize the already parsed table,
    # so no SOP, Skill instruction or reference document is needed by the software.
    text=(SOURCE/'references/SOP-商品标题重写.md').read_text(encoding='utf-8')
    section=text.split('## 3. 替换表（合并版）',1)[1].split('## 4.',1)[0]
    write(PKG/'config/title-mappings.md','## 3. 替换表（合并版）\n'+section+'\n## 4.\n')
    p=PKG/'title_rules.py';s=p.read_text(encoding='utf-8');s=s.replace("Path(__file__).resolve().parents[1]/'references'/'SOP-商品标题重写.md'","Path(__file__).resolve().parent/'config/title-mappings.md'");write(p,s)
    # Independent writable defaults, outside site-packages.
    p=PKG/'account_coordination.py';s=p.read_text();s=s.replace("DEFAULT_DIRECTORY=Path(__file__).resolve().parents[1]/'local'/'execution_locks'","from mye_c_automation.paths import data_root\nDEFAULT_DIRECTORY=data_root()/'ledger'/'execution_locks'");write(p,s)
    p=PKG/'upload_rate.py';s=p.read_text();s=s.replace("Path(__file__).resolve().parents[1]/'local'/'global_upload_rate.sqlite'","__import__('mye_c_automation.paths',fromlist=['data_root']).data_root()/'ledger'/'global_upload_rate.sqlite'");write(p,s)
    # Explicit fixture extraction: only inventory, protocol, queue and referenced image
    # bytes. No old responses, budget DB, credentials, authorization or product snapshot.
    old=SOURCE/'work/full-product-audit-20261114/jobs/JOB_93099438cf014a689846bc05469759ad'
    fixture=ROOT/'tests/fixtures/archived-inputs';fixture.mkdir(parents=True,exist_ok=True)
    needed=set()
    metadata={name:json.loads((old/name).read_text(encoding='utf-8')) for name in ('full_inventory.json','full_ai_queue.json','full_audit_protocol.json')}
    def paths(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in {'file','path','local'} and isinstance(v,str):
                    p=Path(v)
                    if not p.is_absolute():p=SOURCE/p
                    if p.is_file() and p.is_relative_to(old):needed.add(p)
                paths(v)
        elif isinstance(value,list):
            for v in value:paths(v)
    for value in metadata.values():paths(value)
    for source in needed:copy(source,fixture/source.relative_to(old))
    def relocate(value):
        if isinstance(value,str):
            if value.startswith(str(old)):return '@FIXTURE@/'+Path(value).relative_to(old).as_posix()
            possible=SOURCE/value
            if possible.is_file() and possible.is_relative_to(old):return '@FIXTURE@/'+possible.relative_to(old).as_posix()
            return value
        if isinstance(value,list):return [relocate(v) for v in value]
        if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
        return value
    for name,value in metadata.items():write(fixture/name,json.dumps(relocate(value),ensure_ascii=False,indent=2))
    seal={p.relative_to(fixture).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}
    write(ROOT/'tests/fixtures/archived-inputs-seal.json',json.dumps({'files':seal},indent=2))
    p=PKG/'run_8788_real_validation.py';s=p.read_text(encoding='utf-8')
    s=s.replace("ROOT = Path(__file__).resolve().parents[1]", "ROOT = Path(__file__).resolve().parent\nFIXTURES=Path(os.environ.get('MYEC_TEST_FIXTURES', ROOT/'unavailable-test-fixtures'))")
    s=s.replace("ROOT/'work/full-product-audit-20261114/jobs/JOB_93099438cf014a689846bc05469759ad'", "FIXTURES/'archived-inputs'")
    s=s.replace("ROOT/'scripts/config/", "ROOT/'config/").replace("ROOT/'scripts/ai_judge/", "ROOT/'ai_judge/")
    s=s.replace("ROOT/'work/8788-contract-fix-20261114/evidence-before.json'", "FIXTURES/'archived-inputs-seal.json'")
    s=s.replace("len(seal['files']) != 433 or Path(source).resolve() != Path(seal['root']).resolve()", f"len(seal['files']) != {len(seal)} or Path(source).resolve() != DEFAULT_SOURCE.resolve()")
    s=s.replace("return json.loads(Path(path).read_text(encoding='utf-8-sig'))", "return json.loads(Path(path).read_text(encoding='utf-8-sig').replace('@FIXTURE@', DEFAULT_SOURCE.as_posix()))")
    s=s.replace("source_files=433",f"source_files={len(seal)}")
    s=s.replace("(ROOT/'scripts').rglob('*.py')", "ROOT.rglob('*.py')").replace("(ROOT/'scripts/config').rglob", "(ROOT/'config').rglob")
    # Regression seal hashes remain hashes of relocated fixture bytes; json loader
    # substitutes the marker only in memory. Original historical files untouched.
    write(p,s)
    # CWD-based credential discovery is intentionally not inherited.
    p=PKG/'site_client.py';s=p.read_text(encoding='utf-8');start=s.index('    cur = os.path.abspath(os.getcwd())');end=s.index('    out = []',start)
    s=s[:start]+s[end:];write(p,s)
    for row in PROVENANCE:
        path=ROOT/row['target'];row['target_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    write(ROOT/'reports/migration-provenance.json',json.dumps(PROVENANCE,ensure_ascii=False,indent=2))
    print(json.dumps({'assets':len(PROVENANCE),'archived_fixture_files':len(seal)}))

if __name__=='__main__':main()
