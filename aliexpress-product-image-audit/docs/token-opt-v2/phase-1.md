# Phase 1 控制层
依赖：JobManager、BudgetManager、只读audit适配。已增加独立任务目录、状态顺序校验、元数据摘要、失败检查点恢复和预算持久化。验证由tests/test_workflow_v2.py及test_budget_performance_v2.py覆盖。元数据摘要只能检测误改；同用户可改摘要，不是安全隔离。
