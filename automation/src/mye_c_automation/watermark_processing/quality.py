"""File/byte/mask checks; visual semantics remain with the existing reviewer."""
import hashlib
import io
from pathlib import Path
import numpy as np
from PIL import Image


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class WatermarkQualityChecker:
    def check(self,request,result):
        try:
            if 'image_path' in request:
                if sha(request['image_path'])!=request['image_sha256']:raise ValueError('ORIGINAL_CHANGED')
                data=Path(request['image_path']).read_bytes()
            else:
                import base64
                data=request['image_bytes']
                if isinstance(data,str):data=base64.b64decode(data,validate=True)
                if hashlib.sha256(data).hexdigest()!=request['image_sha256']:raise ValueError('ORIGINAL_CHANGED')
            with Image.open(io.BytesIO(data)) as image:before=np.array(image.convert('RGBA'))
            path=Path(result['output_path'])
            if result['output_sha256']!=sha(path):raise ValueError('OUTPUT_SHA_MISMATCH')
            with Image.open(path) as image:
                if image.format!='PNG':raise ValueError('OUTPUT_FORMAT')
                after=np.array(image.convert('RGBA'))
            if before.shape!=after.shape:raise ValueError('OUTPUT_SIZE')
            union=None
            for name,digest in result['mask_sha256'].items():
                if sha(name)!=digest:raise ValueError('MASK_SHA_MISMATCH')
                with Image.open(name) as image:
                    if image.mode!='L' or image.size!=(request['image_width'],request['image_height']):raise ValueError('INVALID_MASK')
                    mask=np.array(image)
                if not np.isin(mask,[0,255]).all() or not np.any(mask):raise ValueError('INVALID_MASK')
                if name==result['mask_paths'][0]:union=mask>0
            if union is None:raise ValueError('MISSING_UNION_MASK')
            if not np.array_equal(before[~union],after[~union]):raise ValueError('OUTSIDE_MASK_CHANGED')
            if not np.array_equal(before[:,:,3],after[:,:,3]):raise ValueError('ALPHA_CHANGED')
            if np.array_equal(before,after):raise ValueError('UNCHANGED_CANDIDATE')
            # Content suitability (including a now-empty background) belongs to
            # the existing V2 candidate gate, not this pixel execution module.
            if not result['regions'] or result['watermark_instances_processed']!=result['watermark_instances_total']:raise ValueError('INCOMPLETE_REGIONS')
            return dict(ok=True,outside_mask_unchanged=True,source_unchanged=True,output_sha256=result['output_sha256'])
        except (ValueError,TypeError,KeyError,OSError) as exc:return dict(ok=False,reason=str(exc))
