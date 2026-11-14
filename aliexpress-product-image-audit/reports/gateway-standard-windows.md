# 新网关标准入口：Windows运行、配置与回退

仅用于本轮授权的真实只读验证。标准入口是 scripts/workflow_runner.py；不需要运行临时单模型探测脚本。没有新增依赖。

## 已有环境

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:VLM_API_KEY) {
    $env:VLM_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host '模型网关密钥' -AsSecureString)).Password
}
```

站点使用已有外部配置 `..\ae-img-audit\cfg.local.json`，模型密钥仅通过环境变量读取。不要把密钥写入下面的模型配置、商品Job或报告。

## 模型配置

静态示例 scripts/config/model.gateway3425.example.json 可复制到本地，内容为：

```json
{
  "schema": "model-gateway/v1",
  "base_url": "http://127.0.0.1:3425/v1",
  "models": ["workbuddy/deepseek-v4.1-flash", "workbuddy/kimi-k3-1"],
  "max_output_tokens": 4096,
  "retries": 0,
  "timeout": 90
}
```

必须有两个不同的模型标识。输出上限为1～16384，重试0～2，超时1～150秒，均须整数。禁止额外密钥字段，URL不能含用户名、密码、query或fragment；HTTP仅允许本机回环地址，远程地址须HTTPS。配置错误在站点登录前拒绝。

本轮真实验收使用 work/gateway-standard-20261113/model.readonly.json，显式输出上限8192、重试0、超时90秒。增大输出上限用于给推理模型留出生成最终答案的空间，不是接口稳定性保证，也不等于每次实际消耗。使用该上限时预算预留同步增加，仍受每件45次模型请求、300000 Token上限约束。完整已知用量与未知用量分别报告，不估算失败调用为0。

模型配置在创建Job时复制并绑定，主审核、独立质量检查和兼容的恢复流程使用同一份冻结设置。修改原配置文件只影响新Job。不同网关/配置的缓存按指纹隔离。未传 --model-config 时保留原模型、原环境配置与默认输出2000的行为。

## 只读预演命令

保持 work/gateway-standard-20261113/policy.readonly.json 的 enabled=false。下面每次创建新目录，并从商品最新状态读取；不重放旧Job，不执行生产上传、保存、翻译或状态修改。

```powershell
$runRoot = Join-Path 'work' ('gateway-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $runRoot) { throw '目录已存在，请使用新的运行目录' }
New-Item -ItemType Directory -Path $runRoot | Out-Null
& $py scripts\workflow_runner.py run `
  --batch 5099,5098,5097 --shop 7 --mode dry_run `
  --site-config '..\ae-img-audit\cfg.local.json' `
  --model-config 'work\gateway-standard-20261113\model.readonly.json' `
  --automation-config 'work\gateway-standard-20261113\policy.readonly.json' `
  --template-config 'scripts\config\template.red-store.screening.example.json' `
  --root (Join-Path $runRoot 'jobs') *> (Join-Path $runRoot 'run.log')
if ($LASTEXITCODE -ne 0) { throw '运行失败，请保留日志与Job后排查' }
```

DEFERRED表示图片、SKU或候选动作仍有未通过项；DRY_RUN_PASSED也只表示预演通过。两者都不代表已经整改或允许批量写入。每个Job的 report.md、report_data.json、image_observations.json、ai_metrics.json 和 quality_metrics.json保留逐项证据；未入队图片不伪称经过模型审核。详情图下载失败、模型超时、低置信、SKU缺标识、SOP冲突均保留具体暂缓原因。

旧Canary配置继续关闭。模型配置本身不授权商品写入；本轮不使用auto_apply。R04的人工整删标签没有解除盒照保护，不能为凑通过率修改is_box或降低置信度。

## 本地测试

```powershell
$env:PYTHONPATH = 'scripts;tests'
& $py -m compileall -q scripts tests
if ($LASTEXITCODE -ne 0) { throw '编译失败' }
& $py -m unittest discover -s tests -v *> reports\gateway-acceptance-local.log
if ($LASTEXITCODE -ne 0) { throw '测试失败，请查看日志' }
```

最终完整回归为487项/255.927秒/OK，compileall退出0；首轮482项及中间485项日志保留为各自版本记录。Fake标准CLI覆盖安全高清替换并保存/回读、HTTP失败、模型分歧和包装保护零写入；Fake结果不计真实整改成功样本。新增策略状态和畸形网关响应的计量修复见gateway-standard-policy-and-usage-fixes.md。

## 停用与回退

新任务省略 --model-config 即回到原默认选择，前提是原网关本身可用；不将旧网关恢复可用作为已验证事实。保留所有带新profile的旧Job，不编辑job.json/binding.json以改模型或重置预算。旧Job的恢复须使用支持冻结profile的兼容版本；不要用更早代码恢复它们。

本轮没有商品写入，无远端商品变更需要回滚。若回退源码，先保留本轮完整文件和证据，再按 gateway-standard-source-changes.json逐项撤回本轮8个已有文件改动和5个新增文件；源码基线为 source-manifest-before-gateway-standard.json，两个后续边界修复前的快照也已保存。禁止git reset/clean、旧ZIP覆盖或删除Job/账本。

接口超时、HTTP错误或usage UNKNOWN时，不自动循环重试、不退款、不清空budget.sqlite。先核查服务和既有调用结果，未知用量继续保持未知；不要通过重置任务绕过保护。
