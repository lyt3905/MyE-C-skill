"""Execution envelope over V2 regions; no product fields or semantic classifier."""
from dataclasses import dataclass
from copy import deepcopy
import base64
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image
from mye_c_automation.ai_judge.image_action_decision import validate_watermarks, mark_disposition, mark_owner, region
from mye_c_automation.resources import validate_resource_json

VERSION='watermark-processing.v1'
DEFAULT_POLICY=dict(max_mask_area=.25,max_roi_area=.45,context_pixels=16,adjacency_pixels=8,dilation=2,
                    opencv_max_mask_area=.04,opencv_max_roi_area=.20,radius=3)


def policy_options(value=None):
    value={} if value is None else deepcopy(value)
    validate_resource_json(value,'watermark-processing-policy.v1.schema.json')
    return dict(DEFAULT_POLICY,**value)


def check_polygon(mark):
    points=region(mark)
    if 'bbox' in mark and 'polygon' in mark:raise ValueError('AMBIGUOUS_REGION')
    if len({tuple(p) for p in points})!=len(points):raise ValueError('DUPLICATE_POLYGON_VERTEX')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        if max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0]) or max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1]):return False
        return cross(a,b,c)*cross(a,b,d)<=0 and cross(c,d,a)*cross(c,d,b)<=0
    for i,a in enumerate(points):
        b=points[(i+1)%len(points)]
        for j in range(i+1,len(points)):
            if j==i+1 or i==0 and j==len(points)-1:continue
            if intersects(a,b,points[j],points[(j+1)%len(points)]):raise ValueError('SELF_INTERSECTING_POLYGON')
    if mark.get('region_type') not in (None,'BBOX' if 'bbox' in mark else 'POLYGON'):raise ValueError('REGION_TYPE_MISMATCH')
    return points


@dataclass
class ParsedInput:
    request: dict
    source_path: object
    source_bytes: bytes
    sha256: str
    pixels: np.ndarray
    rgba: np.ndarray
    instances: list


class WatermarkInputParser:
    def parse(self,request):
        if not isinstance(request,dict):raise ValueError('INVALID_INPUT')
        value=deepcopy(request);serial=deepcopy(value)
        if isinstance(serial.get('image_bytes'),bytes):serial['image_bytes']=base64.b64encode(serial['image_bytes']).decode('ascii')
        validate_resource_json(serial,'watermark-processing-input.v1.schema.json')
        source=Path(value['image_path']).resolve() if 'image_path' in value else None
        if source is not None:data=source.read_bytes()
        else:
            data=value['image_bytes']
            if isinstance(data,str):
                try:data=base64.b64decode(data,validate=True)
                except (ValueError,TypeError) as exc:raise ValueError('INVALID_IMAGE_BYTES') from exc
        digest=hashlib.sha256(data).hexdigest()
        if digest!=value['image_sha256']:raise ValueError('IMAGE_SHA_MISMATCH')
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.size!=(value['image_width'],value['image_height']):raise ValueError('IMAGE_SIZE_MISMATCH')
            if image.format not in {'PNG','JPEG','WEBP'} or image.mode not in {'RGB','RGBA','P','L','LA'}:raise ValueError('IMAGE_FORMAT')
            rgba=np.array(image.convert('RGBA'));pixels=rgba[:,:,:3].copy()
        validate_watermarks(value['watermarks']);ids=set();instances=[]
        for index,mark in enumerate(value['watermarks']):
            check_polygon(mark)
            identifier=mark.get('watermark_id','v2-instance-'+str(index))
            if identifier in ids:raise ValueError('DUPLICATE_WATERMARK_ID')
            ids.add(identifier)
            if mark_disposition(mark)=='REMOVABLE':
                if mark_owner(mark) in {'MANUFACTURER','PRODUCT','PACKAGING','CREATOR'} or mark['kind'] in {'MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','MODEL_TEXT','CREATOR_CREDIT','NORMAL_PHOTO_TEXT'}:raise ValueError('PROTECTED_SEMANTIC_CONFLICT')
                if mark.get('repair_mode') not in {None,'REGION'}:raise ValueError('EXPLICIT_INSTANCE_REGIONS_REQUIRED')
                if mark['preserve_overlap_risk']!='LOW':raise ValueError('REGION_RISK')
                instances.append(dict(mark,watermark_id=identifier,group_id=mark.get('group_id','v2-group-'+str(index))))
        for protected in value['preserve_regions']:check_polygon(protected)
        return ParsedInput(value,source,data,digest,pixels,rgba,instances)


def from_v2(source,observation,rights):
    """Adapt existing V2 output; never alter raw semantic fields."""
    source=Path(source)
    with Image.open(source) as image:width,height=image.size
    return dict(schema_version=VERSION,image_path=str(source),image_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        image_width=width,image_height=height,decision=observation['decision'],authorization_status=rights,
        watermarks=deepcopy(observation['watermarks']),preserve_regions=deepcopy(observation['preserve_regions']),
        background_complexity=observation.get('background_complexity','UNKNOWN'))
