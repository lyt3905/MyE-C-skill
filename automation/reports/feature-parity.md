# V2 功能对应与状态

| 基准能力 | 新软件模块 | 验证状态 / 测试 |
|---|---|---|
| DeepSeek 单模型、禁用 MiMo 和静默回退 | ai_judge / model_config | IMPLEMENTED, UNIT_TESTED, FAKE_VERIFIED；test_v2_deepseek_only, test_current_model_selection |
| 置信度 RECORD_ONLY、usage 缺失为 null | image_action_decision / budget_manager | IMPLEMENTED, FAKE_VERIFIED；test_v2_confidence_record_only |
| 全图审核与 SHA 多 URL 归组 | full_product_audit / image_content_plan | IMPLEMENTED, FAKE_VERIFIED；test_v2_reusable_rules |
| 正文图片、text-image 边界、shopFooter 和正文样式保护 | description_images | IMPLEMENTED, FAKE_VERIFIED；test_description_image_edits, test_v2_reusable_rules |
| 同照片 SIFT / RANSAC / 覆盖率 / 中心稠密像素证明 | visual_versions | IMPLEMENTED, LOCAL_CV_VERIFIED；test_visual_versions 的原图、压缩缩放、不同姿势案例 |
| 干净 KEEP 同照片优先 REPLACE_TWIN、零上传 | v2_remediation / existing executor | IMPLEMENTED, FAKE_VERIFIED；test_visual_versions.VersionWorkflowTests，独立 CLI twin |
| 无 twin 大边框删除 / 小覆盖字局部修复 | image_action_decision / image_repairs_v2 | IMPLEMENTED, FAKE_VERIFIED；独立 frame / repair、test_v2_reusable_rules |
| 未知文字保留、厂家包装产品署名保护 | image_action_decision | IMPLEMENTED, FAKE_VERIFIED；test_v2_text_color_policy, test_v2_full_workflow |
| 主图、详情、正文、SKU 池、真实 SKU 行统一同步 | v2_remediation / sku_assignment | IMPLEMENTED, FAKE_VERIFIED；test_visual_versions, test_v2_two_sku_images |
| 两张无盒不同 SHA 图绑定两个现有规格 | sku_assignment | IMPLEMENTED, FAKE_VERIFIED；test_v2_two_sku_images |
| 受限计划、一次保存、超时先回读、禁止盲重发 | plan_compiler / executor.local | IMPLEMENTED, FAKE_VERIFIED；test_v2_workflow, test_v2_full_workflow |
| 独立引用和图片字节回读、非图片字段精确保留 | v2_remediation.verify_content | IMPLEMENTED, FAKE_VERIFIED；包括漂移、失败和响应丢失对照 |
| LaMa 两种 TorchScript 契约和精确 mask | image_repairs_v2 | IMPLEMENTED, UNIT_TESTED；合成 TorchScript；训练权重未复制 |
| 可配置外部图像编辑适配器 | image_repairs_v2 / v2_remediation | IMPLEMENTED；真实服务 NOT_RUN |
| 独立安装、资源、CLI、Job/缓存/账本/日志 | pyproject / cli / paths / resources | IMPLEMENTED, FAKE_VERIFIED；隔离 wheel 完整回归 |

所有 REAL_MODEL_VERIFIED、REAL_READONLY_VERIFIED、REAL_WRITE_VERIFIED 均 NOT_RUN；PRODUCTION_READY 不作声明。SKU 当前每行仍只有一个 skuImageUrl，没有虚构多图接口。图片外业务规则未重新设计。

Configuration schemas: migrated policy Schema aligned with already-supported V2 actions; gateway and image-options schemas connected to the existing loaders/Job freeze. All examples remain write-disabled. New configuration tests pass.

Shared full verification command and results: regression-test.md / final-isolation/regression/. Every row uses that complete discovery; evidence SHA256 values: evidence-sha256.json.
