# V2完整主流程闭环实施计划

**Goal:** 在现有模块中接通Shop/PID到审核、整改、SKU、上传保存、独立回读和报告。
**Architecture:** 保留workflow_runner、full_product_audit、JudgeClient、BudgetManager、JobManager、Plan和LocalExecutor。以当前756873e为基线，只修复已有路径及数据契约，不另建Runner或执行器。
**Spec:** C:/Users/shana/Downloads/MyE-C-skill_V2_完整主流程闭环改造任务计划书.md
**Execution:** 用户已明确要求单Agent连续本地执行；无需阶段确认，不add/commit/push，不调用真实模型或线上站点。

## 共同约束

- DeepSeek/MiMo，0.80（含）；Token RECORD_ONLY，未知usage/费用为null。
- Description完全排除图片分析，所有非图片字段原值原类型保护。
- 不修改历史Job、原始响应、账本或标签；基线及证据封印见work本轮目录。
- 外部编辑服务和新线上读取/写入均不假造验证；依赖未获授权时标记BLOCKED/NOT_RUN。
- 不删除测试。新需求取代旧条件式复核时，更新旧断言为更严格的双模型断言，同时保留其余校验。

## Task A：生产链路与基线

- [x] 检查Git、源文件与历史证据，保存task-spec.md及baseline。
- [x] 检查run/read_only/full-audit/apply/recovery及上传保存真实调用关系。
- [x] 写v2-full-workflow-baseline.md；记录接口证据和代码缺口。

## Task B/C/D：正式入口与统一视觉契约

Files: scripts/workflow_runner.py、scripts/full_product_audit.py、scripts/ai_judge/image_action_decision.py、对应Schema/Prompt、tests/test_v2_full_workflow.py。

- [x] 先以测试证明read_only/new apply不能绕过V2、直接full-audit默认V2；旧显式legacy仍兼容。
- [x] 正式流程每独立SHA每个模型最多一次，均独立分析，不泄漏对方结果。
- [x] 比较类别、身份、包装、水印归属、动作和SKU适用性；同语义不同措辞/小区域偏移可协调，真实冲突保留字段差异及REVIEW。
- [x] 扩充业务图片类别与文字归属；工厂型号/品牌不可作为可擦第三方水印。
- [x] 用真实可用商品身份/标题上下文，不引入Description，不将UNKNOWN补YES。

## Task E/F：修复、质量与SKU

Files: scripts/image_repairs_v2.py、scripts/v2_remediation.py、scripts/visual_quality.py、scripts/sku_assignment.py。

- [x] 为本地算法失败/质量不通过到已配置AI适配器的有界回退编写失败测试，再实现；身份损坏不得重试刷通过。
- [x] 质量检查包括身份、结构/颜色/角度/配件、包装、受保护文字、清晰度、用途和伪影；旧质量记录兼容但新Prompt明确覆盖。
- [x] 工厂促销/型号文字若明确归属且受保护，不无条件排除SKU候选；归属未知不能擦除或自动选用。
- [x] 有盒绑定现有真实SKU；无盒两张不同SHA，数量不足及单URL限制分开报告。
- [x] 检查本地已有接口与真实快照证据；未经新授权不联网核实其他接口。

## Task G/H/I/J：计划、写入、独立回读与完整报告

Files: scripts/workflow_runner.py、scripts/v2_remediation.py、scripts/automatic_report.py、现有executor与Plan按实证需要定点修改。

- [x] 确认apply也进行V2候选内容回读，不能仅凭结构匹配宣称完成。
- [x] 独立验证保留/新增/替换图片实际字节及SKU引用图片，核对所有非图片字段。
- [x] 保留未知保存停止/只读恢复语义；Fake覆盖保存已生效但超时。
- [x] 现有报告中补齐图池/独立SHA/动作、修复、SKU、写入、回读及模型usage统计。

## Task K：验收与交付

- [x] 新测试观察RED后实现并GREEN；用现有Fake场景扩展完整Shop/PID入口，不另写Runner。
- [x] 覆盖任务书17个场景；真实训练LaMa仅本地自有测试图推理，真实语义模型/线上访问0。
- [x] 运行标准完整回归，保留全部日志、退出码、测试前后源码绑定及历史封印校验。
- [x] 生成任务书10份v2-full-workflow报告，18项验收问题逐项回答，并给出Diff及交付SHA清单。
- [x] 本地实现与Fake分别验收；真实Shadow/整改/平台验证未经本轮授权标记NOT_RUN/BLOCKED，完整生产目标不冒报完成。

## Review focus

双模型同动作却SKU适用性不同；保护区域微小差别不应掩盖真实文字归属冲突；仅SKU引用出现的原图；上传后URL与候选SHA对应；超时已保存的只读恢复；未知用量不得变0；Description嵌套值及类型变化必须失败。
