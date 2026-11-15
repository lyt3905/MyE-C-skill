"""Isolated six-image acceptance preparation. Default is offline preflight.

No Site, Writer, recovery entrypoint, cache client, or remediation is imported.
The current gateway has no verified per-request total-token bound: real mode
fails closed. Enabling it requires implementing and testing a provider-backed
bound, and separate user authorization; there is deliberately no bypass flag.
"""
from policy_engine import MODEL_CONFIDENCE_MIN
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import io
import json
import os
from pathlib import Path
import subprocess
import uuid

from PIL import Image, ImageDraw
from ai_judge.client import COMMON_OUTPUT_CONTRACT, parse_json_content, prepare_image, safe_payload
from ai_judge.schemas import validate_result
from ai_judge.watermark_contract import aggregate_watermarks
from ai_judge.identity_contract import aggregate_identity
from model_config import load_config, fingerprint
from token_budget import (BudgetError, TokenLedger, DurableFakeBudget, provider_capability,
                          request_upper_bound, plan_budget)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT/'work/full-product-audit-20261114/jobs/JOB_93099438cf014a689846bc05469759ad'
DEFAULT_CONFIG = ROOT/'scripts/config/model.gateway8788.example.json'
SEAL = ROOT/'work/8788-contract-fix-20261114/evidence-before.json'
# New local release baseline; the original 8788 manifest and evidence remain sealed.
BASELINE = ROOT/'reports/sku-consensus-targeted-source-manifest.json'
EXPECTED = {
    '20583cfb87a9ac7e0ccf022650a3b262f88d4c9b33eea83e990982d2f8c13b82': ['MAIN_000', 'DETAIL_000'],
    'f58ef0242d0737a4aa4d8c4997e72842049679a391df89c3c6d9179f4264bed6': ['MAIN_001', 'DETAIL_001'],
    'e9a1233b0d4e4282e657d83b75d9f3cdf2636b30dd5591733ded7201b65e0bc7': ['MAIN_002', 'DETAIL_002'],
    '4292661510e41155463451b49d871611c08827bdb1b6dd0701a484eb4c05e8b7': ['MAIN_003', 'DETAIL_003', 'SKU_001', 'SKU_ROW_000'],
    'b001256f377830437d16b2f0b151cc6114d85ea7cdde5e697adf1d9f1c37b82e': ['MAIN_004', 'DETAIL_004'],
    '0fd90100f20a2edcdd286946646bce31346160d172810ddb5fe6a39ef87cc7a5': ['MAIN_005', 'DETAIL_005', 'SKU_000', 'SKU_ROW_001'],
}
ARTIFACTS = (
    '8788-real-validation-inputs.json', '8788-real-validation-preflight.md',
    '8788-real-validation-requests.jsonl', '8788-real-validation-usage.json',
    '8788-real-validation-watermark.json', '8788-real-validation-identity.json',
    '8788-real-validation-region-matches.json', '8788-real-validation-overlay',
    '8788-real-validation-report.md', '8788-real-validation-final-verification.json',
)


class Blocked(ValueError):
    pass


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode('utf-8')
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode('utf-8')).hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(Path(path).rglob('*')) if p.is_file()}


def verify_seal(source):
    seal = read(SEAL)
    if len(seal['files']) != 433 or Path(source).resolve() != Path(seal['root']).resolve() or tree(source) != seal['files']:
        raise Blocked('HISTORICAL_EVIDENCE_CHANGED')


def source_versions():
    files = [p for p in (ROOT/'scripts').rglob('*.py') if '__pycache__' not in p.parts]
    files += list((ROOT/'scripts/config').rglob('*.json'))
    modules = {task: import_module('ai_judge.'+task) for task in ('watermark', 'product_identity')}
    return dict(files={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)},
                contracts={task: dict(schema=module.SCHEMA_VERSION,
                                     prompt_sha256=hashlib.sha256(module.PROMPT.encode()).hexdigest())
                           for task, module in modules.items()},
                matching=read(ROOT/'scripts/config/watermark.matching.v3.json'),
                confidence_min=MODEL_CONFIDENCE_MIN, distinct_models=2, cache='DISABLED',
                cache_version_file_sha256=sha(ROOT/'scripts/ai_judge/cache.py'))


def baseline_check():
    baseline = read(BASELINE)
    mismatch = [p for p, value in baseline['source_after'].items()
                if not (ROOT/p).is_file() or sha(ROOT/p) != value['sha256']]
    if mismatch:
        raise Blocked('PREVIOUS_TEST_SOURCE_CHANGED:'+','.join(mismatch))
    return dict(test_run_id=baseline['run_id'], files_verified=len(baseline['source_after']),
                manifest_sha256=sha(BASELINE), mismatches=[])


def evidence_file(path, source, expected_sha=None):
    p = Path(path)
    if not p.is_absolute(): p = ROOT/p
    p = p.resolve()
    if Path(source).resolve() not in p.parents or not p.is_file():
        raise Blocked('SOURCE_FILE_OUTSIDE_SEALED_JOB_OR_MISSING')
    digest = sha(p)
    if expected_sha is not None and digest != expected_sha: raise Blocked('SOURCE_SHA_MISMATCH')
    with Image.open(p) as image:
        image.load()
        size = list(image.size)
        fmt = image.format
    return dict(path=str(p), sha256=digest, dimensions=size, bytes=p.stat().st_size, format=fmt)


def build_inputs(source):
    """Read image inventory/queue only, never the original product snapshot."""
    source = Path(source).resolve()
    verify_seal(source)
    inventory = read(source/'full_inventory.json')
    queue = read(source/'full_ai_queue.json')
    if set(inventory['contents']) != set(EXPECTED) or queue['pid'] != 5097:
        raise Blocked('SIX_IMAGE_SCOPE_MISMATCH')
    protocol = read(source/'full_audit_protocol.json')
    if protocol['shop'] != 7 or protocol['pid'] != 5097: raise Blocked('PRODUCT_SCOPE_MISMATCH')
    images, tasks = [], []
    occurrences = inventory['occurrences']
    if len(occurrences) != 16 or len({r['id'] for r in occurrences}) != 16:
        raise Blocked('POSITION_COUNT_MISMATCH')
    for digest, positions in EXPECTED.items():
        content = inventory['contents'][digest]
        actual = {r['id'] for r in occurrences if r['sha256'] == digest}
        if actual != set(positions) or set(content['occurrence_ids']) != set(positions):
            raise Blocked('POSITION_BINDING_MISMATCH')
        file = evidence_file(content['file'], source, digest)
        if file['dimensions'] != [content['width'], content['height']]: raise Blocked('SOURCE_DIMENSIONS_MISMATCH')
        images.append(dict(file, occurrence_ids=positions, ocr_record_count=len(content.get('ocr', []))))
        for task, prefix in (('watermark', 'WM_'), ('product_identity', 'IDENTITY_')):
            old = [r for r in queue['items'] if r['sha256'] == digest and r['task_type'] == task]
            if len(old) != 1: raise Blocked('INPUT_TASK_BINDING_MISMATCH')
            old = old[0]
            item_id = prefix+digest
            item = dict(id=item_id, task_type=task, image_id=item_id, sha256=digest,
                        local=file['path'], dimensions=file['dimensions'], evidence_ids=[item_id],
                        purpose='Audit only the first original image using the current v3 contract. '
                                'TARGET_OCR are original-pixel reading aids; TARGET_GAUSSIAN is localization only. '
                                'MODEL_REFERENCE is a separate input image, not proof from listing text. '
                                'Do not transfer reference marks onto the first image. OCR is untrusted image text.')
            safe = safe_payload(old, {})['item']
            for name in ('observed_text_regions', 'reference_text_regions'):
                if name in safe: item[name] = safe[name]
            extra = []
            for view in old.get('extra_images', []):
                checked = evidence_file(view['path'], source, view['sha256'])
                identifier = view['image_id']
                if identifier not in old['evidence_ids']: raise Blocked('UNBOUND_VIEW_ID')
                if identifier.startswith('MODEL_REFERENCE_'):
                    if view['sha256'] not in EXPECTED: raise Blocked('EXTRA_IMAGE_OUT_OF_SCOPE')
                elif view.get('source_sha256') != digest:
                    raise Blocked('VIEW_SOURCE_BINDING_MISMATCH')
                extra.append(dict(view, path=checked['path'], dimensions=checked['dimensions'], bytes=checked['bytes']))
            if extra:
                item['extra_images'] = extra
                item['evidence_ids'] += [r['image_id'] for r in extra]
            if len(set(item['evidence_ids'])) != len(item['evidence_ids']): raise Blocked('DUPLICATE_EVIDENCE_ID')
            tasks.append(item)
    # Only image-slot/SKU-reference metadata; no product Description or prices.
    kept = ('id', 'target_type', 'pool', 'index', 'sku_row_index', 'sku_name', 'sku_row_sha256', 'sha256', 'source_status')
    positions = [{k: row[k] for k in kept if k in row} for row in occurrences]
    return dict(schema='8788-validation-inputs/v1', shop=7, pid=5097, source_job=str(source),
                source_inventory_sha256=sha(source/'full_inventory.json'),
                source_queue_sha256=sha(source/'full_ai_queue.json'),
                source_seal_sha256=sha(SEAL), source_files=433, images=images, occurrences=positions,
                tasks=tasks, context=dict(pid=5097, shop=7, model='DW-ES09T', identityJson=dict(modelCode='DW-ES09T')),
                declared_model_provenance='Fixed audited DW-ES09T target; no product snapshot parsed',
                expected_requests=24, extra_sku_requests=0)


def verify_inputs(source, inputs):
    if inputs != build_inputs(source): raise Blocked('INPUT_MANIFEST_CHANGED')


def validate_output(output, source):
    output, source = Path(output).resolve(), Path(source).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise Blocked('OUTPUT_ISOLATION')
    # Refuse a nested path crossing a symlink/junction into the sealed source.
    return output


class HardBudget:
    """Legacy in-memory Fake API compatibility; not used for runner admission."""
    def __init__(self):
        self.requests = 0
        self.known_tokens = 0
        self.unknown = False
        self.stopped = None
        self.reservation = None

    def reserve(self, total_upper_bound):
        if self.stopped: raise Blocked(self.stopped)
        if self.reservation is not None: raise Blocked('CONCURRENT_REQUEST_FORBIDDEN')
        if self.requests >= 24: raise Blocked('REQUEST_LIMIT')
        if type(total_upper_bound) is not int or total_upper_bound <= 0: raise Blocked('TOKEN_CEILING_UNVERIFIED')
        if self.known_tokens + total_upper_bound > 300000: raise Blocked('TOKEN_LIMIT')
        self.reservation = total_upper_bound
        self.requests += 1

    def settle(self, usage):
        if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                or usage['prompt_tokens']+usage['completion_tokens'] != usage['total_tokens']):
            self.unknown = True; self.stopped = 'USAGE_UNKNOWN'
            raise Blocked(self.stopped)
        self.known_tokens += usage['total_tokens']
        if self.reservation is None or usage['total_tokens'] > self.reservation:
            self.stopped = 'PROVIDER_BOUND_BREACH'
        elif self.known_tokens > 300000: self.stopped = 'TOKEN_LIMIT'
        self.reservation = None
        if self.stopped: raise Blocked(self.stopped)

    def fail(self, reason):
        if self.reservation is not None: self.unknown = True
        self.stopped = self.stopped or reason

    def snapshot(self):
        return dict(requests=self.requests, known_total_tokens=self.known_tokens,
                    total_tokens=None if self.unknown else self.known_tokens,
                    usage_status='USAGE_UNKNOWN' if self.unknown else 'KNOWN',
                    pending_reservation=self.reservation, stop_reason=self.stopped,
                    max_provider_requests=24, max_total_tokens=300000)


def git_info():
    def command(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, encoding='utf-8').strip()
    return dict(root=command('rev-parse', '--show-toplevel'), branch=command('branch', '--show-current'),
                head=command('rev-parse', 'HEAD'), status=command('status', '--short', '--branch'))


def request_body(model, item, context, output_limit):
    """Reuse the repaired prompts and image encoding, without constructing JudgeClient."""
    prompt = import_module('ai_judge.'+item['task_type']).PROMPT
    text = prompt + COMMON_OUTPUT_CONTRACT + ' No write instructions. ' + json.dumps(safe_payload(item, context), ensure_ascii=False)
    content = [dict(type='text', text=text)]
    metadata = []
    for path, identifier, digest in [(item['local'], item['id'], item['sha256'])] + [
            (x['path'], x['image_id'], x['sha256']) for x in item.get('extra_images', [])]:
        sent, details = prepare_image(path)
        if details['original_sha256'] != digest: raise Blocked('SOURCE_SHA_MISMATCH')
        metadata.append(dict(details, evidence_id=identifier))
        content.append(dict(type='text', text=identifier))
        content.append(dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(sent).decode())))
    return dict(model=model, temperature=0, max_tokens=output_limit, response_format=dict(type='json_object'),
                messages=[dict(role='user', content=content)]), metadata


def _http_transport(config, model, item, context, *, body=None):
    """Single HTTP attempt; no redirects, retries or auth probes. Currently gated off."""
    raise Blocked("LEGACY_MODEL_ENTRY_DISABLED_USE_BOUND_WORKFLOW")
    import urllib.request
    key = os.environ.get('VLM_API_KEY')
    if not key: raise Blocked('LOCAL_CREDENTIAL_MISSING')
    if body is None:
        body, _ = request_body(model, item, context, config['max_output_tokens'])
    elif not isinstance(body,dict) or body.get('model')!=model:
        raise Blocked('PREPARED_REQUEST_MODEL_MISMATCH')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): raise Blocked('REDIRECT_FORBIDDEN')
    req = urllib.request.Request(config['base_url']+'/chat/completions',
                                 data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=config['timeout']) as res: return res.read()


def prepare(source, inputs, output, config_path):
    source = Path(source).resolve()
    output = validate_output(output, source)
    baseline = baseline_check()
    verify_inputs(source, inputs)
    config = load_config(config_path)
    if config['base_url'] != 'http://127.0.0.1:8788/v1' or config['models'] != ['deepseek-v4.1-flash', 'mimo-v2.6-pro'] or config['retries'] != 0:
        raise Blocked('MODEL_PROFILE_NOT_APPROVED')
    versions = source_versions()
    if versions['contracts']['watermark']['schema'] != 'watermark/v3' or versions['contracts']['product_identity']['schema'] != 'product-identity/v3' or versions['matching']['min_iou'] != .5:
        raise Blocked('CONTRACT_VERSION_MISMATCH')
    output.mkdir(parents=True, exist_ok=True)
    job = output/('VALIDATION_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex)
    job.mkdir(exist_ok=False)
    (job/'raw').mkdir(); (job/'normalized').mkdir(); (job/'8788-real-validation-overlay').mkdir()
    plan = []
    capabilities = {model: provider_capability(config['base_url'], model) for model in config['models']}
    for item in inputs['tasks']:
        for model in config['models']:
            body, encoded = request_body(model, item, inputs['context'], config['max_output_tokens'])
            proof = request_upper_bound(capabilities[model], image_count=len(encoded))
            plan.append(dict(item_id=item['id'], task_type=item['task_type'], sha256=item['sha256'],
                             model=model, body_sha256=canonical(body), body_bytes=len(json.dumps(body).encode()),
                             visual_inputs=encoded, verified_total_token_upper_bound=proof['request_upper_bound'],
                             token_budget_proof=proof))
    budget_plan = plan_budget([r['token_budget_proof'] for r in plan])
    ledger = TokenLedger.create(job/'token-budget.sqlite', job.name, mode='STRICT')
    write(job/'token-budget-plan.json', budget_plan)
    write(job/'provider-capabilities.json', capabilities)
    write(job/'8788-real-validation-inputs.json', inputs)
    write(job/'source-versions.json', versions)
    write(job/'model-profile.json', config)
    write(job/'request-plan.json', plan)
    old_path = source/'recovery_8788_1/combined_judgements.final2.json'
    historical = read(old_path)
    write(job/'historical-comparison.json', dict(
        source=str(old_path), source_sha256=sha(old_path), state='NO_NEW_REAL_RESULTS',
        tasks={item['id']: dict(sha256=item['sha256'], task_type=item['task_type'],
            original=historical.get(('WM_' if item['task_type']=='watermark' else 'IDENTITY_')+item['sha256'][:16]),
            new_real_result=None) for item in inputs['tasks']}))
    write(job/'preparation.json', dict(baseline=baseline, git=git_info(),
          config_path=str(Path(config_path).resolve()), model_config_sha256=fingerprint(config),
          inputs_sha256=canonical(inputs), versions_sha256=canonical(versions),
          request_plan_sha256=canonical(plan), local_model_ids_verified=True,
          provider_resolved_versions_verified=False, authorization='NOT_GRANTED',
          prohibited=['site_operations', 'recovery', 'remediation', 'extra_sku_tasks']))
    (job/'8788-real-validation-requests.jsonl').touch(exist_ok=False)
    write(job/'8788-real-validation-usage.json', dict(ledger.snapshot(), actual_provider_requests=0, new_model_tokens=0))
    blockers = sorted({'TOKEN_CEILING_UNVERIFIED'} | {b for r in budget_plan['requests'] for b in r['blockers']})
    preflight = '\n'.join([
        '# 8788真实模型验收预检', '', '**PREFLIGHT_BLOCKED**', '',
        '六份完整SHA256、尺寸、辅助证据及16个位置绑定已通过；新Job独立保存，旧433个文件未改。',
        '上一轮253个源码/测试/配置文件逐字节匹配。新Runner源码另行封存，不冒称经过旧567项验证。',
        '配置：http://127.0.0.1:8788/v1；deepseek-v4.1-flash / mimo-v2.6-pro；retries=0。',
        '只核实本地配置ID，未访问网关，供应商实际解析版本仍待真实响应核对。',
        '计划24次：6图 × watermark/product_identity × 2模型；额外SKU请求0。',
        '硬限制：请求上限24；Token上限300000；未知用量/超时/格式错误立即停，失败计数，禁止重试。',
        '', '## 阻断原因', '',
        'TOKEN_CEILING_UNVERIFIED：现有8788配置只有max_output_tokens=8192，它不限制输入Token。',
        '未找到可核实的供应商输入Token上界或服务端单请求总Token硬限制。',
        '事后累计检查无法防止最后一次请求超额；本Runner禁止在没有可信单请求上界时发送请求。',
        '不使用历史均值、字符数或图片尺寸猜测硬上界，也不提供绕过开关。',
        '需要先完成提供方预算能力验证/适配及Fake测试，再单独授权24次/最多300000Token；仅聊天授权不能消除此阻断。',
        '实际路径为WorkBuddy2API-Hub转发；原厂文档的计量保证不能直接套用。网关存在估算usage回填路径，来源未经证明时不认可为实际用量。',
        '24次最坏情况总Token：UNKNOWN；TOKEN_CAP_PROVEN=false，SPEND_CAP_PROVEN=false。详见token-budget-plan.json。',
        '权威账本token-budget.sqlite采用SQLite FULL同步事务；新Job请求数0、已用0、预留0；不存在复用旧账本。',
        '', '## 本轮计数', '', '真实模型请求0；新增Token 0；线上写入0；自动整改0。',
        '本轮未运行真实模式。真实语义、bbox准确度、置信度校准、视觉验收及准确率均未验证。',
    ])+'\n'
    (job/'8788-real-validation-preflight.md').write_text(preflight, encoding='utf-8')
    (job/'8788-real-validation-overlay/index.md').write_text('NOT_RUN：尚无真实模型区域；不得将空区域视为无水印。\n', encoding='utf-8')
    finish(job, inputs, {}, {}, ledger, 'PREFLIGHT_BLOCKED', blockers, fake=False)
    return job


def overlay(job, item, rows, analysis, fake):
    with Image.open(item['local']) as source: original = source.convert('RGB')
    panels = [original.copy() for _ in range(4)]
    for index, row in enumerate(rows):
        draw = ImageDraw.Draw(panels[index+1])
        for mark in row.get('marks', []):
            draw.rectangle(mark['bbox_xyxy'], outline='red' if index == 0 else 'blue', width=3)
            draw.text(tuple(mark['bbox_xyxy'][:2]), mark['mark_id'], fill='yellow')
    draw = ImageDraw.Draw(panels[3])
    for region in analysis.get('regions', []):
        color = {'PASS': 'green', 'FAIL': 'red'}.get(region.get('status'), 'orange')
        for observation in (region.get('model_a_observation'), region.get('model_b_observation')):
            if isinstance(observation, dict) and observation.get('bbox_xyxy'):
                draw.rectangle(observation['bbox_xyxy'], outline=color, width=2)
    for unresolved in analysis.get('unresolved_items', []):
        if unresolved.get('bbox_xyxy'):
            draw.rectangle(unresolved['bbox_xyxy'], outline='orange', width=2)
    width, height = original.size
    sheet = Image.new('RGB', (width*2, (height+30)*2), 'white')
    titles = ['ORIGINAL', 'MODEL A', 'MODEL B', 'REGIONS: RED finding / GREEN protected / ORANGE unresolved']
    for index, panel in enumerate(panels):
        x, y = index%2*width, index//2*(height+30)
        sheet.paste(panel, (x, y+30)); ImageDraw.Draw(sheet).text((x+5, y+5), ('FAKE ' if fake else '')+titles[index], fill='black')
    sheet.save(job/'8788-real-validation-overlay'/(item['sha256']+'.png'))


def finish(job, inputs, results, errors, budget, state, blockers, fake):
    watermark, identity, matches = {}, {}, {}
    for item in inputs['tasks']:
        rows = results.get(item['id'], [])
        paired = dict(results=[r['result'] for r in rows], models=[r['model'] for r in rows])
        if not rows: continue
        if item['task_type'] == 'watermark':
            analysis = aggregate_watermarks(paired, item)
            watermark[item['sha256']] = analysis
            matches[item['sha256']] = dict(regions=analysis['regions'], unresolved_items=analysis['unresolved_items'],
                                           confirmed_findings=analysis['confirmed_findings'])
            overlay(job, item, paired['results'], analysis, fake)
        else: identity[item['sha256']] = aggregate_identity(paired, 'DW-ES09T', item)
    for name, values in (('watermark', watermark), ('identity', identity), ('region-matches', matches)):
        positions = [dict(position, analysis=values.get(position['sha256']),
                          state='AVAILABLE' if position['sha256'] in values else 'NOT_RUN') for position in inputs['occurrences']]
        write(job/('8788-real-validation-'+name+'.json'), dict(mode='FAKE' if fake else 'PREFLIGHT', by_sha256=values, positions=positions))
    evidence_unchanged = True
    try: verify_seal(Path(inputs['source_job']))
    except Blocked:
        evidence_unchanged = False
        blockers = list(blockers)+['HISTORICAL_EVIDENCE_CHANGED']
    usage = dict(budget.snapshot(), actual_provider_requests=0, simulated_requests=budget.requests if fake else 0,
                 new_model_tokens=0, mode='FAKE' if fake else 'PREFLIGHT')
    write(job/'8788-real-validation-usage.json', usage)
    verification = dict(state=state, blockers=blockers, actual_provider_requests=0,
          simulated_requests=budget.requests if fake else 0, new_model_tokens=0, online_writes=0,
          automatic_remediations=0, source_evidence_unchanged=evidence_unchanged,
          real_execution_authorized=False, structural_real_acceptance='NOT_RUN',
          semantic_accuracy='NOT_MEASURED_NO_INDEPENDENT_GROUND_TRUTH',
          bbox_visual_review='NOT_REVIEWED', errors=errors)
    write(job/'8788-real-validation-final-verification.json', verification)
    config = read(job/'model-profile.json')
    lines = ['# 8788独立验收报告', '', state, '',
             '真实请求0 / 新增模型Token 0 / 线上写入0 / 自动整改0。',
             '模拟请求：'+str(usage['simulated_requests'])+'；模拟结果不得用作真实模型验收。',
             '配置模型：'+', '.join(config['models'])+'；供应商实际版本未调用验证。',
             '停止/阻断原因：'+', '.join(blockers or ([budget.stopped] if budget.stopped else [])),
             '旧证据433个文件未变：'+str(evidence_unchanged), '',
             '结构性真实验收、双模型真实一致性、bbox人工可视化检查、语义归属：NOT_RUN。',
             '没有独立可信真值集，准确率不可计算。历史结论保留，尚无真实新结果可比较。', '',
             '| 完整SHA256 | 业务位置 | 水印 | 身份 |', '|---|---|---|---|']
    for image in inputs['images']:
        digest = image['sha256']
        lines.append('| '+digest+' | '+', '.join(image['occurrence_ids'])+' | '+
                     ('FAKE_ONLY' if digest in watermark else 'NOT_RUN')+' | '+('FAKE_ONLY' if digest in identity else 'NOT_RUN')+' |')
    lines += ['', '逐请求用量见requests.jsonl/usage.json；原始响应在raw；规范化结果在normalized。',
              '逐mark匹配、未匹配/歧义/UNKNOWN及五维观察见对应JSON；overlay仅为对照材料，不修改商品图。',
              '本地封存快照仅证明历史输入一致；未访问站点，因此不声称线上SKU现状仍一致。']
    (job/'8788-real-validation-report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return verification


def run_fake(job, transport, *, per_request_ceiling):
    """Explicit injected Fake-only runner; the CLI never calls it in real mode."""
    job = validate_output(job, DEFAULT_SOURCE)
    try:
        with (job/'execution-started.json').open('x', encoding='utf-8') as handle:
            json.dump(dict(mode='FAKE', authorization='NONE', actual_provider_requests=0), handle)
    except FileExistsError:
        raise Blocked('JOB_ALREADY_STARTED') from None
    return _run(job, transport, per_request_ceiling)


def _run(job, transport, ceiling):
    inputs, config = read(job/'8788-real-validation-inputs.json'), read(job/'model-profile.json')
    prep = read(job/'preparation.json')
    results, errors = {}, {}
    budget = DurableFakeBudget(job/'token-budget.fake.sqlite', job.name)
    state = 'FAKE_COMPLETED'
    def journal(row):
        with (job/'8788-real-validation-requests.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())
    try:
        for item in inputs['tasks']:
            for model in config['models']:
                verify_seal(Path(inputs['source_job']))
                if canonical(source_versions()) != prep['versions_sha256']: raise Blocked('SOURCE_VERSION_CHANGED')
                if canonical(inputs) != prep['inputs_sha256'] or fingerprint(config) != prep['model_config_sha256']:
                    raise Blocked('JOB_INPUT_OR_PROFILE_CHANGED')
                # This explicit Fake path supplies synthetic bounds only. The
                # STRICT ledger cannot admit this number as provider proof.
                meta = dict(provider='FAKE', model_id=model, task_type=item['task_type'],
                    image_sha256=item['sha256'], prompt_version=source_versions()['contracts'][item['task_type']]['prompt_sha256'],
                    schema_version=source_versions()['contracts'][item['task_type']]['schema'],
                    request_body_sha256=read(job/'request-plan.json')[(budget.requests)]['body_sha256'],
                    input_text_upper_bound=None, image_input_upper_bound=None, other_input_upper_bound=None,
                    output_token_hard_limit=None, provider_overhead_upper_bound=None,
                    upper_bound_status='FAKE_SYNTHETIC_TOTAL_BOUND', proof_source='Fake test fixture; never provider evidence')
                budget.reserve(ceiling, meta)
                key = f'{budget.requests:02d}'
                event = dict(request=budget.requests, item_id=item['id'], task_type=item['task_type'],
                             model=model, status='RESERVED', mode='FAKE', total_token_upper_bound=ceiling)
                journal(event); write(job/'8788-real-validation-usage.json', budget.snapshot())
                provider_usage = None
                try:
                    budget.mark_sent()
                    raw = transport(model, deepcopy(item), deepcopy(inputs['context']))
                    if isinstance(raw, bytes):
                        (job/'raw'/(key+'.bin')).write_bytes(raw)
                        raw = json.loads(raw)
                    else: write(job/'raw'/(key+'.json'), raw)
                    provider_usage = raw.get('usage')
                    budget.settle(provider_usage)
                    if raw.get('model') != model: raise Blocked('ACTUAL_MODEL_ID_CHANGED')
                    normalized = validate_result(parse_json_content(raw['choices'][0]['message']['content']),
                                                 item['task_type'], item['id'], item, allow_legacy=False)
                    write(job/'normalized'/(key+'.json'), dict(model=model, result=normalized, usage=raw['usage']))
                    results.setdefault(item['id'], []).append(dict(model=model, result=normalized))
                    journal(dict(event, status='SUCCESS', provider_usage=provider_usage, usage=raw['usage']))
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, (Blocked, BudgetError)) else ('TIMEOUT' if isinstance(exc, TimeoutError) else 'SCHEMA_OR_TRANSPORT_ERROR')
                    budget.fail(reason); errors[key] = dict(reason_code=reason, exception_type=type(exc).__name__)
                    journal(dict(event, status='STOPPED', error=errors[key], provider_usage=provider_usage, usage=budget.snapshot()))
                    raise Blocked(reason) from None
                write(job/'8788-real-validation-usage.json', budget.snapshot())
    except (Blocked, BudgetError) as exc:
        state = 'FAKE_STOPPED'; budget.fail(str(exc))
    return finish(job, inputs, results, errors, budget, state, [budget.stopped] if budget.stopped else [], True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-job-dir', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--input-manifest', type=Path, default=ROOT/'reports/8788-real-validation-inputs.json')
    p.add_argument('--output-dir', type=Path, default=ROOT/'work/8788-real-validation-20261114')
    p.add_argument('--model-config', type=Path, default=DEFAULT_CONFIG)
    p.add_argument('--max-provider-requests', type=int, choices=[24], default=24)
    p.add_argument('--max-total-tokens', type=int, choices=[300000], default=300000)
    p.add_argument('--no-retry', action='store_true', default=True)
    p.add_argument('--no-site-write', action='store_true', default=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--preflight-only', action='store_true')
    mode.add_argument('--execute-real-models', action='store_true')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        inputs = build_inputs(args.source_job_dir)
        validate_output(args.input_manifest.parent, args.source_job_dir)
        if args.input_manifest.exists(): verify_inputs(args.source_job_dir, read(args.input_manifest))
        else:
            args.input_manifest.parent.mkdir(parents=True, exist_ok=True)
            write(args.input_manifest, inputs)
        job = prepare(args.source_job_dir, inputs, args.output_dir, args.model_config)
        if args.execute_real_models:
            # No authorization from this task; no locally verifiable provider
            # total-token ceiling. Never call _http_transport from this path.
            print(json.dumps(dict(state='PREFLIGHT_BLOCKED', job=str(job),
                blockers=['TOKEN_CEILING_UNVERIFIED', 'SEPARATE_USER_AUTHORIZATION_REQUIRED'])))
            return 2
        print(json.dumps(dict(state='PREFLIGHT_BLOCKED', job=str(job), actual_provider_requests=0,
                              new_model_tokens=0, online_writes=0)))
        return 2
    except (Blocked, OSError, ValueError, KeyError) as exc:
        print(json.dumps(dict(state='PREFLIGHT_BLOCKED', reason=str(exc) if isinstance(exc, Blocked) else type(exc).__name__,
                              actual_provider_requests=0, new_model_tokens=0, online_writes=0)))
        return 2


if __name__ == '__main__': raise SystemExit(main())
