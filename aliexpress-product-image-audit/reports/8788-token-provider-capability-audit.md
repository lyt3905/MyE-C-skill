# 8788 Provider Token 能力核查

核查日期：2026-11-14。本轮只读取公开技术文档和本机非敏感源码；没有调用聊天、tokenizer、models、余额或账户 API，没有读取网关账户密钥。结论：**当前实际链路不具备已证明的完整 Token 上界，保持 PREFLIGHT_BLOCKED。**

## 实际调用链

项目配置为 `work/operational-20261113-7adadd47/model.json`，请求目标 `http://127.0.0.1:8788/v1/chat/completions`；模型 A `deepseek-v4.1-flash`，模型 B `kimi-k3-1`。不是 DeepSeek/Kimi 原厂 endpoint。客户端使用 Python 3.12 的 `urllib.request`，无供应商 SDK、无显式 API 版本头；OpenAI-compatible JSON 不能证明与原厂计量协议等价。

本机监听进程 PID 39472 的可执行文件是 `D:/software/wb-proxy/python/pythonw.exe`，启动脚本路径确认是 `D:/software/wb-proxy/wb_proxy.py`。磁盘 README 标示 WorkBuddy2API-Hub v1.10.7；这只是本机文件标示，不证明进程加载字节版本或上游 API/模型修订版。两个模型名均在本机 catalog 中，但没有证明最终原厂版本与直连 API 相同。未读取 accounts、settings 或令牌文件。

本机只读证据及文件 SHA256：`8788-token-provider-local-audit.json`。关键位置：

- `wb_catalog.py:103`、`:1180`：两个别名，声明支持图片和上下文/输出规格；catalog 规格不是本轮 300000 Token 服务端硬额度。
- `wb_proxy.py:14257` 附近：可能插入系统提示，客户端文本计数不是最终上游输入的完整计数。
- `wb_proxy.py:16923` 附近：在某条上游 usage 缺失/零值的响应转换路径，用 `estimate_tokens` 回填 prompt/completion/total。不能证明每次请求一定触发，也不能证明每次数字 usage 都来自供应商。
- `wb_proxy.py:1330` 附近：缓存字段别名归一；需辨明包含关系，不能把别名重复相加。

本轮未改动网关源码，也未运行它的探测脚本或限额配置。

## 实际链路能力矩阵

状态枚举严格使用任务书定义。表中 UNKNOWN 表示当前链路缺少可核实保证，不等同于宣布原厂不支持。

| 能力 | A：WorkBuddy / deepseek-v4.1-flash | B：WorkBuddy / kimi-k3-1 | 依据与适用性 |
|---|---|---|---|
| 输入文本 Token 精确计量 | UNKNOWN | UNKNOWN | 网关可能改写/增加输入，原厂 tokenizer 与别名映射未证明 |
| 图片 Token 精确计量 | UNKNOWN | UNKNOWN | 当前转发 API 没有可适用的精确计量承诺 |
| 图片 Token 保守上界 | UNKNOWN | UNKNOWN | DeepSeek 直连存在文档上界，但不能跨链路套用；Kimi estimator 不足以证明当前链路上界 [1][4] |
| 输出 Token 硬上限 | UNKNOWN | UNKNOWN | 项目发送 max_tokens=8192；参数透传不构成当前上游执行保证；原厂定义见[2][3] |
| 单次总 Token 硬上限 | UNKNOWN | UNKNOWN | 未找到适用于该网关/别名的覆盖输入、图片、推理与额外开销的保证 |
| usage 完整性/来源 | UNKNOWN | UNKNOWN | 有估算回填代码；仅三个整数相加正确不能证明原厂实际用量 |
| 失败请求 usage 是否可查 | UNKNOWN | UNKNOWN | 没有已核实的逐请求状态/计费查询机制；本轮没有调用相关 API |
| 项目/API Key 服务端硬消费上限 | UNKNOWN | UNKNOWN | 没有核实当前账号、地区、Key、即时执行及超额窗口；积分不是 Token [5][6] |
| 超限服务端行为 | UNKNOWN | UNKNOWN | 本轮 24/300000 是客户端策略；公开企业积分耗尽说明不能证明本 Key 的 Token 硬限额 |
| 图片缩放/tile/crop 计量规则 | UNKNOWN | UNKNOWN | 未获当前网关最终模型处理规则的可验证合同 |

`TOKEN_CAP_PROVEN=false`；`SPEND_CAP_PROVEN=false`。公开文档没有发现某项保证不意味着功能绝对不存在；本报告只说明当前证据不足以授权严格预算调用。

## 原厂文档：有价值但不能直接迁移的证据

### DeepSeek 直连

[1] [DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/)，适用于文档列出的 `deepseek-flash` / 原厂 Vision API；2026-11-14 阅读。文档原文：**“there is an upper bound of 1024 tokens per image”**。此项在原厂文档范围属于 `DOCUMENTED_UPPER_BOUND`。不能因此将 WorkBuddy 别名的图片上界填成 1024；文本、额外提示和计量来源仍未证明。

[2] [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)，当前公开 `/chat/completions` Schema：`max_tokens` 限制生成长度；`total_tokens=prompt_tokens+completion_tokens`，命中/未命中缓存合计为 prompt，推理/安全明细包含于 completion，不能重复加。适用直连输出参数的状态为 `DOCUMENTED_HARD_LIMIT`，不构成输入+输出的本轮总额度保证。

[7] [Token & Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/)：提供离线 tokenizer，但通用字符比例及图片 calculator 是估算，不保证当前网关改写后的完整计数。估算算法不进入硬预算放行条件。

### Kimi 直连

[3] [Kimi Chat Completions](https://platform.kimi.ai/docs/api/chat)，当前 Schema 举例为 `kimi-k3.1-pro` / `kimi-k3`，不是已证明等价的 `kimi-k3-1`。`max_tokens` 已标 deprecated，`max_completion_tokens` 限制输出；缓存读/写已在 prompt 中，推理及答案已在 completion 中。直连输出参数为 `DOCUMENTED_HARD_LIMIT`，不能直接证明当前代理的执行语义。

[4] [Kimi Estimate Tokens](https://platform.kimi.ai/docs/api/estimate)：文档提供含图片的预估请求和返回值，没有在本次阅读页面找到对本地别名、代理隐藏输入及所有开销的保守上界保证。对本轮用途归为 `ESTIMATE_ONLY`。本轮未访问该 API。

### 当前转发产品公开说明

[5] [WorkBuddy 积分说明](https://www.codebuddy.cn/docs/workbuddy/Credits)：积分随模型定价和任务复杂度变化，不能直接换算成固定 Token 硬额度。

[6] [WorkBuddy 企业购买/用量管理](https://www.codebuddy.cn/docs/enterprise/price/Purchase)：描述企业成员积分耗尽后的限制；没有证明本机转发 Key 的 Token 计量等价性、即时生效或最后一请求不超额。未将其标为本轮有效资金硬保护。

## 本地图片与全局预算结论

现有代码发送原像素尺寸 RGB JPEG、quality=95，以 base64 `image_url` 传输；没有设置 detail。每次还可能携带既有 OCR crop、highpass 拼图或同组六张图中的参考图，均逐张记入预算输入数量。原图、辅助图和编码方式未修改，未新建商品整改图。

两个实际路由的 text/image/other/overhead/output 上界均使用 `null/UNKNOWN`，不是 0。24 次最坏情况总 Token 为 **UNKNOWN**，不是历史均值乘 24。当前不能严格证明总量≤300000。

可选后续路径：取得当前链路可核实的模型版本、最终请求计量及有来源的 usage，连同单请求总 Token 限额或完整保守上界；或另行配置有完整合同的直连 Provider 并重新验收。它们均需额外实现/核验；本轮没有换接口、探测模型或启用真实调用。
