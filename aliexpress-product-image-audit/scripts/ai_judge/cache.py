"""Context-complete stable cache keys. Only validated results may be stored."""
import hashlib,json
from pathlib import Path
from job_manager import atomic_json
def cache_key(task,evidence,context,model,prompt_version='v2',schema_version='v2',policy_version='v2'):
    from importlib import import_module
    prompt=import_module('ai_judge.'+task).PROMPT
    from .client import COMMON_OUTPUT_CONTRACT
    prompt += COMMON_OUTPUT_CONTRACT
    evidence={k:v for k,v in evidence.items() if k not in {'local','image_id','id','evidence_ids'}}
    if 'extra_images' in evidence:
        evidence['extra_images']=[{k:v for k,v in row.items() if k!='path'} for row in evidence['extra_images']]
    context={k:v for k,v in context.items() if k not in {'pid','shop','job_id','product_sha256'}}
    return hashlib.sha256(json.dumps([task,evidence,context,model,prompt,prompt_version,schema_version,policy_version],sort_keys=True).encode()).hexdigest()
class ResultCache:
    def __init__(self,root): self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def get(self,key):
        path=self.root/(key+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    def put(self,key,result,validator):
        validator(result)
        atomic_json(self.root/(key+'.json'),result)
