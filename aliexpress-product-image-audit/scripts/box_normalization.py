"""SOP pixel transform only; callers must independently establish BOX and quality."""
from pathlib import Path
import hashlib
from PIL import Image, ImageFilter, ImageOps

def normalize_box(source, target):
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target:raise ValueError('SOURCE_OVERWRITE')
    original=source.read_bytes()
    with Image.open(source) as opened:
        opened.load()
        image=ImageOps.exif_transpose(opened).convert('RGBA')
        width,height=image.size
        if min(width,height)>=800:raise ValueError('NOT_SMALL')
        if min(width,height)<=0:raise ValueError('INVALID_SIZE')
        scale=800/max(width,height)
        size=(max(1,round(width*scale)),max(1,round(height*scale)))
        resized=image.resize(size,Image.Resampling.LANCZOS)
        background=Image.new('RGB',(800,800),'white')
        left,top=(800-size[0])//2,(800-size[1])//2
        background.paste(resized,(left,top),resized.getchannel('A'))
        background=background.filter(ImageFilter.UnsharpMask(radius=0.6,percent=40,threshold=3))
        target.parent.mkdir(parents=True,exist_ok=True)
        background.save(target,format='PNG')
    if source.read_bytes()!=original:raise ValueError('SOURCE_CHANGED')
    return {'method':'LANCZOS_WHITE_PAD_LIGHT_SHARPEN','source_sha256':hashlib.sha256(original).hexdigest(),
            'candidate_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'source_size':[width,height],'content_box':[left,top,left+size[0],top+size[1]],
            'requires_independent_quality_validation':True}
