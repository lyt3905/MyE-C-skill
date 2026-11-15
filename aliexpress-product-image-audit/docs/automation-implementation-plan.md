# 本轮集成计划

依据：用户指定任务书 a14669b；用户已授权连续本地开发、测试，禁止子Agent/提交/真实调用。

复用现有 workflow_runner、full_product_audit、auto_workflow、BudgetManager、token_budget，不新增Runner或模型客户端，不重写模块。

- [x] A：检查Git、读取源码/报告、封存已有修改和433证据哈希。
- [x] B：项目配置、AGENTS、状态入口。官方配置依据 https://learn.chatgpt.com/docs/config-file/config-reference 。
- [x] C：完整审核同Job接入；权威产物按SHA/Job/Shop/PID/契约版本校验，映射业务位置，UNKNOWN保留。先写失败测试，再做最小接线。
- [x] D：现有公共预算层增加CONTROLLED_CANARY逐请求预留/usage/费用停止；真实默认拒绝；单在途无重试；STRICT不变。辅助模型共用预算；旧直连入口拒绝调用。
- [x] E：Fake集成、完整unittest、标准测试入口、compileall、diff和433证据复核，输出12报告/日志/JSON/补丁。

边界：无有效价格/授权/USD预算时不启用Canary；缺字段、账本损坏、并发、超时、重启悬挂一律停止；未知不变成功。编译和独立质量复核复用旧门禁。真实Shadow、真实写入和生产验收NOT RUN。

裁决：product_state历史Description标题解析例外与本轮固定字段规则冲突。按明确新要求仅保留原值原类型比较；保留旧测试所有保护目标，并将曾允许标题变化的断言收紧为拒绝。没有修改历史报告或业务商品。
