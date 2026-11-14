# Windows验收与回滚说明

在PowerShell中进入仓库根目录：

```powershell
Set-Location D:\GitHub\MyE-C-skill\aliexpress-product-image-audit
$env:PYTHONPATH='scripts;tests'
..\ae-img-audit\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

只验证单件Canary包装器，默认为Fake，不登录站点、不调用模型：

```powershell
..\ae-img-audit\.venv\Scripts\python.exe work\auto-remedy-goal-20261113\snapshot_canary.py
```

读取已通过的预演报告：

```powershell
Get-Content work\auto-remedy-goal-20261113\reviewed-snapshot-v2-jobs\JOB_754f9da4704b4f1f9f3536a5fe61241b\report.md
```

专用配置示例位于work\auto-remedy-goal-20261113\snapshot-preview-policy.json，其中enabled=false、allow_snapshot_sku_rows=true，仅允许Shop7/PID5097的SKU_ASSIGN。默认全局配置未修改。canary-start-confirmation.example.json的confirmed=false，绑定当前源、目标及预演计划SHA；仅供审核，不自动启动。

用户明确启动后才生成匹配的确认文件、提供本地VLM_API_KEY环境变量，并由snapshot_canary.py --execute --confirmation执行。脚本在确认前不会实例化生产Writer；每个执行目录只启动一次，结束后关闭专用执行策略。禁止通过删除当前运行指针、预算、账本或Job重试。

## 商品回滚

本轮已完成一次真实保存，结果验证通过，未执行回滚。保存前、预期及回读快照保存在JOB_7d4f999a45e64242b2e405b47c1bfc18。已额外生成真实只读回滚预演及confirmed=false的示例确认文件，恢复范围仅images与skus，未触发保存。

若写入结果未知，先用现有recover-readback只读核查，不再次保存，也不直接回滚。只有能确认当前状态与已记录写后状态一致时，才用rollback-preview生成恢复方案。预演及恢复都绑定Shop、PID、原计划及源状态；恢复需要该次明确的绑定确认。

实际单件的只读恢复预演命令：

```powershell
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py rollback-preview --job JOB_7d4f999a45e64242b2e405b47c1bfc18 --site-config ..\ae-img-audit\cfg.local.json --root work\auto-remedy-goal-20261113\canary-jobs
```

预期恢复第0行SKU图片及images.sku新增引用；不删除上传资产，本次本来也不上传。已有价格输入、Description及库存等保护继续有效。服务器派生金额可能重新计算，不能承诺用未知接口强制恢复派生值；若当前状态不匹配或保护字段有冲突，停止并核查。

Fake已验证恢复原状态只增加一次保存，重复回滚、未知写入及并发修改会拒绝执行。代码回滚应只撤销本轮列出的文件修改，保留其他用户工作；不得对工作区执行reset/clean。
