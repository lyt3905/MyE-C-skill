> 当前提交版本：[SKU 双模型状态一致性修复与验证](reports/sku-consensus-20261114.md)，672项完整离线测试通过。此前真实只读验证累计30次；最新状态补丁通过离线回放，不宣称整件商品审核已全部通过。

> 最新本地补丁：[SKU 输出字段契约修复](reports/sku-output-contract-20261114.md)，668 项离线测试通过。此补丁在下方真实验收之后开发，未追加真实调用，不把旧结果当作新提示已验证。

> 最新真实只读验收：[Shop 7／5097 结果](reports/mainflow-real-readonly-5097-20261114.md)。新版正式入口完成 28 次请求并生成全量报告，27 次通过格式校验、1 次异常不中断；业务审核仍不完整，商品未修改。下方离线阶段记录保留为历史。

> 最新主流程运行准备：[正式入口参数修复、测试与验收命令](reports/full-audit-generation-20261114.md)。新增可选低推理强度配置及独立 8788 示例；旧配置保持兼容，真实调用仍需授权。

> 正式商品审核入口加固（2026-11-14）：[模型格式异常继续处理与 Windows 使用说明](reports/full-audit-mainflow-20261114.md)。此次推进到 `workflow_runner.py full-audit`，不局限于历史六图验收器；新版真实模型验收仍待授权。

> 当前优先事项（2026-11-14）：先稳定自动审核执行主流程。现有六张历史图片的只读验收入口为 `scripts/complete_observed_audit.py`，单项格式异常记录后继续，支持本地进度查询；准确率优化、完整新商品接入和自动整改后置。[本轮开发与 Windows 使用说明](reports/audit-mainflow-stability-20261114.md)。下方各轮测试数字和入口说明属于对应历史阶段。

> 当前有效范围：[仅主图、详情图、SKU图；Description原值保护](references/当前有效审核范围.md)。此规则覆盖下文历史Description联动口径。

> 最新状态（2026-11-14）：[单件全量审核结果与未完成项](reports/full-product-audit-8788-result.md)。534项完整回归通过；14个语义任务均有双模型结果，两条SKU包装匹配通过，整件商品仍有未确认项，尚未达到完整自动审核验收条件。本轮只读续跑未写商品。下方较早验收记录仅保留为历史。

> 源码溯源更正：[审核清单与GitHub哈希差异核对](reports/full-product-audit-8788-source-reconciliation.md)。历史清单记录Windows原始字节SHA256；GitHub文件应对照核对JSON中的仓库blob哈希。已核对全部233个Python文件：78个字节一致、148个仅换行变化、7个另有末尾空行清理，语法树均一致。该核对不是历史进程已加载模块的运行时证明。

> 8788契约本地修复：[开发报告](reports/8788-development-report.md)、[离线逐图诊断](reports/8788-audit-diagnostics-v2.md)。新版逐标记水印契约和身份五维度仅完成本地Fake/Mock验证；本轮未调用真实模型、未写站、未复用旧授权，也未推送GitHub。

全量只读审核入口为 `scripts/workflow_runner.py full-audit`；获得独立调用额度授权后的补充审核入口为 `scripts/full_audit_recovery.py`。本地网关配置可参照 `scripts/config/model.gateway8788.example.json`，密钥使用本地环境变量，不能写入配置或提交。运行任务、原始回读、凭据和缓存留在本地；GitHub只包含源码、文档与选定测试/结果摘要。

> v1.3 当前验收状态：[真实只读记录](reports/v1.3-real-readonly-canary.md)、[准确率基线](reports/v1.3-audit-accuracy.md)、[功能覆盖矩阵](reports/v1.3-feature-coverage-matrix.md)、[未解决项目](reports/v1.3-remaining-blockers.md)。尚未完成真实Live Dry-run及用户生产Canary，不以Fake通过宣称生产可用。

逐图OCR/CV/模板/残差/模型结果、Token和耗时见Job内image_observations.json；历史记录可离线导出，详见[逐图片记录说明](reports/v1.3-image-observations-guide.md)。缓存、预算阻断与未知用量单独保留，不等同于零Token调用。

# AliExpress 自动审核与整改

复用现有SOP：自动审核、候选生成、独立质量验证、预演、本地授权自动写入和回读。人工只处理不确定及失败异常。开发测试使用Fake/Mock，无生产试写。

## Windows安装与测试

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-auto.txt -r requirements-dev.txt
.\scripts\run_auto_tests.ps1
```

模型网关通过本地环境变量VLM_BASE/VLM_API_KEY配置；站点凭证放local/site.json，不入库。OCR/模型真实质量及站点协议尚未验证，部署前执行只读Canary。

## 审核、预演和自动执行

先参照scripts/config/template_config.example.json填写本地模板适用范围；必需模板缺失不算审核通过。明确无适用模板才能声明no_applicable_shop_ids。

```powershell
$py = '.\.venv\Scripts\python.exe'
$env:AE_READONLY_SITE_CFG=(Resolve-Path .\local\site.json).Path
& $py scripts\workflow_runner.py run --pid 4758 --shop 7 --mode audit --template-config .\local\template_config.json --root .\work\v2
& $py scripts\workflow_runner.py run --pid 4758 --shop 7 --mode dry_run --site-config .\local\site.json --template-config .\local\template_config.json --root .\work\v2
```

复制automation.v1.example.json到local/automation.v1.json；示例默认关闭写入，仍可审核和预演。按实际验收结果设置Shop/PID、动作白名单和预算后，再在本地显式启用；图片新动作未满足质量发布门槛时保持关闭。授权启用后无需逐件确认。擦除/删除/外网找图/盒照补边示例默认关闭；状态不推进、不发布。

```powershell
& $py scripts\workflow_runner.py run --pid 4758 --shop 7 --mode auto_apply --automation-config .\local\automation.v1.json --site-config .\local\site.json --template-config .\local\template_config.json --root .\work\v2
# 验证小批后，用 --batch '4758,4759' 或 --pending 3 替代 --pid。
& $py scripts\workflow_runner.py status --job JOB_xxx --root .\work\v2
& $py scripts\workflow_runner.py report --job JOB_xxx --root .\work\v2
```

上传跨账号共用local/global_upload_rate.sqlite节流，上传完成后至少间隔0.5秒；不删除共享账本绕过限制。每件最多一次保存，未知结果不重发。

## 证据与恢复

Job位于work/v2/JOB_*，保留before/after、计划、上传回执、执行日志和报告。未知保存先recover-readback，内容复检用verify-saved，翻译失败用受限retry-translation（不重新save）。受控商品回退先rollback-preview，检查预案后用绑定确认执行rollback-apply；未知结果只能rollback-readback。

完整命令及限制见reports/auto-v1-deployment-guide.md和auto-v1-migration-rollback.md。测试证据见auto-v1-test-report.md与auto-v1-SOP-coverage-matrix.md；真实环境未验证项目见auto-v1-remaining-blockers.md。

### v1.3 最新验收入口（2026-11-13）

当前真实流程仅通过只读运行，自动生产写入尚未验收。Shop 7用户确认暂无模板，缺项保持暂缓。

- [Windows命令、关闭的Canary示例与回退限制](reports/v1.3-windows-acceptance.md)
- [完整测试记录](reports/v1.3-test-record.md)、[功能覆盖矩阵](reports/v1.3-feature-coverage-matrix.md)
- [主图全局清理验收](reports/v1.3-main-cleanup-acceptance.md)、[未解决项目](reports/v1.3-remaining-blockers.md)

最新价格范围：[沿用采集价及网站派生金额的写后比较](reports/v1.3-derived-pricing-scope.md)。价格不作为商品审核目标，不主动改价；固定Description仍按原值保护，PID324原试写未验证通过。

最新Description范围：[允许站点自动同步顶部生成标题，保留采集正文与图片引用](reports/v1.3-description-header-scope.md)。不新增Description审核或整改；418项完整回归通过，最新状态见reports/v1.3-current-delivery-status.md。

最新标题策略：[不做模型复核，每次自动处理翻译一次](reports/v1.3-title-single-translation-scope.md)；[Shop7/PID3527真实1保存1翻译回读结果](reports/v1.3-single-translation-3527-result.md)。425项完整回归通过，其他图片不确定项继续暂缓。
# V2.0 本地开发入口（2026-11-15）

标准 `scripts/workflow_runner.py run` 与 `full-audit` 默认使用统一视觉决策策略（`--image-workflow v2`），旧内部 Job 和 `--image-workflow legacy` 保持兼容。V2 只处理主图、详情图、SKU 图与真实 SKU 图片引用，不调用 OCR/CV 语义分类，不读取 Description 中的内容。

新增配置样例：`scripts/config/automation.v2.example.json`（执行默认关闭）、`scripts/config/image-options.v2.example.json`（默认 RIGHTS_UNKNOWN）；通过 `--automation-config` 与 `--image-options` 指定。没有素材处理授权时不擦除；没有本地 LaMa 权重或图片编辑后端时明确暂缓。只支持 DeepSeek/MiMo，置信度门槛 0.80，Token 默认仅记录。

站点每个 SKU 目前只证明支持单一图片 URL。无盒分支选两张独立 SHA 的逻辑候选；实际映射首图，并报告未能写入第二张的限制，不假造接口字段或 SKU ID。

本轮只允许离线开发/Fake 测试，未授权运行以上入口连接真实模型或保存线上商品。完整验证结果、限制及后续门槛见 `reports/v2-final-acceptance.md`；真实 Shadow/Canary 本轮均 NOT RUN。

V2续作当前证据见 `reports/v2-followup-acceptance.md` 与 `reports/v2-followup-requirement-matrix.md`；配置式编辑适配器见 `docs/image-edit-adapter-v2.md`。同SKU的第二引用能力尚未核实；两张无盒候选已实际加入既有SKU图片池。真实阶段仍待授权和门槛，不把Fake验收视为完整目标完成。
