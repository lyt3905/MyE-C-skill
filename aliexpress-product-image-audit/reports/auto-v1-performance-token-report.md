# 性能与Token报告（Mock开发验收）

最新原始测试时长与条数以 auto-v1-current-regression.log 为准。测试包括 Windows Python 3.12、原有回归、图片处理、原生IPC，以及1/3/10件完整Fake Workflow批次。

这些耗时不等于生产单商品延迟：Fake模型/站点消除了真实下载、OCR模型加载、供应商推理和上传网络时间。早期基线测试数量与场景不同，不能计算性能提升或退化百分比。

预算已验证：请求/图像/Token原子预留，任一预算失败全部回滚；预算耗尽零请求且不重试；未知usage按UNKNOWN处理；保存与翻译使用持久独立预算。模型比较图SHA和业务/Prompt/Policy等上下文参与缓存绑定，跨Job缓存路径不会作为业务身份。

没有真实供应商usage，不伪造实际Token数或节省比例。Fake返回的usage只验证账本和UNKNOWN/零值行为，不代表真实消耗。自动阶段指标已由automatic_report合并：run/prepare/apply/verify耗时、质量阶段调用、预算快照、上传与保存计数和usage状态。对应test_auto_report_complete通过；真实环境性能样本未验证。
