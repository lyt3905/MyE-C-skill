> 0.2.34 起标题改写已加入默认流程。新建配置和当前活动本地策略默认 TITLE_REWRITE=true；明确设false仍可跳过。自动保存总开关不随之开启。下方“默认关闭”的说明属于旧版本。

# 商品流程中的 DeepSeek 标题修改

业务规则仅参考 `aliexpress-product-image-audit/title-rewriter/`。软件自带完整提示词，运行时不读取该目录。通过现有模型客户端、网关和 Job 账本调用 DeepSeek，不使用旧的本地固定词表生成器。

## 启用

在目标商品使用的 `automation.local.json` 中，将已有 `allow_actions` 对象的 `TITLE_REWRITE` 设为 `true`，保留其他动作和配置。支持商品专用配置 `local/products/商品ID/automation.local.json`。

可选策略配置：

```json
"title_rewrite": {"retries": 2, "retry_delay": 1, "confirmed_facts": []}
```

`retries` 为额外重试次数，支持0–5，默认2；`retry_delay` 是首次等待秒数，支持0–30，后续指数退避且最多30秒。与图片审核重试配置独立。401/403等明确凭据错误不重试。标题使用现有 `model.local.json` 的 DeepSeek型号、网关、输出上限和推理强度，以及现有模型密钥。

旧配置继续兼容。示例策略默认关闭标题写入，初始化不会覆盖已有文件或扩大商品权限。启用后仍使用原有 `run.cmd process 商品链接`；`--audit-only` 只生成建议并报告。未知保存使用原有 `--resume JOB_ID` 回读，不重复生成或重发保存。

## 行为

- 店铺4使用 `In Stock`，店铺7使用 `Hot Sale`；完整前后缀、120字符上限、Megatank/Hasbro等规则与参考目录一致。
- 只发送原始标题、现有英文标题、identityJson以及SKU名称/型号；正文、图片、价格和后台凭据不进入请求。没有搜索/图片工具，不冒称已查证。
- 首次格式有效结果即停止，不增加第二轮模型评审。warnings仅记录和展示，不单独阻断标题；生成失败仍保留原题，图片整改继续。失败记录和原始响应保留。
- 用户明确确认的套装等事实可填写到 `confirmed_facts`（最多10条，每条最多2000字符），单独发送并绑定到本次标题证据，不改写源商品资料或历史回复。
- 自动保存只更新 `titleEn`。`modelCode` 作为结果记录，不写型号/品牌，不调用中文回译。其他业务字段继续保护。
- 后台可能自动将正文首节点中明确标记 `shopTitle=true`、`generatedBy=INGEST_POST_PROCESS`、`generatedRole=SHOP_TITLE` 的标题文字由原英文题同步为新英文题。仅回读校验识别这一精确联动；发送正文、输入哈希和历史快照不改写，其他文字、样式和节点变化仍拒绝。
- 标题与图片/SKU整改合并进现有计划，正式整改阶段最多保存一次；七张主图预处理仍是此前独立阶段。
- `title.applied` 只有在保存收据及独立回读确认后才为true；GENERATED不代表已保存。用量缺失仍为null。

完整提示词：[title_rewrite.deepseek.md](../src/mye_c_automation/prompts/title_rewrite.deepseek.md)。原始响应及思考在Job的 `title_generation.json` 和模型账本；控制台只列最终标题、型号、警告和状态。

离线演示 `run.cmd fake --scenario twin --with-title` 使用同一V2主流程、Mock DeepSeek、合并保存和独立回读，不访问真实模型或线上商品。
