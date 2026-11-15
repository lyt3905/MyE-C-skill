# 集成缺口与验收映射

2026-11-14；HEAD 20ecfe8；对照 a14669b；最终Fake结果以 automation-system-tests-status.json 为准。

| 能力 | 原缺口/本轮改动 | IMPLEMENTED | FAKE_VERIFIED | REAL_VERIFIED | PRODUCTION_READY |
|---|---|---|---|---|---|
| 完整审核→自动计划 | 默认run自动阶段同Job调用full audit，逐位置投影，原响应不改 | YES | 最终日志 | 本轮NO | NO |
| 完整证据绑定 | Job/Shop/PID/商品state/图片SHA/覆盖/Prompt+Schema，缺失不退候选队列 | YES | bridge测试 | NO | NO |
| 未知项保留 | UNKNOWN/全局未决/缺SKU ID显式WEB_DEFER；阻止相关SKU_ASSIGN | YES | bridge及SKU回归 | NO | NO |
| 模型预算 | 扩展原BudgetManager账本，所有正式JudgeClient真实发送必须预留 | YES | budget测试 | NO | NO |
| STRICT | 原token_budget未改，当前Provider仍PREFLIGHT_BLOCKED | YES | 原34测试 | NO | NO |
| CONTROLLED_CANARY | 新Job绑定请求/商品/图数/输出/Token软预留/USD/路由/单在途/0重试 | YES | budget测试 | NO（disabled） | NO |
| 未知与故障 | 不释放未知预留，usage/cost来源、重启悬挂/磁盘错误/账本篡改阻断 | YES | budget测试 | NO | NO |
| 辅助质量审核 | VisualQualityInspector同Job budget.sqlite，共用底层guard | 复用 | 旧质量+profile测试 | NO | NO |
| 旧模型直连 | vlmcheck.call、历史_http_transport关闭；不得绕过新预算 | YES（关闭） | 直接入口拒绝测试 | NO | NO |
| Description | 移除旧标题解析例外，固定字段精确比较；无正文/URL审核 | YES | opaque及收紧的旧测试 | 本轮NO | NO |
| 保存/恢复/幂等 | 复用LocalExecutor/SiteWriter/ExecutionLedger/account_lock | 既有 | 全量旧回归 | 仅5093旧版本单图 | NO |
| 统一Job报告 | 完整审核状态/原始证据链接、计划/质量/执行/回读、模型预算归档 | YES | bridge/report回归 | NO | NO |

每个旧功能按当前源码重验；不照抄auto-v1历史未完成项。跨Job幂等、账号锁、预算预留、恢复和1/3/10件Fake等已在现有代码与测试中找到，不以历史报告旧清单断言缺失；真实验证边界仍保留。

## 任务书22项边界映射

| # | 边界 | 回归入口（tests/） |
|---|---|---|
| 1 | 完全干净 | test_full_product_audit、test_p1p2_default_read_session、test_auto_readonly_acceptance |
| 2 | 单确认mark | test_full_audit_remediation_bridge确认→Fake save/readback |
| 3 | 多mark且UNKNOWN | test_full_product_audit、test_8788_contract、test_full_audit_remediation_bridge |
| 4 | 原厂/印刷/包装/摄影保护 | test_8788_contract、test_watermark_prompt_contract、test_auto_deletion_planning |
| 5 | 类别/owner分歧 | test_v13_store_policy_consensus、test_v13_store_policy_consensus_cli |
| 6 | SKU四字段分歧 | test_sku_consensus、test_sku_output_contract |
| 7 | 缺字段/JSON/超时 | test_full_audit_model_continuation、test_ai_judge_json_content、test_unified_model_budget |
| 8 | 同SHA多位置 | test_full_product_audit、test_full_audit_remediation_bridge |
| 9 | SKU ID缺失/错配 | test_auto_semantic_ids、test_sku_output_contract、bridge |
| 10 | Description隔离/透传 | test_p1p2_scope_*、test_automation_description_opaque、test_v13_description_header |
| 11 | 模板缺失 | test_auto_template_applicability、test_v13_semantic_cli |
| 12 | state/SHA漂移 | test_full_audit_remediation_bridge、test_auto_comparison_cache、test_auto_evidence_binding |
| 13 | 重复Job/缓存版本 | bridge已完成Job重跑、test_workflow_v2、test_model_gateway_cli |
| 14 | 预留/usage/来源 | test_unified_model_budget、test_8788_token_budget |
| 15 | 费用未知/停止线 | test_unified_model_budget缺参数/价格/美元预留 |
| 16 | 失败不重试 | test_unified_model_budget超时、主客户端真实transport默认0重试 |
| 17 | 保存前失败/未知 | test_local_execution、test_auto_execution_semantics |
| 18 | APPLY_UNKNOWN禁止重发 | test_auto_unknown_readback、test_auto_resume_verification、test_auto_unknown_batch_workflow |
| 19 | 写后SHA/SKU漂移 | test_auto_sku_readback_binding、test_auto_saved_check、test_auto_wire_identity |
| 20 | 受保护字段变化 | test_v13_description_header（收紧）、test_p1p2_scope_*、test_auto_brand_readback |
| 21 | 同账号并发/跨Job同PID | test_auto_account_lock、test_auto_execution_ledger、test_auto_cross_shop_workflow |
| 22 | 损坏/写盘失败/重启悬挂 | test_unified_model_budget、test_8788_token_budget |

这些为Fake/Mock或离线验证；不代表22类已通过真实站点验收。旧observed模式的“缺usage继续”仅保留历史Fake行为，真实sender已关闭，不能作为新Canary授权路径。

复审补充：身份明确FAIL必须保留暂缓；直接调用compile_auto_plan也不能省略完整审核的未决项或未修复finding后返回CLEAN。两项回归已先失败后修复，纳入最终完整套件。
