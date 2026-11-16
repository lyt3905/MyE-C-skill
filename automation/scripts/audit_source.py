"""Development-only source inventory; never imported by the installed software."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'aliexpress-product-image-audit'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    reports = ROOT/'reports'
    reports.mkdir(parents=True, exist_ok=True)
    snapshot = {p.relative_to(SOURCE).as_posix(): {'sha256':sha(p), 'bytes':p.stat().st_size}
                for p in SOURCE.rglob('*') if p.is_file()}
    (reports/'source-before.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    commands = ['status --short --branch', 'rev-parse HEAD', 'branch --show-current', 'diff', 'diff --cached']
    git = {c:subprocess.check_output(['git',*c.split()],cwd=SOURCE).decode('utf-8',errors='replace') for c in commands}
    (reports/'workspace-before.json').write_text(json.dumps(git,ensure_ascii=False,indent=2),encoding='utf-8')
    modules={p.stem:p for p in (SOURCE/'scripts').glob('*.py')}
    modules.update({p.name:p for p in (SOURCE/'scripts').iterdir() if p.is_dir() and (p/'__init__.py').is_file()})
    edges={}
    for p in list((SOURCE/'scripts').rglob('*.py'))+list((SOURCE/'tests').glob('*.py')):
        if '__pycache__' in p.parts: continue
        try: tree=ast.parse(p.read_text(encoding='utf-8-sig'))
        except (SyntaxError,UnicodeError):continue
        imports=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):imports.update(a.name.split('.')[0] for a in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:imports.add(n.module.split('.')[0])
        edges[p.relative_to(SOURCE).as_posix()]=sorted(imports)
    selected={'workflow_runner','full_product_audit','v2_remediation','visual_versions'}
    for name,imports in edges.items():
        if name.startswith('tests/'):selected.update(set(imports)&modules.keys())
    while True:
        old=selected.copy()
        for name,imports in edges.items():
            if name.split('/')[1].removesuffix('.py') in selected:selected.update(set(imports)&modules.keys())
        if old==selected:break
    # These modules contain archived acceptance contracts still exercised by regression tests.
    (reports/'dependency-audit.json').write_text(json.dumps({'modules':sorted(selected),'imports':edges},indent=2),encoding='utf-8')
    inventory=[]
    for name,record in snapshot.items():
        parts=Path(name).parts; first=parts[0]; caller=[p for p,imports in edges.items() if Path(name).stem in imports]
        target=None;method='READ_ONLY_RETAIN';required=False
        if first=='scripts' and len(parts)>1 and parts[1].removesuffix('.py') in selected and name.endswith('.py'):
            category='PROGRAM_MODEL_ADAPTER' if parts[1]=='ai_judge' else 'PROGRAM_CORE'
            target='src/mye_c_automation/'+ '/'.join(parts[1:]);method='COPY_REFACTOR';required=True
        elif first=='scripts' and len(parts)>1 and parts[1]=='config':
            category='PROGRAM_SCHEMA' if 'schema' in name else 'PROGRAM_CONFIG';target='src/mye_c_automation/config/'+ '/'.join(parts[2:]);method='COPY';required=True
        elif first=='prompts':category='PROGRAM_PROMPT';target='src/mye_c_automation/'+name;method='COPY';required=True
        elif first=='tests':category='PROGRAM_TEST' if name.endswith('.py') else 'PROGRAM_TEST_FIXTURE';target=name;method='COPY_REFACTOR'
        elif first in {'local','.venv'} or 'cfg.local' in name:category='PROGRAM_MODEL_RESOURCE' if name.endswith(('.pt','.onnx')) else 'SECRET_OR_LOCAL_CONFIG'
        elif first in {'work','jobs'}:category='HISTORICAL_MODEL_RESPONSE' if 'response' in name else 'HISTORICAL_JOB_DATA'
        elif first=='reports':category='HISTORICAL_REPORT'
        elif 'cache' in name.lower() or name.endswith(('.sqlite','.db')):category='LEDGER_OR_CACHE'
        elif first=='references':category='SKILL_REFERENCE'
        elif 'SOP' in name:category='BUSINESS_SOP'
        elif Path(name).name in {'SKILL.md','AGENTS.md'}:category='SKILL_INSTRUCTION'
        elif first=='docs' or name.endswith('.md'):category='PROGRAM_TECH_DOC'
        elif name.startswith('requirements'):category='EXTERNAL_DEPENDENCY'
        else:category='UNKNOWN'
        inventory.append(dict(path=name,category=category,purpose='Baseline '+category.lower(),callers=caller,runtime_required=required,
            dependencies=edges.get(name,[]),sensitive_or_historical=category.startswith(('SECRET','HISTORICAL','LEDGER')),target=target,method=method,
            risk='Preserve source; verify resource paths and regression parity' if target else 'Not distributed; retain at source',
            validation='SHA provenance; isolated offline regression',**record))
    (reports/'asset-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    (reports/'asset-inventory.md').write_text('# Asset inventory\n\nFull per-file classification, SHA, callers, dependencies, target and validation: `asset-inventory.json`.\n\n'+
        '\n'.join(f'- {c}: {sum(r["category"]==c for r in inventory)}' for c in sorted({r['category'] for r in inventory}))+
        '\n\nUNKNOWN and local secrets remain at source. No historical Job becomes active data.\n',encoding='utf-8')
    (reports/'source-dependency-map.md').write_text('# Source dependency map\n\nCLI → workflow_runner.run_automatic → full_product_audit.run_full_audit → ai_judge.JudgeClient / image_action_decision → visual_versions → v2_remediation → plan_compiler → executor.local.LocalExecutor → independent content readback.\n\nDescription image nodes and SHA content groups feed the same plan; SKU selection remains sku_assignment. Detailed static imports: `dependency-audit.json`. Dynamic task prompts in JudgeClient must use the new package namespace.\n\nSelected modules:\n'+ '\n'.join('- '+n for n in sorted(selected)),encoding='utf-8')
    (reports/'migration-plan.md').write_text('''# Independent automation implementation plan

Goal: Installable Python src package preserving the 68e168f V2 implementation.
Architecture: Keep existing module responsibilities and a single runner/client/compiler/executor. Namespace imports, package resources, separate data paths, add CLI orchestration only.
Spec: User-provided MyE-C-skill independent automation construction specification (2026-11-16).

Constraints: Source read-only; single agent; local offline only; no git staging, commits or pushes. All changes inside automation. No model weights, credentials or historical Jobs as active data.

- [ ] Audit and snapshot all original files and workspace modifications; trace imports and resource paths.
- [ ] Run the entire original test discovery on a disposable baseline mirror with network blocked and bytecode disabled (protect original files).
- [ ] Copy only classified program modules, prompts, config/schema and tests. Refactor imports to mye_c_automation; use package resources and independent data roots.
- [ ] Preserve archived acceptance fixtures explicitly in regression fixtures, with source hashes; never expose archived runners as the CLI.
- [ ] Add installation metadata, resource diagnostics, V2 CLI/JSON, Fake adapters and persistent Fake demonstration using the existing production runner.
- [ ] Test wheel installation from an unrelated working directory. Guard original-directory access with an interpreter audit hook; run complete regression and Fake workflow.
- [ ] Compare discovery IDs and source hashes, scan paths/symlinks, produce acceptance and limitations.

Review focus: subprocess module paths; wheel resource inclusion; historical fixture absolute paths; default ledger/lock placement; lost save response never resends.

Ruling: User supplied a detailed design and explicitly requested continuous execution without phase approval. Reuse module boundaries rather than manufacture another V2 architecture. User forbids subagents and commits, so review is performed locally and all work remains unstaged.
''',encoding='utf-8')
    print(json.dumps({'source_files':len(snapshot),'selected_modules':len(selected),'bytes':sum(r['bytes'] for r in snapshot.values())}))

if __name__=='__main__':main()
