# 当前实现接口与契约（不是新架构方案）

复用 workflow_runner/workflow_v2_pipeline/audit_one/ai_judge/plan_compiler/plan_v2/executor/job_manager 主链。

| 现有/新增边界 | 实际契约 |
|---|---|
| audit_one→Workflow | 绑定PID/Shop的完整快照、原始图片/字节SHA、OCR/残差/模板证据 |
| Workflow→Judge | 稳定业务图片ID；模型负载只含白名单字段和图片，不含本地路径/密钥 |
| RemedyPlanner→Quality | 孪生/裁切/局部背景试擦/显式官方池候选；失败保留原URL |
| Quality→AutoDecision | 独立证据、真实源/候选SHA、必要检查全部为true；不靠置信度单值通过 |
| AutoDecision→Compiler | AUTO_SAFE按动作白名单，DEFERRED逐项保留；最终结构非法整件阻断 |
| Compiler→Executor | v3自动计划绑定Policy哈希、源快照、独立质量/语义记录；v2不自动获得新授权 |
| Dry-run/Apply | 共用final_state模拟器；上传预演显示UPLOAD_TOKEN；写前后均验证 |
| LocalExecutor→Site | 持久预算、幂等日志；最多一次Site.save；独立翻译；未知结果只读恢复 |
| 跨Job协调 | 账号内核锁跨输出root；持久ExecutionLedger阻止未知/重复写入 |
| 回读→验收 | 保存快照、实际图片字节SHA/型号/包装复检；离线check.py --job-dir核证据与结构 |

运行中Policy文件变更使旧权限失效。原图、候选和复检证据必须保留；不能删除日志后绕过幂等。

当前限制与未完成要求以implementation/remaining-blockers为准；接口已存在不代表其全部外部环境已验证。
