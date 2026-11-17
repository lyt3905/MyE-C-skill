"""Generic, explicitly annotated fixtures: no detector or store-specific content."""
import hashlib
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def sample(root, *, boxes=None, background='white', complexity='SMOOTH', alpha=False, decorations=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGBA' if alpha else 'RGB',(320,240),background)
    draw=ImageDraw.Draw(image)
    draw.rectangle((132,70,188,175),fill=(25,95,160,180) if alpha else (25,95,160))
    draw.text((130,181),'X9',fill='black')
    boxes=boxes or [[.05,.15,.19,.22]]
    marks=[]
    for i,box in enumerate(boxes):
        coords=[int(v*s) for v,s in zip(box,(320,240,320,240))]
        draw.rectangle(coords,fill=(190,70,150,155) if alpha else (190,70,150))
        marks.append(dict(watermark_id='instance-'+str(i),group_id='group-0',kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',
            action='REMOVE_TEXT',bbox=box,confidence=0.0,preserve_overlap_risk='LOW',repair_mode='REGION',region_type='BBOX',
            arrangement='SCATTERED',content_type='TEXT'))
    path=root/'source.png';image.save(path)
    return dict(schema_version='watermark-processing.v1',image_path=str(path),image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        image_width=320,image_height=240,decision='REMOVE_TEXT',authorization_status='OWNED_OR_LICENSED',watermarks=marks,
        preserve_regions=[dict(kind='PRODUCT_PRINT',bbox=[.39,.74,.62,.84])],background_complexity=complexity)


def varied_sample(root, arrangement, *, background='black'):
    """AI-equivalent explicit rotated polygons across distinct synthetic styles."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(640,480),background);draw=ImageDraw.Draw(image)
    draw.rectangle((280,155,360,315),fill=(40,120,180));draw.text((285,320),'FACTORY X9',fill='gray')
    points={'SINGLE':[(55,65)],'REPEATED':[(35,60),(415,300)],'DIAGONAL':[(25,50),(150,135),(390,260)],
        'HORIZONTAL':[(25,60),(215,60),(410,60)],'VERTICAL':[(35,40),(35,180),(35,320)],
        'GRID':[(25,45),(410,45),(25,320),(410,320)],'SCATTERED':[(40,50),(425,180),(95,335)],
        'MIXED':[(25,40),(210,40),(410,175),(70,325)]}[arrangement]
    marks=[];fonts=['C:/Windows/Fonts/arial.ttf','C:/Windows/Fonts/times.ttf','C:/Windows/Fonts/consola.ttf']
    for i,(x,y) in enumerate(points):
        stamp=Image.new('RGBA',(145,40));d=ImageDraw.Draw(stamp);font=ImageFont.truetype(fonts[i%3],18+i*2)
        d.text((7,3),['ALPHA 42','Sample B','Violet'][i%3],font=font,fill=[(210,40,140,90),(30,170,80,145),(200,140,30,210)][i%3]);d.ellipse((110,5,132,26),outline=(120,80,200,145),width=2)
        angle=[-28,0,41,90][i%4];rotated=stamp.rotate(angle,expand=True,resample=Image.Resampling.BICUBIC)
        image.paste(rotated,(x,y),rotated)
        # Full rotated instance extent is explicitly supplied, never discovered.
        x1,y1=min(640,x+rotated.width),min(480,y+rotated.height)
        marks.append(dict(watermark_id='w'+str(i),group_id='g'+str(i%2),kind='STORE_WATERMARK',action='REMOVE_TEXT',owner='THIRD_PARTY_STORE',
            polygon=[[x/640,y/480],[x1/640,y/480],[x1/640,y1/480],[x/640,y1/480]],confidence=.1*i,
            preserve_overlap_risk='LOW',repair_mode='REGION',region_type='POLYGON',arrangement=arrangement,content_type='TEXT_AND_GRAPHIC',opacity=[.35,.6,.85][i%3]))
    path=root/'source.png';image.save(path)
    return dict(schema_version='watermark-processing.v1',image_path=str(path),image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        image_width=640,image_height=480,decision='REMOVE_TEXT',authorization_status='OWNED_OR_LICENSED',watermarks=marks,
        preserve_regions=[dict(kind='MODEL_TEXT',bbox=[.42,.66,.58,.70])],background_complexity='COMPLEX')
