"""Stable labelled contact sheets; source files remain unchanged."""
import hashlib
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
from job_manager import atomic_json

def _local_evidence(directory, manifest, rows, residuals, template_rows=()):
    """Gaussian high-pass is independent of median residual; neither assigns ownership."""
    import cv2
    import numpy as np
    import math
    import time
    highpass=[]; crops=[]; tiles=[]
    highdir=directory/'highpass'; highdir.mkdir(exist_ok=True)
    cropdir=directory/'candidate_crops'; cropdir.mkdir(exist_ok=True)
    by_key={}
    for kind in ('main','detail','sku'):
        for i,row in enumerate(r for r in rows if r.get('kind')==kind and not r.get('error')):
            by_key[(kind,row.get('index',i))]=row
    residual_by_id={r['evidence_id']:r for r in residuals}
    def save_image(path,image):
        image.save(path,format='PNG')
        return str(path.relative_to(directory)),hashlib.sha256(path.read_bytes()).hexdigest()
    for number,row in enumerate(manifest):
        with Image.open(row['source']) as source:
            source=source.convert('RGB')
            gray=cv2.cvtColor(np.array(source),cv2.COLOR_RGB2GRAY).astype(np.float32)
            scales=[]
            highpass_started=time.perf_counter()
            for sigma in (3.0,9.0):
                band=gray-cv2.GaussianBlur(gray,(0,0),sigmaX=sigma,sigmaY=sigma)
                entry={'sigma_pixels':sigma,'gain':16.0}
                for polarity,signal in [('positive',band),('negative',-band)]:
                    image=Image.fromarray(np.clip(signal*16,0,255).astype(np.uint8))
                    path,digest=save_image(highdir/(str(number)+'_'+str(int(sigma))+'_'+polarity+'.png'),image)
                    entry[polarity+'_path']=path;entry[polarity+'_sha256']=digest
                    tiles.append((row['id']+' s='+str(sigma)+' '+polarity,image.copy()))
                scales.append(entry)
            highpass.append({'image_id':row['id'],'pool':row['kind'],'index':row['index'],
                             'source_sha256':row['sha256'],'source_coordinates':[0,0,source.width,source.height],
                             'algorithm':'gaussian-highpass/v1','scales':scales,
                             'elapsed_ms':round((time.perf_counter()-highpass_started)*1000,3)})
            proposals=[]
            for item in by_key.get((row['kind'],row['index']),{}).get('ocr',[]):
                rect=item.get('rect')
                if isinstance(rect,list) and len(rect)==4:
                    proposals.append((rect,'ocr-region/v1',item.get('score',0),{}))
            for band in by_key.get((row['kind'],row['index']),{}).get('borders',[]):
                pixels=band.get('pixels');side=band.get('side')
                if type(pixels) not in (int,float) or not math.isfinite(pixels) or pixels<=0:continue
                boxes={'top':[0,0,source.width,pixels],
                       'bottom':[0,source.height-pixels,source.width,source.height],
                       'left':[0,0,pixels,source.height],
                       'right':[source.width-pixels,0,source.width,source.height]}
                if side in boxes:proposals.append((boxes[side],'edge-band/v1',band.get('uniformity',0),{'band':band}))
            for match in template_rows:
                if match['evidence_id']==row['id'] and match['status'] in {'HIT','SUSPECT'} and match.get('source_coordinates'):
                    proposals.append((match['source_coordinates'],match['algorithm'],match['ncc'],
                                      {'template_sha256':match['template_sha256'],'projection':match.get('projection','gray')}))
            residual=residual_by_id.get(row['id'])
            if residual:
                with Image.open(directory/residual['path']) as image:
                    field=np.abs(np.array(image.convert('L')).astype(np.float32)-128)
                count,_,stats,_=cv2.connectedComponentsWithStats((field>=24).astype(np.uint8),8)
                for x,y,w,h,area in sorted(stats[1:count],key=lambda s:int(s[4]),reverse=True)[:6]:
                    if area<8 or w*h>field.size*.5: continue
                    sx,sy=source.width/field.shape[1],source.height/field.shape[0]
                    proposals.append(([math.floor(x*sx),math.floor(y*sy),math.ceil((x+w)*sx),math.ceil((y+h)*sy)],
                                      'median-residual-component/v1',min(1.,float(area)/float(w*h)),{}))
            seen=set()
            for rect,algorithm,score,provenance in proposals:
                if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in rect):continue
                x0,y0,x1,y1=rect
                box=(max(0,math.floor(x0)),max(0,math.floor(y0)),min(source.width,math.ceil(x1)),min(source.height,math.ceil(y1)))
                key=(box,algorithm)
                if box[2]<=box[0] or box[3]<=box[1] or key in seen:continue
                seen.add(key)
                path,digest=save_image(cropdir/(row['id']+'_'+str(len(seen))+'.png'),source.crop(box))
                crops.append({'image_id':row['id'],'pool':row['kind'],'index':row['index'],
                              'source_sha256':row['sha256'],'source_coordinates':list(box),'path':path,'sha256':digest,
                              'algorithm':algorithm,'score':score,'purpose':'localization only; no ownership verdict',**provenance})
    if tiles:
        sheet=Image.new('RGB',(960,270*((len(tiles)+3)//4)),'white');draw=ImageDraw.Draw(sheet)
        for i,(label,image) in enumerate(tiles):
            x,y=(i%4)*240,(i//4)*270
            sheet.paste(ImageOps.contain(image.convert('RGB'),(235,240)),(x,y));draw.text((x+2,y+245),label,fill='black')
        sheet.save(directory/'highpass_montage.jpg')
    atomic_json(directory/'highpass_manifest.json',{'algorithm':'gaussian-highpass/v1','items':highpass,
                'purpose':'localization only; independent from median residual; not a watermark verdict'})
    atomic_json(directory/'candidate_crop_manifest.json',{'items':crops,'status':'CANDIDATES' if crops else 'NO_CANDIDATES',
                'coordinates':'original pixels','purpose':'localization only; no automated removal authority'})
    return [directory/scale[polarity+'_path'] for item in highpass for scale in item['scales']
            for polarity in ('positive','negative')]+[directory/item['path'] for item in crops]

def build(directory, rows, templates=None, shop_id=None,templates_required=False):
    directory=Path(directory)
    manifest=[]
    for kind in ('main','detail','sku'):
        entries=[r for r in rows if r.get('kind')==kind and not r.get('error')]
        canvas=Image.new('RGB',(960,max(1,(len(entries)+3)//4)*270),'white')
        draw=ImageDraw.Draw(canvas)
        for i,row in enumerate(entries):
            source=Path(row['file'])
            if not source.is_absolute(): source=Path(__file__).parent/source
            data=source.read_bytes()
            with Image.open(source) as im: thumb=ImageOps.contain(im.convert('RGB'),(230,235))
            x,y=(i%4)*240,(i//4)*270
            canvas.paste(thumb,(x+(240-thumb.width)//2,y))
            label=kind.upper()+'_'+str(row.get('index',i)).zfill(3)
            draw.text((x+4,y+240),label,fill='black')
            manifest.append({'id':label,'source':str(source),'sha256':hashlib.sha256(data).hexdigest(),'kind':kind,'index':row.get('index',i),
                             'source_field':row.get('source','images'),'source_index':row.get('source_index',row.get('index',i))})
        canvas.save(directory/('audit_sheet_'+kind+'.jpg'))
    # Full-image high-pass evidence remains traceable to the unchanged source.
    import time
    started=time.perf_counter()
    residuals=[]
    from residcheck import resid
    import cv2
    import numpy as np
    out=directory/'residual'; out.mkdir(exist_ok=True)
    for index,row in enumerate(manifest):
        source=Path(row['source'])
        decoded=cv2.imdecode(np.frombuffer(source.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        if decoded is None: continue
        residual_started=time.perf_counter()
        visual,score=resid(decoded)
        target=out/(str(index)+'.png')
        cv2.imencode('.png',visual)[1].tofile(str(target))
        residuals.append({'evidence_id':row['id'],'source_sha256':row['sha256'],'path':str(target.relative_to(directory)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'mean_absolute_residual':score,'source_coordinates':[0,0,decoded.shape[1],decoded.shape[0]],
                          'elapsed_ms':round((time.perf_counter()-residual_started)*1000,3)})
    # Render actual residual evidence for review, including empty explicit results.
    if residuals:
        sheets=Image.new('RGB',(960,270*((len(residuals)+3)//4)),'white')
        for i,item in enumerate(residuals):
            with Image.open(directory/item['path']) as im:
                sheets.paste(ImageOps.contain(im.convert('RGB'),(240,250)),((i%4)*240,(i//4)*270))
        sheets.save(directory/'resid_montage.jpg')
    from template_applicability import resolve
    resolved=resolve(directory,shop_id,templates_required,templates)
    templates=resolved['templates']
    if resolved['source'] and Path(resolved['source']['source'])!=directory/'template_config.json':
        atomic_json(directory/'template_config.json',resolved['configuration'])
    applicable=[spec for spec in templates if spec.get('shop_id')==shop_id]
    template_sources=[resolved['source']] if resolved['source'] else []
    scans=[]
    from wm_tpl import scan,VERSION
    for spec in templates:
        if spec.get('shop_id') != shop_id:
            continue
        template_path=Path(spec['path'])
        if not template_path.is_absolute(): template_path=directory/template_path
        template_sources.append({'source':str(template_path.resolve()),'sha256':hashlib.sha256(template_path.read_bytes()).hexdigest(),'kind':'template','shop_id':shop_id})
        template=np.load(template_path,allow_pickle=False)
        for row in manifest:
            projection=spec.get('projection','gray')
            match=scan(row['source'],template,return_location=True,projection=projection)
            score=match.get('ncc') if isinstance(match,dict) else match
            scans.append({'image':row['source'],'evidence_id':row['id'],'source_sha256':row['sha256'],
                          'template_sha256':hashlib.sha256(template_path.read_bytes()).hexdigest(),
                          'shop_id':shop_id,'ncc':score,'status':'UNKNOWN' if score is None else ('HIT' if score>=.80 else ('CLEAN' if score<=.65 else 'SUSPECT')),
                          'source_coordinates':match.get('source_coordinates') if isinstance(match,dict) else None,
                          'algorithm':VERSION,'projection':projection,'variance_window':'top_left_aligned','std_floor':2.0,'hit_threshold':.80,'clean_threshold':.65})
    atomic_json(directory/'template_scan.json',{'items':scans,'status':resolved['status']})
    local_paths=_local_evidence(directory,manifest,rows,residuals,scans)
    atomic_json(directory/'residual_manifest.json' ,{'items':residuals,'elapsed_ms':round((time.perf_counter()-started)*1000,3),'purpose':'localization; residual score alone does not classify watermark'})
    atomic_json(directory/'audit_sheet_manifest.json',{'schema':'audit-sheet/v2','items':manifest,'purpose':'localization only; originals required for final judgement'})
    bound=[]
    names=['audit_account.json','audit_product.json','audit_flags.json','audit_raw.json','template_config.json','template_scan.json','candidate_crop_manifest.json','highpass_manifest.json','residual_manifest.json','audit_sheet_manifest.json']
    montages=[directory/name for name in ('resid_montage.jpg','highpass_montage.jpg')] if residuals else []
    current_paths=([directory/name for name in names]+montages+
                   [directory/('audit_sheet_'+kind+'.jpg') for kind in ('main','detail','sku')]+
                   [directory/item['path'] for item in residuals]+local_paths)
    for path in sorted(current_paths):
        if path.exists(): bound.append({'path':str(path.relative_to(directory)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    atomic_json(directory/'evidence_manifest.json',{'schema':'evidence-manifest/v1','files':bound,'sources':manifest+template_sources})
    return manifest
