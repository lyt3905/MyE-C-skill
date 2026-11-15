# V2 当前逐项证据矩阵

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

| 要求 | 状态 | 证据 | 局限 |
|---|---|---|---|
| A/Git和基线 | 已核对 | work/v2-followup-20261115/baseline/manifest.json | 当前HEAD 20ecfe83；继续保留全部未提交改动，不提交推送。 |
| A/现有链路复用 | 本地已接入 | scripts/workflow_runner.py; scripts/full_product_audit.py; scripts/plan_compiler.py | 使用原JobManager、JudgeClient、BudgetManager、LocalExecutor/ExecutorService，无新总Runner/HTTP客户端/账本。 |
| A/项目配置及单Agent | 配置核对 | AGENTS.md; .codex/config.toml | 项目gpt-6.1-sol/medium配置保留，关闭agents；没有创建子Agent。 |
| B/每SHA统一判断 | Fake覆盖 | tests/test_v2_vision.py; tests/test_v2_workflow.py | 逐SHA一次主模型、独立条件第二模型，不重复同一模型抬高置信。 |
| B/合法分类五动作与绑定 | Fake覆盖 | scripts/ai_judge/image_action_decision.py; scripts/config/schemas/image-action-decision.v2.schema.json | 字段、SHA、枚举、归一化坐标、弃权/UNKNOWN、版本和缓存绑定。 |
| B/保护文字与不明归属 | Fake覆盖 | test_v2_completion.test_protected_text_keeps_and_unknown_ownership_reviews_with_v2_client | 工厂Logo、商品/包装印刷、创作者署名保留，归属未知暂缓。真实识别效果未验证。 |
| B/模糊盒关系不变成通过 | Fake覆盖 | test_v2_completion.test_possible_same_product_box_stays_review_after_second_model | 第二模型仍POSSIBLY_SAME_PRODUCT时保持REVIEW。 |
| B/OCR和CV语义禁用 | Fake路径断言 | tests/test_v2_workflow.py | V2执行时旧audit/run_ocr/border_candidates被设为抛错；传统算法只用于像素处理。 |
| B/独立full-audit入口 | Fake路由覆盖 | test_v2_completion.test_full_audit_cli_defaults_to_v2_without_ocr_template_requirement; test_standalone_v2_audit_freezes_new_job_and_uses_unified_strategy | run和full-audit均默认V2；legacy显式指定；不要求OCR模板。 |
| C/同商品盒与优先级 | Fake程序规则 | tests/test_v2_repairs_sku.py; test_v2_workflow.test_box_branch_binds_existing_sku_without_creating_variants | 清楚盒/同框/盒单图/置信门槛；优先玩具同框，现有真实SKU ID。 |
| C/无盒两图 | Fake程序规则 | test_v2_completion.test_two_no_box_candidates_both_enter_existing_sku_image_pool | 两张独立SHA进入已有images.sku列表；不足不复制，角度优先。 |
| C/单SKU双引用 | 未证明服务端能力 | scripts/final_state.py; scripts/executor/site_write_client.py | 当前执行器只映射一个skuImageUrl；不伪造第二字段/变体。与两张图进入SKU图片池区分。 |
| C/运输箱背景盒部件 | Prompt契约/Fake规则覆盖，真实未验证 | prompts/image_action_decision.v2.md; tests/test_v2_repairs_sku.py | AI是唯一分类源；程序拒绝不合格分类/非同商品盒；不能用Fake声明真实识别准确。 |
| C/映射不明与适用性 | Fake覆盖 | test_v2_completion.test_sku_selector_preserves_valid_existing_reference_and_respects_suitability; test_missing_sku_id_preserves_reference_while_independent_main_repair_continues | 尊重模型SKU适用性、保留合格旧引用；缺/重复ID不造ID，独立主图修复仍可继续。 |
| D/授权及mask | 本地合成验证 | scripts/image_repairs_v2.py; tests/test_v2_repairs_sku.py | 仅OWNED_OR_LICENSED，保护区/面积/归一化/原图只读、Telea/NS与一次备选。 |
| D/透明度 | 合成像素验证 | test_v2_completion.test_local_repair_preserves_transparency_outside_mask | RGBA的mask外颜色及alpha不变；候选丢失透明度时拒绝。 |
| D/LaMa可调用契约 | 合成TorchScript验证 | test_v2_completion.test_local_torchscript_adapter_accepts_installed_lama_two_tensor_contract | 真实torch.jit加载合成计算图测试双Tensor/字典契约、padding和输出；不是训练模型质量验证。 |
| D/真实LaMa模型 | 未配置 | C:/Users/shana/.cache/torch/hub/checkpoints; docs/image-edit-adapter-v2.md | 只发现两份.partial；项目及现有环境未发现完整LaMa权重；不自动下载。 |
| E/真实编辑后端配置入口 | Fake文件适配器覆盖 | test_v2_completion.test_frozen_configured_edit_adapter_runs_through_normal_prepare_and_budget | image_options冻结本地适配器路径、SHA和已选模型，在同一JudgeClient/BudgetManager内执行。 |
| E/真实图像编辑服务 | 未配置/未验证 | docs/image-edit-adapter-v2.md | 没有已核实支持编辑的真实服务及适配器；不得把MiMo视觉端点假设为图片生成端点。 |
| E/失败质量分型 | Fake覆盖 | tests/test_v2_workflow.py; test_v2_completion.test_failed_regeneration_identity_never_uploads_or_repeats_edit | 身份/包装/印刷损伤立即拒绝；残留/伪影最多一次备选；重绘失败不反复尝试。 |
| E/删除后SKU换引用 | Fake全链路 | test_v2_completion.test_deleted_image_sku_reference_is_reassigned_in_same_single_save; test_delete_sku_reassignment_to_repaired_image_resolves_both_operations | 同一次保存中删除池引用并重绑真实SKU；实际方案缺少所需重绑则不执行删除。 |
| E/最后包装证据 | Fake全链路 | test_v2_completion.test_deletion_preserves_last_retail_box_evidence; test_box_composite_deletion_can_continue_when_packaging_evidence_remains | 保留唯一盒证据；另有同商品包装证据时可删除装饰拼图并绑定保留位置。 |
| E/保留图内容漂移 | Fake独立回读 | test_v2_completion.test_retained_box_byte_drift_fails_content_verification_without_resave | 记录预期/实际SHA；内容变更失败，不重发保存。 |
| F/引用专用图片修复 | Fake全链路 | test_v2_completion.test_reference_only_sku_image_is_repaired_uploaded_and_bound_to_existing_id | 原先只在SKU引用的图片生成新SKU池位置，上传与URL回读可验证。 |
| F/引用专用删除及暂缓 | Fake全链路 | test_v2_completion.test_reference_only_delete_is_resolved_by_authorized_existing_sku_assignment; test_reference_only_review_remains_explicitly_deferred | 有授权、真实ID与明确替代时换引用；REVIEW保留明确记录，不丢条目。 |
| F/上传后URL回读 | Fake全链路 | test_v2_completion.test_repaired_image_selected_for_sku_verifies_resolved_upload_url | 用执行器已解析的expected_after校验SKU，避免成功修复误报失败。 |
| F/Description与非图片字段 | Fake全链路 | tests/test_v2_workflow.py; test_v2_completion.test_v2_one_three_ten_products_use_real_jobs_and_shared_fake_ledger | Description不进模型上下文、未下载其URL；写后原类型和值一致；价格/状态/行数等保护。 |
| F/单次保存与未知结果 | Fake全链路 | test_v2_workflow.test_unknown_save_has_no_resend; test_v2_completion.test_v2_batch_stops_after_unknown_save_without_creating_next_job | APPLY_UNKNOWN只读恢复，不再上传保存；批次停止，不创建后续Job。 |
| F/I跨Job幂等 | Fake全链路 | test_v2_completion.test_v2_cross_job_duplicate_plan_does_not_save_again | 同PID、同源状态、同操作的第二Job保存0次，历史Job证据不改写。 |
| I/1/3/10商品 | V2 Fake覆盖 | test_v2_completion.test_v2_one_three_ten_products_use_real_jobs_and_shared_fake_ledger; reports/v2-followup-retained-fake-jobs.json | 14个不同PID的实际V2 Fake Job，共用批次账本，串行单次保存和保护字段断言。 |
| G/调用记录与停止机制 | 本地预算及Fake覆盖；真实未验证 | scripts/ai_judge/client.py; scripts/budget_manager.py; tests/test_unified_model_budget.py | 统一入口；用户Token仅记录覆盖有效，缺失不造0；显式STRICT/受控模式仍拒绝不完整配置。 |
| G/真实Shadow | NOT RUN | reports/v2-controlled-shadow-report.md | 本轮禁止真实模型调用，不能替代成已完成状态。 |
| G/分动作及包装准确率 | 工具Fake验证，真实门槛未满足 | scripts/shadow_evaluate.py; tests/test_v2_accuracy.py; reports/v2-evaluation-empty-real.json | 跨位置SHA独立计数、五动作和包装/SKU分组；真实人工样本0，不能满足真实门槛。 |
| H/线上Canary | NOT RUN | reports/v2-single-product-live-canary.md | 当前禁止线上商品写入；前轮PID5097授权和结果不复用。 |
| I/真实批量及独立生产验收 | 未完成 | reports/v2-production-readiness.md | 真实Shadow/Canary、准确率、后端能力与独立审查仍缺，不得PRODUCTION_READY。 |
| 交付/17份报告与补丁 | 本地交付已校验 | reports/v2-evaluation-acceptance.md; reports/v2-evaluation-delivery-manifest.json | 795项完整离线回归通过；真实阶段仍未完成。 |
