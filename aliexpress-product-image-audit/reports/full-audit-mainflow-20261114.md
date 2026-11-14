> 后续参数兼容修复与最终 665 项回归见 [最新报告](full-audit-generation-20261114.md)。本报告的 661 项和源码清单对应上一阶段，原记录保留。

# 正式商品自动审核入口：模型异常继续处理

本轮继续“先尽量保证自动审核主流程可用”，从历史六张图片验收器推进到正式 `workflow_runner.py full-audit` 入口。只修改本地代码并使用 Fake；无真实模型请求、无新审核 Token、无站点访问、无线上写入和自动整改。

## 缺陷与修复

正式入口的 JudgeClient 在第一路模型返回字段/JSON 格式错误后立即返回，导致同一图片的第二路模型未执行。虽然队列会处理其他图片，但丢失第二路证据。

新增可选 `continue_model_errors`，仅正式全商品审核入口默认开启，其他旧调用保持原行为。仅已收到响应后的解析与 Schema 校验异常，保存错误后继续下一模型；不重试格式错误。保留失败模型的空位置并标记 NEEDS_REVIEW，避免把模型 B 误标为模型 A。将原始响应保存在请求 metrics 内，随 `full_ai_metrics.json` 落盘。

截断响应即使包含可解析 JSON 也不能成为有效结论。预算保护、失败扣减、UNKNOWN 用量保护、网络重试政策、水印/身份判断逻辑、置信度阈值保持不变。只在响应解析阶段继续，不将预算结算错误或缓存错误当作格式错误吞掉。

## 回归

- 新增 7 项：A/B 单侧格式失败、空 choices、截断但有效 JSON、预算不足阻止第二路、超时不额外开启第二路、正式入口完整商品集成。
- 正式入口集成使用实际 JudgeClient 与 Fake Transport/Reader/Auditor，覆盖不同图片内容和主图/详情图/SKU 图及 SKU 引用；第一路异常后全部 12 请求位置执行，7 个业务位置都出现在报告，异常仍阻止 audit_complete。
- 针对性 43 项通过；记录：`full-audit-mainflow-targeted-tests-status.json` 与 `full-audit-mainflow-targeted-tests.log`。
- 完整套件 661 项全部通过，0 失败、0 错误，耗时 872.047 秒；测试期间源码未变，真实调用/新审核 Token/线上写入均为 0。测试后源码基线和 433 文件封印再次验证通过。完整套件结果见 `full-audit-mainflow-full-tests-status.json`、`full-audit-mainflow-full-tests.log`、`full-audit-mainflow-full-source-manifest.json`。运行中不修改源码。

## 源码基线与历史证据

旧 `8788-test-source-manifest.json` 和历史证据均未覆盖。两处源码修改正确触发旧基线不匹配。本轮针对性回归运行后生成新的独立源码清单，验证运行期间源码不变，然后将新版验收器的 BASELINE 指向此新清单；逐文件 SHA256 验证函数保持不变，未跳过校验。新清单绑定 run_id `b7d7861f89f54d8ba2105d976191d821`、264 个源码/测试/配置文件。随后另行运行完整套件验证。

这只说明新版本本地回归所覆盖的源码，不表示新代码用于此前真实审核。旧真实执行源码归档、旧 Job 和 433 文件封印均继续保留。

## Windows 入口

正式商品入口如下；本轮未执行以下真实调用命令，需另行明确授权模型调用与只读站点访问：

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\workflow_runner.py --root .\work\full-audit-new full-audit --pid 5097 --shop 7 --site-config .\local\site.json --model-config .\local\model.json --template-config .\local\template_config.json
```

注意 `--root` 位于子命令 `full-audit` 之前。密钥用本地环境变量，不写入报告、配置或 Git。请使用实际已核对的本地配置路径。不得以新建空模板声明来冒充已确认无适用模板。

固定预算仍是 40 次请求、32 张不同图片和 500000 Token；预算不足会阻止执行，不能靠此修复绕过预算。Description、价格与标题复核仍排除。缺失图片、模板、型号或颜色证据均可导致报告有 UNKNOWN，不能以完成执行宣称商品合规。

## 当前边界

本轮正式入口改动只获得离线 Fake 验证，尚未获得新版真实模型验收。已有真实调用结果属于旧源码。真实双模型能否稳定返回完整字段、网关用量与账单一致性、模板缺失以及身份 UNKNOWN 仍未消除，自动整改继续后置。下一项主流程核对是正式入口的请求参数：历史六图执行器已使用 reasoning_effort=low 和 16384 输出限制，而正式网关配置示例仍为 8192，需在下一步以兼容方式检查这一差异，不能因为本轮 Fake 通过就宣称真实空输出问题已解决。

回滚只对照 `work/full-audit-mainflow-20261114/task-only.diff` 撤销本轮差异；原文件快照在同目录 baseline。保留新旧测试证据与历史审核文件，不对整个仓库执行 reset。未提交、推送 GitHub。
