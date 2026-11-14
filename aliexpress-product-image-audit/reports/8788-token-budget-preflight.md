# 8788 Token预算最终离线预检

**PREFLIGHT_BLOCKED**

预算持久化、预留及停止机制的Fake测试通过；真实Provider的完整上界仍无法证明，未启用真实模式。

| 检查 | 结果 |
|---|---|
| 配置/本机Provider | WorkBuddy2API-Hub；deepseek-v4.1-flash / kimi-k3-1；远端原厂版本UNKNOWN |
| 输入文本/图片/隐藏提示上界 | UNKNOWN；JSON为null，不填0 |
| 输出限额在实际链路的保证 | UNKNOWN；max_tokens=8192只是一项请求参数 |
| usage来源及完整性 | UNKNOWN；存在估算回填路径，禁止只信数字格式 |
| 24次最坏情况总Token | UNKNOWN / null |
| 300000硬限制 | 保持300000；没有证明24次可安全发送，STRICT拒绝预留 |
| 请求数/并发/重试 | 固定24 / 1 / 0；失败不退次数 |
| SQLite权威账本 | FULL同步原子事务；版本、Job及逻辑校验通过Fake |
| 六原图/16位置/433旧文件 | 核对通过，历史文件未改 |
| 本轮真实请求/审核Token/线上写入/整改 | 0 / 0 / 0 / 0 |

TOKEN_CAP_PROVEN=false；SPEND_CAP_PROVEN=false。未知量不是经验估算；没有扩大额度。

新Job：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\8788-token-budget-preflight-20261114\VALIDATION_20261114T055134Z_665064b053924876b95fb98f2e77388e
新账本：token-budget.sqlite；request_count=0、actual_tokens=0、reserved_tokens=0、unknown_committed_tokens=0、status=PREFLIGHT_BLOCKED。
逐请求依据见新Job/token-budget-plan.json和provider-capabilities.json；上界细项全部保留null/UNKNOWN。

## Windows离线验收命令

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\run_8788_real_validation.py `
  --source-job-dir .\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad `
  --input-manifest .\reports\8788-real-validation-inputs.json `
  --output-dir .\work\8788-token-budget-preflight-20261114 `
  --max-provider-requests 24 --max-total-tokens 300000 `
  --no-retry --no-site-write --preflight-only
```

本次实际exit2/PREFLIGHT_BLOCKED。命令只离线读取配置和既有证据；每次创建新Job，不重启历史Job。

## 仍缺的能力

两条实际路由都缺少：可核实的原厂版本/协议映射、包含图片和网关改写的最终输入上界、输出上限及额外开销保证、有来源的完整usage、可核实的失败计费状态。
原厂DeepSeek有文档图片上界，但未证明适用于当前转发；Kimi估算接口未获当前路由保守上界保证。
需后续取得当前链路保证或另行验收直连Provider；本轮不修改接口、不探测、不调用模型。完成本地报告后停止等待。
