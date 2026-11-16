"""Stable JSON interface; execution delegates to the one migrated V2 runner."""
import argparse
import json
import os
from pathlib import Path

def main(argv=None):
    parser=argparse.ArgumentParser(prog='myec-automation',description='Independent V2 image automation')
    sub=parser.add_subparsers(dest='command',required=True)
    doctor=sub.add_parser('doctor',help='Check installed resources and local image modules without network')
    doctor.add_argument('--config-dir',type=Path,help='Also validate local configuration without connecting')
    configure=sub.add_parser('configure',help='Initialize or validate local configuration without network')
    config_ops=configure.add_subparsers(dest='operation',required=True)
    init=config_ops.add_parser('init',help='Create missing configuration files; preserve existing files')
    init.add_argument('--directory',type=Path)
    check=config_ops.add_parser('check',help='Report missing configuration and optional future audit command')
    check.add_argument('--directory',type=Path);check.add_argument('--shop',type=int);check.add_argument('--pid',type=int)
    models=sub.add_parser('models',help='Install explicitly supplied local weights without inference')
    model_ops=models.add_subparsers(dest='operation',required=True)
    install=model_ops.add_parser('install-lama')
    install.add_argument('--source',type=Path,required=True);install.add_argument('--destination',type=Path,required=True)
    install.add_argument('--sha256',required=True);install.add_argument('--bind-config',type=Path)
    deploy=sub.add_parser('deploy',help='Generate a local deployment review; no service activation')
    deploy_ops=deploy.add_subparsers(dest='operation',required=True)
    review=deploy_ops.add_parser('review');review.add_argument('--install-root',type=Path,required=True);review.add_argument('--output',type=Path,required=True)
    fake=sub.add_parser('fake',help='Run full V2 with synthetic images, Mock DeepSeek and Fake persistence')
    fake.add_argument('--scenario',choices=['twin','frame','repair','keep'],default='twin')
    fake.add_argument('--data-root',type=Path)
    status=sub.add_parser('status',help='Read a Job and its structured result')
    status.add_argument('job_id');status.add_argument('--data-root',type=Path)
    results=sub.add_parser('results',help='Show final image JSON only; raw responses remain in audit evidence')
    results.add_argument('job_id');results.add_argument('--root',type=Path)
    cache=sub.add_parser('cache-images',help='Seed success cache from verified Job image evidence; no network or Job edits')
    cache.add_argument('job_id');cache.add_argument('--root',type=Path,required=True)
    cache.add_argument('--cache-root',type=Path)
    process=sub.add_parser('process',help='Run configured V2 audit, safe remediation, save and independent readback from one product URL')
    process.add_argument('url');process.add_argument('--config-dir',type=Path);process.add_argument('--data-root',type=Path)
    process.add_argument('--shop',type=int);process.add_argument('--audit-only',action='store_true')
    process.add_argument('--resume',help='Continue this process Job; never repeat an unknown save')
    workflow=sub.add_parser('workflow',help='Existing authorized V2 workflow CLI (arguments after --)')
    workflow.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args(argv)
    try:
        if args.command=='process':
            from mye_c_automation.one_command import process_product
            result=process_product(args.url,config_dir=args.config_dir,data_dir=args.data_root,shop=args.shop,audit_only=args.audit_only,resume=args.resume)
        elif args.command=='doctor':
            import cv2
            from mye_c_automation.resources import resource_path
            from mye_c_automation.ai_judge.image_action_decision import PROMPT,CONFIDENCE_POLICY
            from mye_c_automation import __version__
            result=dict(status='OK',version=__version__,sift=hasattr(cv2,'SIFT_create'),confidence_policy=CONFIDENCE_POLICY,
                prompt_loaded=bool(PROMPT),schema=str(resource_path('config/schemas/image-action-decision.v2.schema.json')),network_calls=0)
            if args.config_dir:
                from mye_c_automation.configuration import check_configuration
                result['configuration']=check_configuration(args.config_dir)
                if not result['configuration']['ready_for_readonly']:result['status']='NEEDS_CONFIGURATION'
        elif args.command=='configure':
            from mye_c_automation.configuration import initialize_config,check_configuration
            result=initialize_config(args.directory) if args.operation=='init' else check_configuration(args.directory,shop=args.shop,pid=args.pid)
        elif args.command=='models':
            from mye_c_automation.model_resources import install_lama
            result=install_lama(args.source,args.destination,args.sha256)
            if args.bind_config:
                from mye_c_automation.configuration import bind_lama
                result['configuration']=bind_lama(args.bind_config,args.destination,args.sha256)
        elif args.command=='deploy':
            from mye_c_automation.deployment_review import build_review
            result=build_review(args.install_root,args.output)
        elif args.command=='fake':
            from mye_c_automation.paths import initialize_data
            root=initialize_data(args.data_root);os.environ['MYEC_DATA_ROOT']=str(root)
            from mye_c_automation.fake import run_fake
            result=run_fake(root,args.scenario)
        elif args.command=='status':
            from mye_c_automation.job_manager import JobManager
            from mye_c_automation.paths import data_root
            manager=JobManager(data_root(args.data_root)/'jobs');job=manager.load(args.job_id);path=manager.directory(args.job_id)
            result=dict(job=job,state=json.loads((path/'state.json').read_text(encoding='utf-8')),
                result=json.loads((path/'automatic_result.json').read_text(encoding='utf-8')) if (path/'automatic_result.json').exists() else None)
        elif args.command=='cache-images':
            from mye_c_automation.job_manager import JobManager
            from mye_c_automation.download_manager import seed_image_cache
            manager=JobManager(args.root);manager.load(args.job_id)
            result=seed_image_cache(manager.directory(args.job_id),args.cache_root or args.root/'image-download-cache')
        elif args.command=='results':
            from mye_c_automation.job_manager import JobManager
            from mye_c_automation.paths import data_root
            manager=JobManager(args.root or data_root()/'jobs');job=manager.load(args.job_id)
            path=manager.directory(args.job_id)
            judgements=json.loads((path/'full_ai_judgements.json').read_text(encoding='utf-8'))
            result=dict(job_id=job['job_id'],pid=job['pid'],shop=job['shop_id'],items=[dict(image_sha256=digest,
                decision=row['decision'],final_json=next((value for value in row.get('results',[]) if isinstance(value,dict) and 'decision' in value),None),
                policy_adjustments=row.get('policy_adjustments',[]),reason_codes=row.get('reason_codes',[])) for digest,row in judgements.items()])
        else:
            from mye_c_automation.workflow_runner import main as run
            return run(args.arguments[1:] if args.arguments[:1]==['--'] else args.arguments) or 0
        print(json.dumps(result,ensure_ascii=False))
        if args.command=='process':
            if result.get('technical_status') in {'APPLY_UNKNOWN','RESERVED','TRANSLATION_PENDING'}:return 3
            if result.get('status') in {'ERROR','FAILED'}:return 2
        return 2 if result.get('status')=='NEEDS_CONFIGURATION' else 0
    except (ValueError,OSError) as exc:
        print(json.dumps(dict(status='ERROR',error=type(exc).__name__,message=str(exc))))
        return 2
