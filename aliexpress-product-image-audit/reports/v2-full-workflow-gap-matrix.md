# V2缺口与处理结果

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

本轮基于756873e的现有V2定点修复；831项完整回归通过（失败/错误/跳过0），新增26项。标准测试入口退出0、网络尝试0、测试前后297份源码/配置/Prompt绑定一致。22个独立保留Fake场景、1个正式CLI完整Fake任务及2个本地OpenCV/真实训练LaMa的Fake工作流已完成。新增真实语义模型调用、线上读取/上传/保存均0；不add/commit/push。

普通代码缺口已在现有链路中修复并通过Fake；外部依赖/授权/平台能力缺口不以Fake替代。真实编辑服务能力、当前平台其他SKU接口及本版本真实准确率/写入效果仍是生产阻断。
