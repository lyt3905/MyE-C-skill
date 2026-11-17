# DeepSeek 本地标题重写实施计划

目标：按现有标题 SOP 调用项目已选定的 DeepSeek，支持批量、多线程、失败重试；每件取得有效结果即停止，保存本地 JSON，不访问商品站点。

采用 Python 标准库线程池，复用现有模型 HTTP 入口、JSON 解析器和标题常量。现有 JudgeClient 限定审核 schema、真实并发为 1 且重试为 0，不适合直接套用生成任务，因此只增加一个脚本，不增加第三套审核器或写入执行器。

- [x] 添加离线测试：单次成功、失败重试、重试耗尽、真正并发、重复输入复用、成功断点续跑、输入变化重新生成、HTTP 请求及 CLI 文件闭环。
- [x] 添加 `prompts/title_rewrite.md`：任务和 JSON 输出协议；运行时拼入当前 SOP 第 1–4 节，避免复制替换表。
- [x] 添加 `scripts/rewrite_titles_deepseek.py`：本地 JSON/JSONL 输入、可配置线程/重试/超时、增量输出、来源指纹；成功不复核、不多候选生成。使用现有 DeepSeek 型号和兼容 API，密钥从环境变量读取。
- [x] 添加示例输入与使用说明；运行相关离线测试、CLI 模拟 HTTP 闭环及语法检查，更新 PROJECT_STATE。

执行约束：单 Agent；保留工作区其他改动；不提交推送，不写线上商品，不改旧 Job 或账本。本次验证只用模拟 API，真实模型验证记为 NOT_RUN。Token 原样记录，缺失保留 null，不阻断。

验证：新增14项，相关离线回归共49项通过；日志 `reports/deepseek-title-rewrite-20261117-tests.log`。网络连接在测试时被禁止，HTTP 入口使用模拟响应。按用户单 Agent 要求自行复查，未派生审查 Agent。
