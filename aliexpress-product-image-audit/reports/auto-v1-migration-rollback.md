# 回滚与迁移

部署前备份完整源码、依赖版本及本地配置，保留每个Job的before/after、计划、质量证据、上传回执和执行日志。停止自动执行时禁用本地automation配置并停止后续批次，不删除幂等账本或预算数据库。

代码回退使用部署前完整备份，保留运行证据。当前工作区原先已有修改与未跟踪代码，不可用git clean/reset整体回退。

商品回退是一次新的写入。工具先读取当前商品并生成绑定当前哈希的预案；仅恢复原任务修改过的内容字段，保护状态、价格、重量等字段。原始状态本身不满足结构规则时拒绝恢复。未知保存必须先获得匹配的只读回读，状态漂移拒绝执行；禁止盲目重发。回滚保存最多一次，失败后只能只读核对。

```powershell
$py = '.\.venv\Scripts\python.exe'
& $py scripts\workflow_runner.py rollback-preview --job JOB_xxx --site-config .\local\site.json --root .\work\v2
# 检查Job内rollback预案及生成的确认示例；显式确认后另存确认文件。
& $py scripts\workflow_runner.py rollback-apply --job JOB_xxx --site-config .\local\site.json --confirmation .\local\rollback-confirmation.json --root .\work\v2
& $py scripts\workflow_runner.py rollback-readback --job JOB_xxx --site-config .\local\site.json --root .\work\v2
```

回滚成功仅表示恢复原快照，不表示原商品通过SOP；需重新审核。标题翻译单独处理。Fake演练覆盖恢复一次、重复执行拒绝、状态漂移及未知写入拒绝（test_auto_controlled_rollback.py）。本轮没有生产修改，也未验证生产回滚。
