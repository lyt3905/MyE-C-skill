# V2统一视觉决策契约

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

版本化Prompt：prompts/image_action_decision.v2.md；运行校验：scripts/ai_judge/image_action_decision.py；声明Schema：scripts/config/schemas/image-action-decision.v2.schema.json。

每个独立SHA由主视觉模型一次性判断visual_class、业务位置、零售盒状态/区域/关系、文字类型和区域、身份、完整性、清晰度、SKU适用性、保护区及KEEP/DELETE/REMOVE_TEXT/AI_REGENERATE/REVIEW。结果映射回全部主图/详情/SKU池和引用位置；SHA、枚举、有限置信、区域和证据ID必须绑定。

只允许deepseek-v4.1-flash和mimo-v2.6-pro（保留已配置路由别名）。用户门槛0.80覆盖文档0.90默认值。DELETE/AI_REGENERATE及关键不确定/无效JSON触发一次独立第二模型；不传第一模型答案，不重复同一模型刷置信。冲突、弃权、身份未知、未知文字、盒关系仍POSSIBLY_SAME_PRODUCT等保持REVIEW。

OCR/CV不作为语义来源；Description完全排除。缓存继续使用原模型/图片/上下文/Prompt/Schema/配置绑定。真实语义准确率尚未验证。
