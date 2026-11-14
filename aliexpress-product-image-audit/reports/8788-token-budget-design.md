# 8788 Token 预算保护实现说明

本轮仅修改验收 Runner 的预算接线，新增 `scripts/token_budget.py`、能力配置和 Fake 测试。水印 Prompt/Schema/聚合器、身份五维逻辑、共享 `BudgetManager` 及业务写入流程均未改动。

## 边界与依据

请求上限固定 24，总 Token 上限固定 300000，并发固定 1，无重试。实际 WorkBuddy 两个路由没有可适用的完整硬上界；STRICT 账本以 PREFLIGHT_BLOCKED 创建，禁止拿调用者传入的数字冒充供应商证明。没有可放行的真实 Provider 配置，也没有预算绕过参数。

`provider_capability` 绑定 endpoint、model、API/文档版本、复核有效期、路由和 usage 来源。`request_upper_bound` 只接受 DOCUMENTED_HARD_LIMIT / DOCUMENTED_EXACT_COUNT / DOCUMENTED_UPPER_BOUND；任一必需字段未知、过期、只有估算或 Fake 证据进入 STRICT 时，上界为 null。复核有效期只是配置维护门槛，不是供应商保证。

文本、每张图、其他输入、输出、额外开销五部分不重复相加。图片只在图像计量项中计一次；若原厂输入总额已包含图像，不应再累加图像子项。当前未采用任何图片估算或未证明的上下文长度作为硬边界。

`plan_budget` 要求正好24份完整上界，且最坏情况总和≤300000；不完整时总和为 null，TOKEN_CAP_PROVEN=false。SPEND_CAP_PROVEN 独立为 false，未把积分或金额额度重命名为 Token 限制。

## 权威账本

每个新 Job 有独立 `token-budget.sqlite`；Fake 使用不同的 `token-budget.fake.sqlite`。STRICT 与 FAKE 模式写入 meta，创建使用排他文件创建，既有账本不覆盖、不迁移、不重置。旧 Job / 旧预算完全不接入。

SQLite `BEGIN IMMEDIATE` + `synchronous=FULL` + DELETE journal，使检查余额、计数和预留在同一事务内持久化。每次操作校验版本、Job、固定上限、数据库完整性和逻辑状态；没有“读出余额后分别扣减”的窗口。跨线程/实例共享文件时也只能保留一个在途请求。

账本以逐 request_id 记录模型/Provider/任务/完整图片 SHA、Prompt/Schema/请求体版本、各项上界、预留状态、原始 usage、来源、时间和错误。Fake 总额上界明确标为合成夹具；未证明的分项为 null，不补造供应商计量。人读 JSON 只是导出，不参与放行。

全局：`committed=settled_actual+reserved+unknown_committed_upper_bounds`。只有满足 `committed+next_bound<=300000` 且请求数<24、无在途/未知/停止状态才能预留。请求次数不因失败或安全释放而退回。

## 状态变化

1. 原子提交 RESERVED，保存请求元信息；提交失败则不发送。
2. 持久化 DISPATCHED 后才调用一次 Fake transport。客户端崩溃窗口也按可能已发送处理。
3. 正常 usage 经 Provider Schema 校验后，将预留替换为实际消耗，保存完整原始 usage 和 usage_source。
4. 超时、服务端错误、无法解析或用量不完整：UNKNOWN_COMMITTED，保留原预留上界、总实际用量为 null，停止后续请求。
5. 实际用量超出预留：持久化实际值及 BUDGET_GUARD_BREACH，停止并承认事前证明失效；事后检测不能撤销消耗。
6. 仅本进程在 RESERVED 且尚未 DISPATCHED 时可用 LOCAL_NOT_SENT 释放；重复释放拒绝，次数仍计入24。没有远端状态查询，所以不接受“超时就是未发送”。
7. 重开有 RESERVED/DISPATCHED 的账本时保守转 UNKNOWN_COMMITTED；不重新请求、不重复扣减。已结算 request_id 不能重复记账或预留。

持久化失败会使当前实例停止，尽力写独立失败标记；同目录失败标记存在时拒绝恢复。即使磁盘无法写标记，权威账本的未结算预留仍保留，重开也不会释放。报告所用最后快照会标为 ledger_readable=false/usage未知，绝不用于继续放行。

## usage 解析和来源

原厂 DeepSeek 和 Kimi 分开解析：DeepSeek 校验 cache_hit+cache_miss=prompt；Kimi 校验缓存读写子项及别名；推理/图片/缓存子集不额外累加。字段缺失、改名、未知计量项、分项/总额或别名冲突都拒绝，并保留原始 usage。

当前 `workbuddy:<model>` Schema 始终因 USAGE_PROVENANCE_UNVERIFIED 拒绝；网关可估算回填 usage，不能仅凭数字格式放行。原厂解析器的测试不代表已把本机路由认证为原厂。FAKE 使用独立 fake-chat Schema，仅合成数据，实际调用与 Token 统计始终0。

## 运行与隔离

默认离线预检。现有 `--execute-real-models` 入口仍封闭，本轮未运行。没有新建模型客户端，既有 HTTP 辅助函数未接入发送；没有增加 Provider 探测、tokenizer 请求、站点读取或写入。

原 HardBudget 保留为既有离线单元测试的兼容接口，已从 Runner 放行路径移除；Runner 使用 DurableFakeBudget/TokenLedger。本轮所有能触发 transport 的运行均明确为 Fake，不能给 STRICT 提供授权或证明。

回滚本轮预算功能应恢复本轮基线 Runner，移走新增模块、能力配置和测试；不要删除 Job、账本、报告或证据。无需线上回滚。
