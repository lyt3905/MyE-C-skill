# 自动审核主流程稳定性修复

本轮按“先保证自动审核主流程可用”的优先级，收敛修改到现有只读图片验收执行器。未重新设计架构，未调用真实模型、消耗新审核 Token、访问站点、写入商品或执行整改。

## 修改内容

- `complete_observed_audit.run_new()` 直接在一个新 Job 内遍历全部 24 个请求位置，不再依赖创建子 Job 才能越过单项格式错误。
- 已收到响应但 JSON/字段格式错误或输出被截断时，保存原始响应和错误、登记失败并继续其他位置。不重试，不补造字段，不把异常算作通过。
- 超时、HTTP 错误、模型身份不符、输入或源码哈希变化、授权异常、存储失败继续停止。请求唯一性与 24 次上限保持不变。
- 新增 `observed-progress.json`，请求发送前保存进度；报告完成后区分执行完成、执行有异常和所有图片结论是否确定。
- 新增 `--status-job`，只读本地进度或兼容读取旧报告，不创建任务、不改旧 Job、不请求模型。
- 保留低层 `observed_audit.run()` 默认遇错停止的兼容行为；推荐入口显式启用单项异常继续。旧子 Job 续跑代码仅保留兼容，本轮未运行。

## 当前可用范围与后置事项

当前入口绑定 Shop 7 / PID 5097 的六张历史图片、16 个业务位置，执行水印和商品身份双模型任务。它不是任意新商品的完整 SOP 入口，也不代表型号、颜色等 UNKNOWN 已解决。执行完成不等于商品审核通过。

水印/身份 Prompt、Schema、聚合规则、阈值未在本轮改动。Description 不审核；价格、标题复核不纳入本轮。准确率调优、新商品完整接入、自动整改、供应商 Token 上界证明后置。观察模式仍明确标注无 Token 硬上限；严格预算模式没有放宽。

曾尝试增加 workflow_runner 别名，发现会触发历史源码基线保护，已撤回；该文件与本轮开始快照逐字节一致，没有降低基线保护。

## 验证记录

新增回归 8 项，先复现单项异常导致依赖子 Job 的问题，再完成修复：首次聚焦通过 8 项，耗时 64.820 秒。覆盖首尾格式异常、输出截断、UNKNOWN 继续、发送前持久进度、超时停止、模型身份不符停止、默认离线入口、只读状态与旧报告兼容。

完整离线套件：654 项通过，0 失败、0 错误，耗时 617.984 秒；真实模型调用 0、新增审核 Token 0、线上写入 0；测试期间源码未变化，网络拦截触发 0 次。测试后再次核对历史 433 个证据文件，封印保持一致。

完整离线套件结果见 [测试状态](audit-mainflow-stability-tests-status.json)、[完整日志](audit-mainflow-stability-full-tests.log)、[测试源码绑定](audit-mainflow-stability-test-source-manifest.json)。测试进程阻止真实网络；集成子进程使用 Fake 执行器。

离线命令预检已通过：默认创建未启动新任务、读取旧任务状态成功；历史 433 个证据文件封印验证通过，旧最终 Job 查询前后全树哈希一致。记录在 `work/audit-mainflow-stability-20261114/offline-smoke.json`。

本轮修改差异：`work/audit-mainflow-stability-20261114/task-only.diff`（相对本轮开始快照，避免混入之前未提交的修改）。未提交或推送 GitHub。

## Windows 使用

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\complete_observed_audit.py --help
# 仅生成新的离线准备任务，不发出请求
& $py .\scripts\complete_observed_audit.py --output-dir .\work\audit-mainflow-local
# 查看已有 Job，填入实际目录
& $py .\scripts\complete_observed_audit.py --status-job '<Job绝对路径>'
```

未来明确授权真实调用后，执行命令为：

```powershell
& $py .\scripts\complete_observed_audit.py --output-dir .\work\audit-mainflow-local --execute-observed-models --user-statement '<本次真实调用的明确授权>'
```

本轮没有执行上面的真实调用命令。网关密钥使用本地环境变量，不写入报告或源码。任务仍固定六张图片，不能用该命令宣称任意商品全量审核已验收。

## 回滚

仅需要撤销本轮时，从 `work/audit-mainflow-stability-20261114/baseline` 对照恢复 observed_audit.py、complete_observed_audit.py 和 README 的本轮差异，并移除本轮新增测试。不要 git reset 整个仓库；工作区含之前任务和其他项目修改。历史证据、已执行 Job 和此前源码归档均应保留。
