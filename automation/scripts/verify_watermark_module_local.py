"""Explicit offline acceptance: synthetic annotations, actual installed LaMa.

Never calls a semantic model or product endpoint. Does not grant AI quality PASS.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    with (out/'claimed').open('x') as stream:stream.write('One offline acceptance run; actual local LaMa; no model API or product I/O.')
    sys.path.insert(0,str(ROOT/'tests'))
    from watermark_module_fixtures import varied_sample,sample
    from mye_c_automation.watermark_processing import process_watermarks,WatermarkQualityChecker
    from mye_c_automation.image_repairs_v2 import lama_torchscript
    from mye_c_automation.configuration import load_image_options
    import socket
    from unittest.mock import patch
    import torch
    torch.set_num_threads(4)
    options=load_image_options(ROOT/'local/image-options.local.json')
    started=time.perf_counter();backend=lama_torchscript(options['lama_model_path'],options['lama_model_sha256'])
    load_time=time.perf_counter()-started;calls=[]
    def counted(image,mask):
        before=time.perf_counter();candidate=backend(image,mask)
        calls.append(dict(image_shape=list(image.shape),mask_shape=list(mask.shape),elapsed_seconds=round(time.perf_counter()-before,6)))
        return candidate
    counted.model_sha256=backend.model_sha256;counted.input_contract=backend.input_contract
    cases=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    def no_network(*a,**k):raise AssertionError('NETWORK_FORBIDDEN')
    with patch.object(socket.socket,'connect',side_effect=no_network),patch.object(socket.socket,'connect_ex',side_effect=no_network):
        for layout in ['SINGLE','REPEATED','DIAGONAL','HORIZONTAL','VERTICAL','GRID','SCATTERED','MIXED','SIMPLE_BLACK','SIMPLE_WHITE','PRODUCT_SURFACE']:
            folder=out/layout
            if layout.startswith('SIMPLE_'):
                request=sample(folder,background='black' if layout.endswith('BLACK') else 'white')
            elif layout=='PRODUCT_SURFACE':
                request=sample(folder,boxes=[[.43,.40,.56,.47]],complexity='COMPLEX');request['watermarks'][0].update(opacity=.5,subject_overlap=True)
            else:request=varied_sample(folder,layout,background='black' if len(layout)%2 else 'white')
            (folder/'input.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
            before=len(calls);result=process_watermarks(request,folder/'result',lama=counted,policy=dict(max_roi_area=.55))
            checks=WatermarkQualityChecker().check(request,result) if result['processing_status']=='PROCESSED' else dict(ok=False,reason=result['failure_reason'])
            if checks['ok']:
                pictures=[Image.open(request['image_path']).convert('RGB'),Image.open(result['visualization_path']).convert('RGB'),Image.open(result['output_path']).convert('RGB')]
                board=Image.new('RGB',(1920,525),'#f6f7fa');draw=ImageDraw.Draw(board)
                for i,(label,picture) in enumerate(zip(['原图（测试标注）','Mask 可视化','本地修复 · 待AI复核'],pictures)):
                    draw.text((640*i+10,8),layout+' · '+label,fill='black',font=font)
                    picture.thumbnail((640,480));board.paste(picture,(640*i+(640-picture.width)//2,45+(480-picture.height)//2))
                board.save(folder/'comparison.png')
            row=dict(case=layout,processing_status=result['processing_status'],quality_status=result['quality_status'],
                algorithm=result['algorithm_used'],instances=result['watermark_instances_total'],regions=len(result['regions']),
                actual_lama_calls=len(calls)-before,deterministic_quality=checks,execution_time=result['execution_time'],
                result=str(folder/'result/processing-result.json'),comparison=str(folder/'comparison.png'))
            cases.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    result=dict(status='REAL_LOCAL_INFERENCE_VERIFIED' if all(r['deterministic_quality']['ok'] for r in cases) else 'FAILED',
        semantic_annotations='SYNTHETIC_FIXTURE_NOT_REAL_DEEPSEEK',semantic_quality='NOT_RUN_PENDING_AI_REVIEW',
        actual_lama_calls=len(calls),opencv_cases=sum(r['actual_lama_calls']==0 for r in cases),
        load_seconds=round(load_time,6),model_path=options['lama_model_path'],model_sha256=backend.model_sha256,
        input_contract=backend.input_contract,inferences=calls,cases=cases,real_deepseek_requests=0,site_reads=0,uploads=0,saves=0)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    gallery='<!doctype html><meta charset="utf-8"><title>通用水印模块本地验收</title><style>body{font:16px system-ui;background:#f6f7fa;padding:20px}img{width:100%;max-width:1600px}section{margin:30px 0}</style><h1>通用水印模块：本地推理对比</h1><p>测试标注；真实本地 LaMa / OpenCV；最终语义质量待 AI 复核。没有线上修改。</p>'
    for row in cases:gallery+='<section><h2>'+row['case']+'</h2><p>'+row['processing_status']+' / '+row['quality_status']+'</p><img src="'+row['case']+'/comparison.png"></section>'
    (out/'gallery.html').write_text(gallery,encoding='utf-8')
    return 0 if result['status']=='REAL_LOCAL_INFERENCE_VERIFIED' else 1


if __name__=='__main__':raise SystemExit(main())
