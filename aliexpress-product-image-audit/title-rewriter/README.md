# 本地 DeepSeek 批量标题重写

脚本：`rewrite_titles_deepseek.py`。读取本地商品资料，真实调用 DeepSeek 生成英文标题，结果只存本地 JSON，不登录店铺、不保存商品，也不执行中文回译。

## 快速运行

把整个 `title-rewriter` 文件夹放到任意位置，在此文件夹中打开 PowerShell 运行：

```powershell
$env:VLM_API_KEY = '填入你现有网关的密钥'
python rewrite_titles_deepseek.py --input products.example.json --output results.json --workers 4 --retries 2
```

默认复用当前项目的 `http://127.0.0.1:8788/v1` 兼容 API 和 `deepseek-v4.1-flash`。需先有正在运行的模型网关；这里不是店铺地址。也可设置 `DEEPSEEK_API_KEY`，它的优先级高于 `VLM_API_KEY`；或用 `--api-key-env MY_KEY` 指定环境变量。

已有模型配置可直接复用：

```powershell
python rewrite_titles_deepseek.py --input products.json --output results.json --model-config model.example.json --workers 4 --retries 2
```

`--base-url`、`--model`、`--timeout`、`--max-tokens` 可覆盖配置；不指定配置时地址也读取 `VLM_BASE`。沿用项目已启用的 `deepseek-v4.1-flash` / `workbuddy/deepseek-v4.1-flash`，未新增官方 `deepseek-chat` 等型号支持。并发/重试由本脚本参数决定，不采用旧图片审核配置中的串行/零重试行为。只需 Python 3.10 或更新版本，全部使用标准库，无需安装第三方依赖，也不依赖原项目。模型网关及密钥仍需自行提供。

## 商品输入

支持 JSON 数组、`{"products": [...]}`、单个商品 JSON，以及一行一个商品的 `.jsonl`。参见 `products.example.json`。

```json
[
  {"id": 3527, "shopId": 7, "title": "NewAge NA-H74 威震天 小比例 变形玩具", "identityJson": {"modelCode": "NA-H74"}}
]
```

- `title` 必填，指原始标题；不会修改输入文件。
- `shopId` / `shop` 为 4 或 7，也可用 `--shop 7` 统一指定，4 对应 `In Stock`，7 对应 `Hot Sale`。
- 可提供 `titleEn`、`identityJson`、`skus`（只传名称和型号）；Description、图片、价格等不发送。
- `id` / `pid` 仅用于标识结果，不会据此读取线上商品。

## 执行行为

- 默认4线程；`--workers 8` 可改为8线程。
- 默认失败后最多额外重试2次，即每件最多3次请求。网络超时、429、5xx、空回复/截断/错误格式等会重试；401/403等明确凭据错误直接记录失败。重试间隔默认1、2秒，可用 `--retry-delay` 修改，单次等待最多30秒。
- 第一次有效结果直接采用，不重复生成、不做第二轮模型评审。检查 JSON、120字符、店铺前后缀等基本格式，不声称自动证明了角色/商品语义正确。
- 每件完成立即更新结果文件，顺序与输入一致。再次运行同一命令，跳过输入、提示词和请求配置未变的成功结果，只重新处理失败/未完成项。同一批相同内容仅调用一次。
- 完整提示词或商品内容、模型地址/型号、输出设置改变会重新生成。希望整批重生成时使用新的输出文件。输出文件用于当前批次，换输入批次请换输出路径。
- Token usage 按实际回复保留，缺失为 `null`；`calls` 保留每次调用的回复/状态，失败记录不被后续成功覆盖。
- 不确定项位于 `warnings`，有警告仍保存结果供查看；`SUCCEEDED` 仅表示取得格式有效的生成结果，不等于商品业务审核通过。

退出码：全部取得结果为0；有失败为1；配置/文件错误为2。

## 提示词

完整提示词集中在 `prompt.md` 一个文件，包含角色、JSON 输出格式，以及从当前 SOP 第1–4节合并的模板、字段规则、完整替换表和字符限制。脚本直接读取此文件作为 system 消息，不再运行时拼接 SOP；打开这个文件即可查看实际发送的完整提示词。后续修改 SOP 时，需同步更新此文件中的相应规则。本脚本没有联网搜索工具；需要外部查证的信息由模型在 `warnings` 中说明，不冒称已查证。

## 本次验证

实现状态：IMPLEMENTED、FAKE_VERIFIED。离线测试覆盖并发、失败重试、首次成功停止、重复内容合并、断点续跑、输入/配置改变失效、HTTP 请求构造及完整 CLI 文件闭环。

2026-11-17：新增14项测试，连同现有标题、网关配置、提示词和 DeepSeek 单模型回归共49项通过；测试期间禁止真实网络连接。原始49项日志位于原项目 reports；本目录独立验证日志见 `verification.log`。此为相关回归，不是全项目全量测试。

真实模型调用：NOT_RUN；线上商品访问/写入：NOT_RUN；PRODUCTION_READY：未声明。单 Agent，未 commit/push。

## 文件清单与独立验证

- `rewrite_titles_deepseek.py`：主脚本。
- `prompt.md`：完整提示词，直接修改此文件即可。
- `api_support.py`、`model_config.py`：从原项目提取的 HTTP、JSON 和配置辅助代码。
- `products.example.json`：商品输入示例。
- `model.example.json`：模型配置示例，不含密钥。
- `tests/`：离线测试。

离线验证：`python -m unittest discover -s tests -v`。

独立性已验证：将整个目录复制到原项目之外，移除 PYTHONPATH，并用 `python -S` 禁用第三方包后，命令帮助及全部14项离线测试通过。证据见同目录 `verification.log`。
