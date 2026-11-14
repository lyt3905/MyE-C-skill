# 当前工作区基线

- 源码目录：D:/GitHub/MyE-C-skill/aliexpress-product-image-audit；相邻 ae-img-audit 提供现有 Windows Python 虚拟环境。
- 起始 HEAD：b84cc545ff94057bba5bafbebc3a090d3d32abe1。工作区已有大量未提交修改与未跟踪开发模块；未覆盖、删除或用 ZIP 替换这些内容。
- 最初系统 Python 缺少依赖，原始失败日志保留。后使用相邻 .venv 在 Windows Python 3.12 执行完整 unittest。
- 最早完整 Windows 日志 auto-v1-windows-baseline.log：125项、4处失败；该次已含初步缺池修复，不能称为完全未改动基线。
- 保留原测试，并针对新任务的必需池/零空保存要求补齐旧夹具与断言。当前完整结果见 auto-v1-current-regression.log。
- 生产写站路径：Workflow→独立候选质量→本地Policy→compile_auto_plan→live_dry_run→LocalExecutor→ExecutorService→SiteWriteClient→_SiteTransport.save(autoSave=true)。未在开发测试中连接生产试写。
- 状态/发布不在自动计划白名单；保存前后均对状态与保护字段检查。翻译为单独受限API路径。
- 自动执行仍在开发验收中，完整缺口见 auto-v1-implementation.md 末尾，不能把绿测试等同全部需求完成。
