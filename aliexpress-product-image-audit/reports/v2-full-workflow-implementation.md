# V2完整主流程改造

本轮基于756873e的现有V2定点修复；831项完整回归通过（失败/错误/跳过0），新增26项。标准测试入口退出0、网络尝试0、测试前后297份源码/配置/Prompt绑定一致。22个独立保留Fake场景、1个正式CLI完整Fake任务及2个本地OpenCV/真实训练LaMa的Fake工作流已完成。新增真实语义模型调用、线上读取/上传/保存均0；不add/commit/push。

| 功能 | 状态 | 证据与限制 |
|---|---|---|
| 正式入口、采集、去重及引用 | IMPLEMENTED / FAKE_VERIFIED | workflow_runner run(read_only/audit/dry_run/apply/auto_apply)、full-audit、audit_one默认V2；显式legacy兼容；原Job不迁移 |
| 双模型分类与五动作 | IMPLEMENTED / FAKE_VERIFIED | 每独立SHA每模型一次；归属/身份/动作/SKU冲突明确记录；新真实准确率NOT_RUN |
| OpenCV/LaMa像素执行 | IMPLEMENTED / FAKE_VERIFIED / REAL_VERIFIED | REAL_VERIFIED仅指本地完整训练权重对自有合成图真实推理，不包含真实商品语义质量 |
| AI编辑及回退 | IMPLEMENTED / FAKE_VERIFIED / BLOCKED | 有界调用既有适配器、记账和质量门禁；真实服务能力/配置尚无证据，真实执行NOT_RUN |
| SKU有盒/无盒分支 | IMPLEMENTED / FAKE_VERIFIED | 现有真实ID；两张不同SHA候选；当前writer仅单URL引用，第二张纳入图片池并如实报告限制 |
| 平台多引用接口调查 | BLOCKED | 旧真实快照证实skuImageUrl为字符串、图片池为数组；未新授权线上读取，不能断言平台不存在其他接口 |
| Plan/上传/保存/独立回读 | IMPLEMENTED / FAKE_VERIFIED | 正式CLI保留任务1模拟上传1保存，全图片池+SKU引用字节校验，非图片字段精确比较 |
| 报告与账本 | IMPLEMENTED / FAKE_VERIFIED | 原始响应、规范化结果、差异、mask、候选、回执、独立快照及模型usage均落原Job目录；未知usage/费用null |
| 本轮真实Shadow/真实整改 | NOT_RUN / BLOCKED | 本轮未授权新真实模型或线上读写；历史授权不复用 |
| 生产就绪 | BLOCKED | 不能标PRODUCTION_READY：缺本版本独立真值准确率、实际编辑/平台新接口/新线上写入回读证据 |

## 实际变更

- workflow_runner：read_only接现有完整V2审核；run --mode apply复用现有auto_apply授权执行；单独apply加载冻结策略并执行V2字节回读；无变更路径也独立验证后才报告完成。
- full_product_audit：新直接调用默认V2和RECORD_ONLY；保留显式legacy；传入真实可用标题/身份上下文，仅sanitizer白名单，无Description；只读任务也生成原有报告。
- image_action_decision/Schema/Prompt：业务类别、文字owner、可选逐字段评分；根confidence要求覆盖所有关键判断的最低把握。身份/字段缺失或未知保留REVIEW，两个模型均须达到0.80。保留原始/规范化结果和字段差异。
- 区域协调：只对两模型同类同归属且IoU≥0.5的定位作几何匹配（不是降低模型置信度），矩形修复范围取并集，保护区域合并；远离区域、不同多边形修复区域或真实业务字段分歧保持REVIEW。不平均置信度抬高结果。
- 本地修复：最多2次本地尝试；本地技术失败跳过重复本地算法，只有已配置且授权的适配器才允许1次AI回退。身份/保护损坏直接停止。成功回退必须绑定本地失败记录、独立质量通过和候选SHA，修复原建议与实际执行动作均可追溯。
- 文字保护与SKU：MANUFACTURER/PRODUCT/PACKAGING/CREATOR归属不可擦；不将工厂型号促销文字无条件排除SKU。UNKNOWN不得擦除或凑SKU候选。
- 回读：独立快照independent_after.json及其SHA；所有保留图池/真实SKU引用均按原图或上传候选SHA验证；所有非图片字段（包括SKU规格/价格/ID和Description）原值原类型比较。
- 业务最终状态统一为AUTO_VERIFIED/PARTIALLY_AUTO_FIXED/REVIEW_REQUIRED/FAILED/APPLY_UNKNOWN，技术恢复状态另存technical_status。批处理仍按技术致命状态停止，未知保存不重发。

未新建Runner、模型客户端、预算账本或商品写入执行器。旧条件式模型次数断言改为更严格的双模型断言；旧协议测试显式选择legacy，未删除/跳过测试。历史响应/Job/账本/标签不修改。
