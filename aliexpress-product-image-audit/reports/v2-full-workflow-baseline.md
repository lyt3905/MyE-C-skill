# V2完整主流程基线（改造前）

基线HEAD：756873e26235920669af3950222f89e66ae5fdb6；分支codex/8788-contract-local-fix-20261114。项目自身工作区原为干净；同仓库profit-ledger-registration等其他项目修改完整保留。既有805项测试及Q批次历史证据按SHA封印，原始Job/响应/账本不改写。

唯一执行目标为用户本轮《完整主流程闭环改造任务计划书》，授权仅本地开发/测试。新真实模型、线上读取及写入NOT_RUN；不沿用历史授权。

| 生产链路 | 基线代码/行为 | 需要验证或修复 |
|---|---|---|
| run audit/dry_run/auto_apply | workflow_runner.main → JobManager(v2) → run_automatic → full_product_audit.run_unified_audit → v2_remediation.prepare → compile_auto_plan → LocalExecutor | 已有主干；须完整入口回归 |
| run read_only/apply | main末端else创建未带image_workflow的Job → legacy run | V2 CLI默认未贯穿所有mode |
| direct run_full_audit | image_workflow=None → create默认legacy | 正式函数默认与CLI不同 |
| apply子命令 | local_apply → LocalExecutor.execute → record_executor_receipt | 仅结构回读不等于V2内容回读；须检查计划类型和回读 |
| 模型协调 | image_action_decision.decide，主模型确定时不调用第二模型；区域/保护区域要求精确相等 | 本轮要求独立双模型关键字段协调；SKU适用性未比较 |
| 分类与上下文 | 旧visual_class仅9类；上下文未传实际title/model/product_type | 缺装饰拼版/尺寸表等明确类别，可能过度暂缓 |
| 本地修复/AI编辑 | remove_text + 已有configured_image_edit；真实完整LaMa已安装 | 普通本地修复失败后未接通已配置AI回退 |
| SKU | select_v2有盒/无盒+真实ID；单URL方案 | PROMOTIONAL_TEXT全部排除，无法区分工厂正常型号文字 |
| 字节回读 | v2_remediation.verify_content核验整改候选和保留包装素材 | SKU_ASSIGN只有URL比较，普通保留图未全面按源SHA核验 |
| 最终证据 | 既有automatic_report/模型账本/Job目录 | 需对齐本轮完整统计与真实/Fake等级 |

已有支持属于IMPLEMENTED，部分FAKE_VERIFIED；不能因文件存在标为REAL_VERIFIED或PRODUCTION_READY。历史Q批次24图只有1 KEEP、23 REVIEW，10份明确DELETE全暂缓，证明真实业务目标未完成。其原始结果保持不变。
