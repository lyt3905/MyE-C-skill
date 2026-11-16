"""Offline diagnostics of sealed image evidence. No Site, Writer, or Judge calls."""
from mye_c_automation.policy_engine import MODEL_CONFIDENCE_MIN
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PIL import Image
from mye_c_automation.ai_judge.watermark_contract import aggregate_watermarks
from mye_c_automation.ai_judge.identity_contract import aggregate_identity
from mye_c_automation.full_product_audit import assemble_report

OPTIONAL=('full_ai_queue.json','full_ai_judgements.json','full_ai_metrics.json','full_audit_report.json',
          'coverage_matrix.json','combined_judgements.json','new_judgements.json','new_metrics.json',
          'highpass_manifest.json','candidate_crop_manifest.json','source_verified.json','authorization.json','parent_bindings.json')


def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def baseline_trigger(task,result):
    """First-return condition of the recorded v1 consumer, not a model inference."""
    rows=result.get('results',[])
    if len(rows)!=2:return {'branch':'_strong: result_count != 2','reason_code':'REQUIRED_FIELD_MISSING','field':'results'}
    for i,row in enumerate(rows):
        if row.get('abstain') is not False:return {'branch':'_strong: abstain','reason_code':'MODEL_ABSTAIN','model_index':i,'field':'abstain','value':row.get('abstain')}
        if type(row.get('confidence')) not in (int,float) or row['confidence']<MODEL_CONFIDENCE_MIN:return {'branch':f'_strong: confidence < {MODEL_CONFIDENCE_MIN:.2f}','reason_code':'LOW_CONFIDENCE','model_index':i,'field':'confidence','value':row.get('confidence')}
    if task=='watermark':
        from mye_c_automation.policy_engine import KEEP, REMOVE, evaluate
        for i,row in enumerate(rows):
            if not isinstance(row.get('marks'),list) or not row['marks']:return {'branch':'_watermark: missing/empty marks','reason_code':'MARKS_INCOMPLETE','model_index':i,'field':'marks'}
            for j,mark in enumerate(row['marks']):
                for field,invalid,code in (
                    ('classification',mark.get('classification') not in KEEP|REMOVE,'OWNER_UNPROVEN'),
                    ('confidence',type(mark.get('confidence')) not in (int,float) or mark['confidence']<MODEL_CONFIDENCE_MIN,'LOW_CONFIDENCE'),
                    ('owner',not mark.get('owner'),'OWNER_UNPROVEN'),('location',not mark.get('location'),'EVIDENCE_INSUFFICIENT')):
                    if invalid:return {'branch':'_watermark: mark validation','reason_code':code,'model_index':i,'field':f'marks[{j}].{field}','value':mark.get(field)}
        if len({r.get('classification') for r in rows})!=1:return {'branch':'_watermark: root policy disagreement','reason_code':'MODEL_DISAGREEMENT','field':'classification'}
    elif task=='product_identity':
        if len({r.get('image_type') for r in rows})!=1:return {'branch':'_identity: image_type disagreement','reason_code':'IMAGE_TYPE_CONFLICT','field':'image_type'}
    return None


def diagnose(job_directory,output,declared_model):
    job=Path(job_directory);phase=job/'recovery_8788_1';output=Path(output)
    if job.resolve()==output.resolve() or job.resolve() in output.resolve().parents:raise ValueError('OUTPUT_MUST_NOT_MODIFY_JOB')
    def read(path):return json.loads(path.read_text(encoding='utf-8'))
    def choose(names):
        for p in names:
            if p.is_file():return p
        raise ValueError('REQUIRED_DIAGNOSTIC_INPUT_MISSING')
    inventory_path=choose([job/'full_inventory.json']);queue_path=choose([job/'full_ai_queue.json'])
    result_path=choose([phase/'combined_judgements.final2.json',phase/'combined_judgements.final.json',phase/'combined_judgements.json',job/'full_ai_judgements.json'])
    report_paths=[phase/'final_report.after-component.json',phase/'final_report.json',job/'full_audit_report.json']
    old_path=next((p for p in report_paths if p.is_file()),None)
    inventory,queue,results=read(inventory_path),read(queue_path),read(result_path)
    original=read(old_path) if old_path else {}
    before={str(p.relative_to(job)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob('*') if p.is_file()}
    # Reconstruct only in-scope image-pool and SKU-reference metadata. The fixed
    # field and its content are never parsed, copied or used as test input here.
    pools={name:[] for name in ('main','detail','sku')};skus=[]
    for occurrence in sorted(inventory['occurrences'],key=lambda r:(r.get('pool','zz'),r.get('index',r.get('sku_row_index',0)))):
        if occurrence['target_type']=='image_slot':
            if occurrence['pool'] not in pools:raise ValueError('OUT_OF_SCOPE_IMAGE_POOL')
            pools[occurrence['pool']].append(occurrence['url'])
        else:skus.append({'skuName':occurrence['sku_name'],'skuImageUrl':occurrence['url']})
    product={'id':queue['pid'],'identityJson':{'modelCode':declared_model},'images':pools,'skus':skus}
    model_names=['model_a','model_b'];auth=phase/'authorization.json'
    if auth.exists():model_names=read(auth).get('model_config',{}).get('models',model_names)
    protocol=job/'full_audit_protocol.json';original_models=read(protocol).get('models',model_names) if protocol.exists() else model_names
    provenance=original.get('judgement_provenance',{});matrix=[];source_checks={}
    for sha,content in inventory['contents'].items():
        p=Path(content['file']);exists=p.is_file();matches=exists and hashlib.sha256(p.read_bytes()).hexdigest()==sha
        dimensions=None
        if matches:
            with Image.open(p) as image:dimensions=list(image.size)
        source_checks[sha]={'file_exists':exists,'sha256_matches':matches,'dimensions':dimensions,
            'dimensions_match':dimensions==[content['width'],content['height']]}
    for item in queue['items']:
        task=item['task_type'];result=deepcopy(results.get(item['id'],{}));sha=item['sha256'];content=inventory['contents'][sha]
        names=original_models if provenance.get(item['id'])=='original_job' else model_names
        result['models']=names
        if task=='watermark':analysis=aggregate_watermarks(result,item)
        elif task=='product_identity':analysis=aggregate_identity(result,declared_model,item)
        else:continue
        for reason in analysis['unresolved_items']:
            indices=[reason['model_index']] if isinstance(reason.get('model_index'),int) else list(range(len(result.get('results',[])))) or [None]
            for index in indices:
                row=result.get('results',[])[index] if isinstance(index,int) and index<len(result.get('results',[])) else {}
                required=('schema_version','coverage_complete','no_marks_detected','image_size','marks','unresolved_items') if task=='watermark' else ('schema_version','observations')
                missing_fields=[field for field in required if field not in row]
                if task=='watermark':
                    for j,mark in enumerate(row.get('marks',[]) if isinstance(row.get('marks'),list) else []):
                        if isinstance(mark,dict):missing_fields += [f'marks[{j}].{f}' for f in ('mark_id','bbox_xyxy','abstain','evidence_ids') if f not in mark]
                matrix.append({'source_sha256':sha,'business_positions':content['occurrence_ids'],'task_id':item['id'],'task_type':task,
                    'model_index':index,'model_name':names[index] if isinstance(index,int) and index<len(names) else None,'cross_model_reason':reason.get('model_index') is None,
                    'original_observation':{k:deepcopy(row.get(k)) for k in ('classification','decision','confidence','abstain','image_type','model','observed_model','color','observed_color','evidence_ids') if k in row},
                    'reason':deepcopy(reason),'trigger_consumer':'watermark_contract.aggregate_watermarks' if task=='watermark' else 'identity_contract.aggregate_identity',
                    'missing_fields':missing_fields,'fields_required_by':'watermark/v3' if task=='watermark' else 'product-identity/v3',
                    'baseline_first_return':baseline_trigger(task,result),'local_evidence':{'source':source_checks[sha],
                        'ocr_regions_recorded':bool(content.get('ocr')),'supplemental_views':[{'image_id':v.get('image_id'),'file_exists':Path(v['path']).is_file()} for v in item.get('extra_images',[])]},
                    'local_recheck':'format/field/binding diagnostics only; cannot create missing semantic observations',
                    'new_authorization_needed_for_new_inference':True,'historical_confidence_changed':False})
    generated=('required_pool_','main_count_1_to_6','main_exact_duplicates','sku_pool_reference_')
    checks=[r for r in original.get('global_checks',[]) if not r['rule'].startswith(generated)]
    checks.append({'rule':'offline_source_files_verified','verdict':'PASS' if all(r['sha256_matches'] and r['dimensions_match'] for r in source_checks.values()) else 'UNKNOWN'})
    report=assemble_report(product,inventory,results,checks,queue=queue)
    report.update(analysis_mode='OFFLINE_EXISTING_EVIDENCE_ONLY',source_judgements=str(result_path),new_model_requests=0,new_tokens=0,production_writes=0,
        historical_token_accounting=original.get('combined_token_accounting'),source_file_checks=source_checks)
    missing=[str(base/name) for base in (job,phase) for name in OPTIONAL if not (base/name).is_file()]
    after={str(p.relative_to(job)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob('*') if p.is_file()}
    if before!=after:raise ValueError('ORIGINAL_EVIDENCE_CHANGED_STOP_WRITING')
    output.mkdir(parents=True,exist_ok=True)
    write(output/'8788-unknown-reason-matrix.json',{'schema':'unknown-reason-matrix/v2','source_judgements':str(result_path),
        'source_file_sha256':hashlib.sha256(result_path.read_bytes()).hexdigest(),'rows':matrix,'missing_optional_inputs':missing,
        'evidence_files_unchanged':len(before),'new_model_requests':0,'new_tokens':0,'production_writes':0})
    write(output/'8788-audit-diagnostics-v2.json',report)
    lines=['# 8788审核本地诊断 v2','',
        '仅离线读取既有图像证据。真实模型请求0、新增模型Token 0、线上写入0；原始证据未改动。',
        '这是新契约对历史结果的兼容性诊断，不是一次新的真实审核，不用新Schema给历史结果补全字段。','',
        '| 业务位置 | 水印覆盖 | 水印复核 | 身份结论 | SKU包装 | 原因 |','|---|---|---|---|---|---|']
    for row in report['occurrences']:
        lines.append('| '+row['id']+' | '+row['coverage_status']+' | '+str((row['watermark_audit'] or {}).get('review_status'))+' | '+str(row['checks'].get('product_identity'))+' | '+row['checks'].get('sku_packaging','不适用')+' | '+', '.join(row['unknown_reason_codes'])+' |')
    lines+=['','每个mark的双模型观察、区域、置信度、证据ID及身份五维度详见同名JSON。旧root结果保留legacy观察和已确认finding，coverage不能标为COMPLETE。',
        '有店铺横幅的图片依然保留NON_COMPLIANT；小字或其他维度UNKNOWN不能覆盖它，也不能据此执行删除。',
        '未找到的可选文件逐项记录在8788-unknown-reason-matrix.json，不推定其内容。']
    (output/'8788-audit-diagnostics-v2.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    causes=['# 8788 UNKNOWN原因还原','',
        '已确认源码存在Prompt/Schema主要验证root，而全量消费者要求marks的契约错位。历史任务purpose另要求marks，因此实际输出有时带marks，不能把所有UNKNOWN解释成marks缺失。',
        '在5097横幅样本中实际已有marks；v1还因营销文字待定类别、局部置信度不足返回UNKNOWN。其他样本包括root弃权、低于0.90及BOX/MIXED冲突。',
        '矩阵中的baseline_first_return是原v1聚合器的首个返回条件；reason字段是新诊断契约指出的具体字段/区域问题。两者分开，不把新Schema缺项冒称历史模型违规。',
        '已识别局部事实保持原值，旧输出没有覆盖声明、像素区域或维度观察时不补成完整结果。','',
        '| 任务 | 原v1首个触发条件 | 原因 |','|---|---|---|']
    for item in queue['items']:
        if item['task_type'] not in {'watermark','product_identity'}:continue
        trigger=baseline_trigger(item['task_type'],results.get(item['id'],{}))
        causes.append('| '+item['id']+' | '+(trigger['branch'] if trigger else '该v1首判没有发现UNKNOWN条件')+' | '+(trigger['reason_code'] if trigger else '见完整逐维度检查')+' |')
    (output/'8788-unknown-root-cause.md').write_text('\n'.join(causes)+'\n',encoding='utf-8')
    return {'positions':len(report['occurrences']),'reason_rows':len(matrix),'evidence_files_unchanged':len(before),'new_model_requests':0,'new_tokens':0,'production_writes':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--declared-model',required=True)
    args=parser.parse_args();print(json.dumps(diagnose(args.job_dir,args.output,args.declared_model)))


if __name__=='__main__':main()
