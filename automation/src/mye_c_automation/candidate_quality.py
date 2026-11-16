"""Independent pixel and semantic gate. Unavailable checks never count as passes."""
import hashlib
from pathlib import Path
from PIL import Image

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class CandidateQualityGate:
    def __init__(self, inspector=None):
        self.inspector=inspector

    def validate(self, source, candidate, context, expected_sha256=None):
        result={'ok':False,'checks':{},'evidence_ids':[]}
        try:
            source,candidate=Path(source),Path(candidate)
            digest=sha256(candidate)
            result.update(source_sha256=sha256(source),candidate_sha256=digest)
            if expected_sha256 is not None and digest!=expected_sha256: raise ValueError('CANDIDATE_HASH_MISMATCH')
            if candidate.stat().st_size>20*1024*1024: raise ValueError('CANDIDATE_TOO_LARGE')
            with Image.open(candidate) as image:
                image.verify()
                if image.format not in {'PNG','JPEG','WEBP'} or min(image.size)<800:
                    raise ValueError('CANDIDATE_FORMAT_OR_SIZE')
                result.update(width=image.width,height=image.height,mime=Image.MIME[image.format])
            if self.inspector is None: raise ValueError('CONTENT_VALIDATOR_UNAVAILABLE')
            observed=self.inspector.inspect(source,candidate,context)
            required={'product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','ocr_pass','residual_pass','template_pass'}
            if not observed.get('evidence_ids') or any(observed.get(k) is not True for k in required):
                raise ValueError('CONTENT_VALIDATION_FAILED')
            # Re-open after the external validator to reject changes during inspection.
            if sha256(source)!=result['source_sha256'] or sha256(candidate)!=digest:
                raise ValueError('VALIDATOR_INPUT_CHANGED')
            result.update(ok=True,checks={k:v for k,v in observed.items() if type(v) is bool},evidence_ids=observed['evidence_ids'])
            result['checks']['source_bound']=True
        except Exception as exc:
            result['reason']=str(exc)
        return result
