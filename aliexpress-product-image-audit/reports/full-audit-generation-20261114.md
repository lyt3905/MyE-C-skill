> 后续已获得授权并完成新版真实只读验收，见 [真实结果](mainflow-real-readonly-5097-20261114.md)。本文件保留原离线阶段记录。

# 自动审核正式入口：最终参数与运行准备

## 本轮优先目标

先保证现有自动审核主流程可用，继续后置自动整改和精度扩展。此次修复承接 [正式入口异常继续处理](full-audit-mainflow-20261114.md)，并修复正式请求参数与历史已跑通六图执行器的差异。只使用 Fake/Mock，无真实请求、无新增审核 Token、无站点访问/商品写入/整改。

## 修改

1. `model_config.py` 为 model-gateway/v1 增加可选 reasoning_effort，限定 low/medium/high；非法类型或值明确拒绝，未知字段和密钥字段仍拒绝。
2. `JudgeClient` 只在配置明确设置时发送该字段，并记录在 metrics；该字段参与配置指纹和 Job 冻结，防止改变参数后复用错误缓存。旧配置不额外发送字段，旧指纹不变。
3. 新增独立示例 `scripts/config/model.gateway8788.mainflow.example.json`：8788 接口、deepseek-v4.1-flash + kimi-k3-1、16384 输出限制、low 推理强度、重试 0。没有覆盖旧示例、本地配置或历史任务。
4. 上一阶段已修复正式审核的模型单项格式错误继续处理，并保留原始响应与模型位置。此次继续保留预算和 UNKNOWN 用量保护，未修改 Prompt、Schema、聚合规则或阈值。

## 验证

新增 4 项 Fake 请求与配置回归：两路请求参数、Job 冻结、旧配置及哈希兼容、非法值拒绝、参数变化隔离指纹。先运行失败复现旧配置不接受 reasoning_effort，再完成实现并转绿。

针对性 64 项通过，耗时 16.313 秒；来源清单 `full-audit-generation-targeted-source-manifest.json` 绑定 266 个文件。新版验收器沿用原逐文件 SHA 校验函数，将 BASELINE 指向这份已通过针对性测试的新清单；旧清单和 661 项测试证据均保持原样。最终完整回归 **665 项全部通过**，0 失败、0 错误，耗时 864.562 秒。测试期间源码未变，网络拦截触发 0 次；真实模型调用、新审核 Token、线上写入均为 0。测试结束后逐项核对当前源码与最终清单一致，266 文件基线和 433 历史证据封印通过；查询旧最终 Job 未改变文件。独立只读代码复核未发现实质问题。完整回归单独记录在 `full-audit-generation-full-tests-status.json`、`full-audit-generation-full-tests.log`、`full-audit-generation-full-source-manifest.json`。

本轮源码不是此前真实审核使用的源码；不得把历史真实结果算作此版模型验收。

## 本机离线核对

`work/full-audit-generation-20261114/offline-environment.json` 只检查文件存在和环境变量是否配置，不读取/输出密钥或登录。

- 已有站点配置：`D:\GitHub\MyE-C-skill\ae-img-audit\cfg.local.json`。
- 当前进程未配置 VLM_API_KEY；真实验收前需由用户在本机配置，不在聊天中传密钥。
- Shop 7 尚无确认模板；保持 REQUIRED_TEMPLATE_MISSING，不声明“无适用模板”来冒充通过。缺模板不妨碍产出不完整的审核报告，但不能宣称审核全部通过。
- 程序仍有 40 次请求、32 张不同图片与 500000 Token 的账本阈值。图片 Token 的可靠供应商上界仍未证明，不能声称严格 Token 硬上限已解决。

## Windows 操作

仅帮助命令，不请求模型或站点：

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\workflow_runner.py full-audit --help
```

仅在用户明确授权新版真实模型验收且本机密钥已配置后执行以下命令；本轮没有执行：

```powershell
& $py .\scripts\workflow_runner.py --root .\work\full-audit-new full-audit --pid 5097 --shop 7 --site-config '..\ae-img-audit\cfg.local.json' --model-config .\scripts\config\model.gateway8788.mainflow.example.json --template-config .\scripts\config\template_config.example.json
```

示例模板配置保留 Shop 7 模板缺失状态。命令只读，不保存、上传、翻译或修改状态；不运行 full_audit_recovery.py，不重启旧 Job。--root 位于 full-audit 之前。应先确认站点仍是 Shop 7；代码也会检查店铺上下文和账号。

预期输出位于新 Job：full_audit_report.json、coverage_matrix.json、full_ai_judgements.json、full_ai_metrics.json、full_audit_evidence_manifest.json、report.md。模型格式异常标为 NEEDS_REVIEW；执行完成不表示所有业务项目有明确结论，也不表示商品合规。

## 尚未验证与回滚

尚未执行新版真实网关/站点只读验收，因此无法保证真实字段返回质量、完整商品真实耗时或最终用量。型号/颜色 UNKNOWN、缺失模板和自动整改仍后置。下一阶段应在授权后用同一件商品只读验证，保留所有新旧证据。

本阶段差异在 `work/full-audit-generation-20261114/task-only.diff`，原文件在同目录 baseline。只撤销对应差异即可回滚，不对共享仓库整体 reset；保留所有历史与新测试证据。未提交或推送 GitHub。
