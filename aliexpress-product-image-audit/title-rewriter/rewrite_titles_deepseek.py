"""Local-only DeepSeek title generation; first valid result wins, no site writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

from api_support import _open_model_request, parse_json_content
from model_config import load_config, require_enabled_model
PREFIX = {4: 'In Stock', 7: 'Hot Sale'}
SUFFIX = 'Action Figures Collection Gifts'

ROOT = Path(__file__).resolve().parent
SCHEMA = 'deepseek-title-rewrite/v1'
DEFAULT_MODEL = 'deepseek-v4.1-flash'
DEFAULT_BASE = 'http://127.0.0.1:8788/v1'


def make_messages(product, shop):
    if shop not in PREFIX:
        raise ValueError('UNKNOWN_SHOP: specify shop 4 or 7')
    if not isinstance(product.get('title'), str) or not product['title'].strip():
        raise ValueError('ORIGINAL_TITLE_MISSING')
    prompt = (ROOT / 'prompt.md').read_text(encoding='utf-8')
    data = {k: product[k] for k in ('title', 'titleEn', 'identityJson') if k in product}
    data['skus'] = [{k: row[k] for k in ('skuName', 'name', 'modelCode') if k in row}
                    for row in product.get('skus', []) if isinstance(row, dict)]
    data.update(shop=shop, shop_prefix=PREFIX[shop])
    return [{'role': 'system', 'content': prompt},
            {'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}]


def send_request(messages, *, base_url, model, api_key, timeout, max_tokens, reasoning_effort=None):
    require_enabled_model(model)
    body = {'model': model, 'messages': messages, 'temperature': 0,
            'max_tokens': max_tokens, 'response_format': {'type': 'json_object'}}
    if reasoning_effort is not None:
        body['reasoning_effort'] = reasoning_effort
    request = urllib.request.Request(base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'})
    with _open_model_request(request, timeout=timeout) as response:
        return json.load(response)


def parse_result(raw, shop):
    if (not isinstance(raw, dict) or not isinstance(raw.get('choices'), list)
            or not raw['choices'] or not isinstance(raw['choices'][0], dict)):
        raise ValueError('INVALID_COMPLETION_RESPONSE')
    choice = raw['choices'][0]
    if choice.get('finish_reason') != 'stop' or not isinstance(choice.get('message'), dict):
        raise ValueError('MODEL_OUTPUT_INCOMPLETE')
    result = parse_json_content(choice['message']['content'])
    if not isinstance(result, dict):
        raise ValueError('MODEL_OUTPUT_NOT_OBJECT')
    title = result.get('titleEn')
    if (not isinstance(title, str) or not title.strip() or len(title) > 120
            or title != title.strip() or '\n' in title or '\r' in title
            or not title.startswith(PREFIX[shop] + ' ') or not title.endswith(' ' + SUFFIX)):
        raise ValueError('INVALID_TITLE_FORMAT_OR_LENGTH')
    if re.search(r'\b(?:Megatron|Hasbro)\b', title, re.I):
        raise ValueError('FORBIDDEN_TITLE_WORD')
    warnings = result.get('warnings', [])
    model = result.get('modelCode')
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        raise ValueError('INVALID_WARNINGS')
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('INVALID_MODEL_CODE')
    return {'titleEn': title, 'modelCode': model, 'warnings': warnings}


def rewrite_one(product, shop, *, request, retries=2, retry_delay=1, messages=None):
    row = {'id': product.get('id', product.get('pid')), 'shop': shop,
           'original_title': product.get('title'), 'status': 'FAILED', 'attempts': 0,
           'usage': None, 'calls': []}
    try:
        messages = messages or make_messages(product, shop)
    except (ValueError, TypeError, KeyError) as exc:
        row['error'] = str(exc)
        return row
    for attempt in range(1, retries + 2):
        row['attempts'] = attempt
        call = {'attempt': attempt, 'usage': None}
        row['calls'].append(call)
        try:
            raw = request(messages)
            call['raw_response'] = raw
            call['usage'] = raw.get('usage') if isinstance(raw, dict) else None
            result = parse_result(raw, shop)
            call['status'] = 'SUCCEEDED'
            row.update(result, status='SUCCEEDED', usage=call['usage'])
            row.pop('error', None)
            return row
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            # Do not persist upstream error bodies, request headers or API keys.
            error = ('HTTP_' + str(exc.code)) if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            if isinstance(exc, ValueError):
                error = 'INVALID_MODEL_RESPONSE'
            call.update(status='FAILED', error=error)
            row['error'] = error
            permanent = isinstance(exc, urllib.error.HTTPError) and exc.code not in {408, 409, 425, 429} and exc.code < 500
            if permanent or attempt > retries:
                break
            time.sleep(min(retry_delay * 2 ** (attempt - 1), 30))
    return row


def _write_output(output, document):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(output)


def run_batch(products, output, *, request, shop=None, workers=4, retries=2,
              retry_delay=1, request_settings=None, progress=None):
    if workers < 1 or retries < 0 or retry_delay < 0:
        raise ValueError('workers >= 1, retries >= 0, retry_delay >= 0 required')
    if not isinstance(products, list) or any(not isinstance(p, dict) for p in products):
        raise ValueError('Input must contain a list of product objects')
    output = Path(output)
    previous = {}
    if output.exists():
        old = json.loads(output.read_text(encoding='utf-8-sig'))
        if old.get('schema') != SCHEMA:
            raise ValueError('Output exists but is not a title rewrite result file')
        previous = {row['fingerprint']: row for row in old['results']
                    if row and row.get('status') == 'SUCCEEDED'}
    document = {'schema': SCHEMA, 'request_settings': request_settings or {},
                'results': [None] * len(products)}
    groups = {}
    for index, product in enumerate(products):
        selected_shop = shop if shop is not None else product.get('shopId', product.get('shop'))
        try:
            selected_shop = int(selected_shop)
            messages = make_messages(product, selected_shop)
        except (ValueError, TypeError, KeyError) as exc:
            document['results'][index] = {'id': product.get('id', product.get('pid')),
                'status': 'FAILED', 'attempts': 0, 'error': str(exc), 'calls': [], 'usage': None}
            continue
        fingerprint = hashlib.sha256(json.dumps({'messages': messages,
            'settings': request_settings or {}}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if fingerprint in previous:
            document['results'][index] = dict(previous[fingerprint], id=product.get('id', product.get('pid')))
        else:
            group = groups.setdefault(fingerprint, {'product': product, 'shop': selected_shop,
                                                   'messages': messages, 'indices': []})
            group['indices'].append(index)
    _write_output(output, document)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(rewrite_one, group['product'], group['shop'], request=request,
                    retries=retries, retry_delay=retry_delay, messages=group['messages']): fingerprint
                   for fingerprint, group in groups.items()}
        for future in as_completed(futures):
            fingerprint = futures[future]
            row = dict(future.result(), fingerprint=fingerprint)
            for index in groups[fingerprint]['indices']:
                product = products[index]
                document['results'][index] = dict(row, id=product.get('id', product.get('pid')))
            _write_output(output, document)
            if progress:
                progress(row)
    return document


def load_products(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.jsonl':
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, dict):
        return data['products'] if 'products' in data else [data]
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description='DeepSeek 本地批量标题重写；结果增量保存，成功后不重复生成。')
    parser.add_argument('--input', required=True, help='商品 JSON / JSONL 文件')
    parser.add_argument('--output', required=True, help='结果 JSON；重跑时复用输入及配置未变的成功结果')
    parser.add_argument('--shop', type=int, choices=sorted(PREFIX), help='统一店铺；否则读取每件 shopId/shop')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--retries', type=int, default=2, help='失败后的额外重试次数，默认2')
    parser.add_argument('--retry-delay', type=float, default=1)
    parser.add_argument('--model-config', help='复用项目 model-gateway/v1 JSON 配置')
    parser.add_argument('--base-url', help='兼容 API 地址，含 /v1')
    parser.add_argument('--model', help='项目已启用的 DeepSeek 型号')
    parser.add_argument('--timeout', type=int, help='每次请求超时秒数，默认150')
    parser.add_argument('--max-tokens', type=int, help='最大输出 Token，默认4096')
    parser.add_argument('--api-key-env', default=None, help='密钥环境变量名；默认依次读取 DEEPSEEK_API_KEY、VLM_API_KEY')
    args = parser.parse_args(argv)
    try:
        config = load_config(args.model_config) if args.model_config else {}
        settings = {'base_url': (args.base_url or config.get('base_url') or os.environ.get('VLM_BASE') or DEFAULT_BASE).rstrip('/'),
                    'model': args.model or config.get('models', [DEFAULT_MODEL])[0],
                    'timeout': args.timeout if args.timeout is not None else config.get('timeout', 150),
                    'max_tokens': args.max_tokens if args.max_tokens is not None else config.get('max_output_tokens', 4096)}
        if config.get('reasoning_effort'):
            settings['reasoning_effort'] = config['reasoning_effort']
        require_enabled_model(settings['model'])
        if min(settings['timeout'], settings['max_tokens'], args.workers) < 1 or args.retries < 0 or args.retry_delay < 0:
            raise ValueError('Invalid timeout, max-tokens, workers or retries')
        if Path(args.input).resolve() == Path(args.output).resolve():
            raise ValueError('Input and output must be different files')
        key = os.environ.get(args.api_key_env) if args.api_key_env else (os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('VLM_API_KEY'))
        if not key:
            raise ValueError('请设置 DEEPSEEK_API_KEY 或 VLM_API_KEY 环境变量')
        request = partial(send_request, api_key=key, **settings)
        result = run_batch(load_products(args.input), args.output, request=request,
            shop=args.shop, workers=args.workers, retries=args.retries,
            retry_delay=args.retry_delay, request_settings=settings,
            progress=lambda row: print(f"{row['id']}: {row['status']} ({row['attempts']} attempts)", flush=True))
        succeeded = sum(row['status'] == 'SUCCEEDED' for row in result['results'])
        print(f"完成：{succeeded}/{len(result['results'])} 成功；结果：{Path(args.output).resolve()}")
        return 0 if succeeded == len(result['results']) else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f'{exc}\n')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
