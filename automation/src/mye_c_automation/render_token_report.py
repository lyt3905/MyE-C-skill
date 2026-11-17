# -*- coding: utf-8 -*-
"""Render a compact, deterministic 25–40 line token-opt-v1 product report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

WORKFLOW_VERSION = "token-opt-v1"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _budget_status(metrics: dict[str, Any]) -> str:
    budget = metrics.get("budget", {})
    unknown = False
    for name in ("full_resolution_views", "temporary_scripts", "model_requests"):
        row = budget.get(name, {})
        value = row.get("value")
        limit = row.get("limit", row.get("target_max"))
        if value is None or limit is None:
            unknown = True
        elif value > limit:
            return "WARN"
    return "UNKNOWN" if unknown else "PASS"


def render(workdir: Path, pid: int) -> str:
    metrics_v2=_load(workdir / "run_metrics.json")
    if metrics_v2.get('schema') == 'token-opt-metrics/v2':
        review=_load(workdir/'review.json')
        state=_load(workdir/'state.json').get('state',review.get('status','UNKNOWN'))
        receipt=_load(workdir/'apply_receipt.json') or _load(workdir/'executor_receipt.json')
        return '\n'.join([f'# 商品 {pid} 审核报告', '- 流程：token-opt-v2', '- 结论：'+state,
            '- 原因：'+review.get('reason',''), '- 商品写入：'+str(receipt.get('site_save_calls',0)),
            '- content_review_status: '+receipt.get('content_review_status','NOT_VERIFIED'),
            '- AI 请求：'+str(metrics_v2['ai'].get('requests')), '- AI 缓存命中：'+str(metrics_v2['ai'].get('cache_hits')),
            '- Token状态：'+str(metrics_v2.get('budget',{}).get('token_status','UNKNOWN')),
            '- 实际 Token：'+str(metrics_v2.get('budget',{}).get('actual_tokens',metrics_v2['ai'].get('total_tokens'))),
            '- usage 可用：'+str(metrics_v2['ai'].get('usage_available')),
            '- 预算：'+str(metrics_v2.get('budget')), '- 耗时毫秒：'+str(metrics_v2.get('timing')),
            '- 未测量指标保留 null；不能据此宣称性能或质量验收完成。'])+'\n'
    flags = _load(workdir / "audit_flags.json")
    plan = _load(workdir / "plan.v1.json")
    metrics = _load(workdir / "run_metrics.json")
    receipt_candidate = _load(workdir / "apply_receipt.json")
    before = _load(workdir / "product_before.json")
    after_candidate = _load(workdir / "product_after.json")
    summary = flags.get("summary", {})
    counts = summary.get("counts", {})
    actions = plan.get("review", {}).get("actions", [])
    executor = metrics.get('executor', {})
    applied_this_run = (
        executor.get("mode") == "apply"
        and receipt_candidate.get("schema") == "token-opt-apply-receipt/v1"
        and receipt_candidate.get("workflow_version") == WORKFLOW_VERSION
        and receipt_candidate.get("pid") == pid
    )
    receipt = receipt_candidate if applied_this_run else {}
    after = after_candidate if applied_this_run else {}
    status_before, status_after = before.get("status"), after.get("status", before.get("status"))
    budget_status = _budget_status(metrics) if metrics.get("workflow_version") == WORKFLOW_VERSION else "MISSING"
    lines = [
        f"# 商品 {pid} 审核报告",
        f"- 流程版本：{WORKFLOW_VERSION}",
        f"- 结论：{'已写回并通过回读' if receipt.get('ok') else '只读审计/dry-run，未写回'}",
        f"- 模式：{summary.get('suggested_mode', 'unknown')}",
        f"- 预算状态：{budget_status}",
        f"- 状态：{status_before} → {status_after}",
        "## 图片",
        f"- 图池：main {counts.get('main')} / detail {counts.get('detail')} / sku {counts.get('sku')}",
        f"- OCR 命中：{summary.get('ocr_hit_count', 0)}",
        f"- 重复对：{summary.get('duplicate_pair_count', 0)}",
        f"- 边框候选：{summary.get('border_candidate_count', 0)}",
        f"- 残差候选：{summary.get('residual_candidate_count', 0)}",
        f"- 异常动作：{len(actions)}",
    ]
    for row in actions[:2]:
        lines.append(f"- {row.get('kind', 'ACTION')} {row.get('slot', '')}：{row.get('reason', '见结构化计划')}")
    lines.extend([
        "## 标题 / 编号 / 品牌",
        f"- titleEn：{before.get('titleEn')} → {after.get('titleEn', before.get('titleEn'))}",
        f"- brand：{before.get('brand')} → {after.get('brand', before.get('brand'))}",
        f"- identityJson：{before.get('identityJson')} → {after.get('identityJson', before.get('identityJson'))}",
        "- 原始 title：保持不动（以回读结果为准）",
        "- 中文回译：仅在计划声明 translate_title 时触发",
        "## 写回与复检",
        f"- Site.save / status：{executor.get('site_save_calls', 0)} / {executor.get('status_calls', 0)} 次",
        f"- 上传 / 翻译：{executor.get('upload_calls', 0)} / {executor.get('translate_calls', 0)} 次",
        f"- 回读校验：{'PASS' if receipt.get('ok') else ('不适用（dry-run）' if executor.get('mode') == 'dry_run' else '未执行或未通过')}",
        f"- 校验错误：{'; '.join(receipt.get('verification_errors', [])) or '无'}",
        f"- weight：{before.get('weight')} → {after.get('weight', before.get('weight'))}",
        f"- price：{before.get('price')} → {after.get('price', before.get('price'))}",
        "- logoCode：由严格计划保护，禁止变化",
        "## 资源指标",
        f"- 图片出现/唯一内容：{metrics.get('image_occurrences')} / {metrics.get('unique_content_digests')}",
        f"- 下载缓存命中/联网：{metrics.get('downloads', {}).get('cache_hits')} / {metrics.get('downloads', {}).get('network_fetches')}",
        f"- 证据缓存命中/未命中：{metrics.get('evidence', {}).get('cache_hits')} / {metrics.get('evidence', {}).get('cache_misses')}",
        f"- OCR 执行/复用：{metrics.get('ocr', {}).get('image_executions')} / {metrics.get('ocr', {}).get('cache_reuses')}",
        f"- 原图查看：{metrics.get('budget', {}).get('full_resolution_views', {}).get('value')} / 12",
        f"- 临时脚本：{metrics.get('budget', {}).get('temporary_scripts', {}).get('value')} / 1",
        f"- 模型请求：{metrics.get('budget', {}).get('model_requests', {}).get('value')} / 45（外部会话账本）",
        "## 遗留与回滚",
        "- 遗留：以 audit_flags.json 未裁定项为准；不确定项不得写成已通过。",
        "- 回滚：product_before.json 仅作人工回滚依据，程序不会自动回滚。",
    ])
    return "\n".join(lines[:40]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--workdir")
    args = parser.parse_args()
    workdir = Path(args.workdir) if args.workdir else __import__('mye_c_automation.paths',fromlist=['data_root']).data_root() / "jobs" / f"pp_{args.pid}"
    output = workdir / f"报告_{args.pid}.md"
    output.write_text(render(workdir, args.pid), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
