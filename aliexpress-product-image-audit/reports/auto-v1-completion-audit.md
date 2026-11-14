# 最终需求完成审计（本地开发验收）

基于任务书14/14.1及当前实现核对，以下为证据位置，不以测试数量替代覆盖。E01–E35的组件与Workflow证据边界见覆盖矩阵；真实模型和生产协议按未验证披露。

| 要求 | 实现 | 已执行测试模块 | 证据边界 |
|---|---|---|---|
| 自动入口与授权 | workflow_runner.run_automatic / automation_policy | disabled_audit、recovery_policy、auto_workflow | 本地Fake验证 |
| 四条标准闭环 | auto_workflow / semantic_remedies / plan_compiler | auto_workflow、auto_workflow_more、auto_semantic_workflow | 本地Fake验证 |
| 试擦与保护元素 | remedy_planner / policy_engine / visual_quality | auto_erase、auto_real_auditor_workflow、policy_v2、business_matrix | 处理代码真实；语义判断Fake |
| 独立证据与不确定保留 | remedy_binding / auto_decision | auto_evidence_binding、auto_reference_isolation、auto_generated_sku | 本地验证 |
| Dry-run共用模拟 | final_state.simulate_final_snapshot | auto_live_preview、auto_preview_identity | 本地验证 |
| 写前结构阻断 | final_state.pre_apply_validate / service | round2_preapply、auto_required_pools、auto_compiler | 本地验证 |
| 单次保存及保护字段 | executor/local / service / site_client | auto_wire_identity、local_execution、auto_unknown_batch_workflow | Fake调用计数；真实协议未验证 |
| 独立翻译与重试限制 | executor/local.retry_translation | auto_semantic_workflow、auto_translation_retry | 本地Fake验证 |
| 回读内容SKU描述 | auto_workflow.verify_content / check | auto_sku_readback_binding、auto_saved_check、auto_main_chain | 本地Fake验证 |
| 状态恢复与批次熔断 | execution_ledger / batch_scheduler | auto_unknown_batch_workflow、auto_cross_shop_workflow、auto_batch_workflow | Windows Fake验证 |
| 预算及真实性 | BudgetManager / automatic_report | auto_reservations、auto_report_complete、auto_comparison_cache | 无真实usage不报节省比例 |
| 交付与回滚 | build_sync_bundle / controlled_rollback | delivery_bundle、auto_controlled_rollback | 归档隔离281次/40.426秒/OK |

外部未验证：真实OCR/GLM/Kimi标注质量、站点只读Canary、真实上传/保存/翻译/回滚。开发期间没有生产试写。

最终交付归档独立测试：293次/53.601秒/OK（包含真实双进程上传限速与混合失败批次）。


## Phase逐阶段证据定位

| 阶段 | 当前实现与直接证据 |
|---|---|
| 0 | baseline保留HEAD、工作区、原回归和调用路径；未覆盖原工作区 |
| 1 | auto_main_chain/required_pools/live_preview/preview_identity及v21_compiler覆盖原主链缺陷 |
| 2 | auto_decision混合安全/延后，auto_conditional条件检查状态；compiler仅接纳AUTO_SAFE |
| 3 | auto_workflow孪生、auto_workflow_more裁切完整Fake闭环；auto_erase及real_auditor_workflow试擦/官方池 |
| 4 | auto_sku共享本体/盒照/冲突；semantic_workflow与generated SKU完整Fake分派/回读 |
| 5 | auto_title确定规则，semantic_workflow标题/翻译，brand_workflow明确品牌字段；未知来源不改 |
| 6 | final_state共用模拟，auto_live_preview；wire_identity验证autoSave=true；unknown_write不重发 |
| 7 | workflow_more部分整改保留详情，E07分歧实际审核入口；report_complete及saved_check验收 |
| 8 | batch_workflow的1/3/10件，cross_shop_workflow串行；upload_rate双进程共享；reservations原子预算 |
| 9 | Windows完整回归、独立归档回归、定向独立复审及RED/GREEN修复；十报告/README/Schema/源码ZIP/patch |



最终状态以末尾交付验收记录为准。Phase2条件分级、Phase8全局上传限速以及内容失败熔断均已补齐，并包含于300次完整回归。

最终交付验收：当前源码完整回归300次/49.648秒/OK；同版本归档解压独立目录完整回归300次/48.809秒/OK，260个唯一测试。封存期间代码/JSON配置/PowerShell脚本SHA与已测试归档逐项一致。外部未验证项目仍按清单披露。
