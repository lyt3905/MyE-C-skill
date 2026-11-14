# 未验证与限制
真实站点PID/Shop、本地凭证及真实模型未提供，本轮未读取凭证，未连接生产；真实模型/商品/执行均未验证。
终检调用check.verify_snapshot纯结构体检并与ExecutorService完整写敏感状态哈希比较；不等同线上重新下载所有图片运行完整OCR/残差人工验收。残差拼图仍需人工查看，机器测试不能代替肉眼确认。
本轮支持现有compiler白名单修改；新图片替换和复杂SKU/描述修复仍需具体证据与人工决策；未宣称所有任务书T01-T30均新增独立完整场景。
APPLY_UNKNOWN持久化阻止自动重试；人工先只读回读核对，不提供自动重发。

## T01–T30逐项证据（全部为离线，不代表生产通过）

|项|实现/测试证据|验证范围与缺口|
|---|---|---|
|T01|test_workflow_v2.test_complete_and_resume_without_side_effects|干净只读链通过，真实商品未验证|
|T02|test_vertical_workflow.test_review_dryrun_apply + test_business_matrix.test_watermark_sop|候选链与第三方分类分别通过，真实水印像素识别未验证|
|T03–T05|test_business_matrix.test_watermark_sop|厂家/社交/摄影KEEP通过|
|T06|test_workflow_evidence_integration.test_template_and_residual_are_real_outputs|模板实际调用与拼图生成通过，真实极淡样本未验证|
|T07|policy/compiler仅人工变更|无自动擦除路径；真实本体淡字方案选择未验证|
|T08|test_business_matrix.test_watermark_sop|中文海报复核通过|
|T09|compiler只接受原池URL且需人工review|test_v21_compiler.test_T09_box_deletion_rejected已通过；基于证据盒照标记强制拒绝删除|
|T10|check.verify_snapshot main_count|test_vertical_workflow.test_T10_excess_main_images_fail_delivery证明超6终检拒绝；删除须人工选择|
|T11–T15|test_business_matrix.test_sku_packaging_protection + test_semantic_queue|缺图/共享本体/共享盒/有盒无盒冲突离线通过；模型字段已加Prompt/Schema，真实输出未验证|
|T16–T17|test_business_matrix.test_description_http_status|404/410死链与403/405不确定通过|
|T18|test_ai_judge.test_timeout_counted|超时不CLEAN通过|
|T19|test_ai_judge.test_invalid_response_never_clean|无效JSON复核通过|
|T20|test_business_matrix.test_model_disagreement_reviews|模型分歧复核通过|
|T21|test_vertical_workflow.test_review_dryrun_apply|manual重编译到执行通过|
|T22|test_v21_compiler.test_review_evidence_mutation_rejected|证据变更复核失效通过|
|T23|live_dry_run比较compiled.plan_sha256|test_T23_plan_tampering_rejected_before_get与test_T23_evidence_tampering_rejected_before_get独立通过|
|T24|test_v21_compiler.test_live_dry_run_and_bound_receipt|live状态漂移路径实现，真实商品漂移未验证|
|T25|test_vertical_workflow + test_token_opt.test_dry_run_has_zero_mutations|零写Fake通过|
|T26|test_local_execution.test_failures_and_no_retry|上传失败零save通过|
|T27|test_vertical_workflow.test_save_timeout_journal_blocks_retry|APPLY_UNKNOWN且禁止重试通过|
|T28|test_local_execution.test_failures_and_no_retry|回读不符不VERIFIED通过|
|T29|test_vertical_workflow.test_review_dryrun_apply|非空计划一次save回读通过|
|T30|test_local_execution.test_failures_and_no_retry|注入完整checker FAIL不交付通过；默认snapshot结构终检|
