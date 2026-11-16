"""Complete the explicit test-fixture/data relocation after first full regression."""
import hashlib,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'src/mye_c_automation'
SOURCE=ROOT.parent/'aliexpress-product-image-audit'
fixture=ROOT/'tests/fixtures/archived-inputs'
name='recovery_8788_1/combined_judgements.final2.json'
source=SOURCE/'work/full-product-audit-20261114/jobs/JOB_93099438cf014a689846bc05469759ad'/name
target=fixture/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
seal={p.relative_to(fixture).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.rglob('*') if p.is_file()}
(ROOT/'tests/fixtures/archived-inputs-seal.json').write_text(json.dumps({'files':seal},indent=2),encoding='utf-8')
p=PKG/'run_8788_real_validation.py';s=p.read_text(encoding='utf-8').replace("len(seal['files']) != 25",f"len(seal['files']) != {len(seal)}").replace('source_files=25',f'source_files={len(seal)}');p.write_text(s,encoding='utf-8')
p=PKG/'audit_one.py';s=p.read_text(encoding='utf-8').replace('EVIDENCE_CACHE = ROOT / ".cache" / "audit_evidence" / "v1"',"from mye_c_automation.paths import data_root\nEVIDENCE_CACHE = data_root() / 'cache' / 'audit_evidence' / 'v1'");p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_v2_workflow.py';s=p.read_text(encoding='utf-8').replace("tempfile.TemporaryDirectory(dir=Path.cwd()/'work')",'tempfile.TemporaryDirectory()');p.write_text(s,encoding='utf-8')
p=PKG/'fake.py';s=p.read_text(encoding='utf-8').replace("assets['https://fake/spare']=image_bytes(other if scenario=='twin' else clean)","assets['https://fake/spare']=image_bytes(other if scenario=='twin' else Image.fromarray(np.random.default_rng(170).integers(20,235,(1000,1000,3),dtype=np.uint8)))")
s=s.replace("def product(self,pid):self.counters['independent_reads']+=1;return copy.deepcopy(self.state)","def product(self,pid):\n        self.counters['independent_reads']+=1\n        if self.counters['saves']:self.counters['independent_readbacks']+=1\n        return copy.deepcopy(self.state)")
s=s.replace("def product(self,pid):return copy.deepcopy(self.state)","def product(self,pid):\n        if self.counters['saves']:return self.readonly_client().product(pid)\n        return copy.deepcopy(self.state)")
s=s.replace('independent_reads=0,model_calls=0','independent_reads=0,independent_readbacks=0,model_calls=0');p.write_text(s,encoding='utf-8')
provenance=json.loads((ROOT/'reports/migration-provenance.json').read_text(encoding='utf-8'))
provenance.append(dict(source=source.relative_to(SOURCE).as_posix(),target=target.relative_to(ROOT).as_posix(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
for row in provenance:row['target_sha256']=hashlib.sha256((ROOT/row['target']).read_bytes()).hexdigest()
(ROOT/'reports/migration-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'archived_fixture_files':len(seal)}))
