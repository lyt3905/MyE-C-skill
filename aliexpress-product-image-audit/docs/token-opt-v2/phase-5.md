# Phase 5 Shadow验收
分级OCR、单模型优先和批量请求未启用。需收集固定样本的GLM/Kimi双判、单判及人工标签，比较漏检/误报、实际Token及延迟后决定是否启用。当前无真实对比数据，结论为未验收，不能生成虚构提升百分比。

## 离线 Shadow 工具
`scripts/shadow_evaluate.py samples.jsonl --output report.json` 只读取人工标注、baseline/candidate 的实际测量，不调用模型或网站。模板 `templates/shadow-samples.example.jsonl` 是明确标记的虚构示例，禁止作为验收结果。报告输出漏检/误报数量、实际 token 总数与延迟总和，始终要求人工审核，不自动宣告上线验收。

## 部署审查包
`deployment/New-ExecutorDeploymentReview.ps1` 只生成部署 manifest，绝不创建账户、修改 ACL 或启用服务。manifest 指定独立非管理员身份、受保护代码/凭证/状态目录、拒绝远程连接的命名管道、消息大小和超时上限。默认仅 validate/dry_run，写入关闭。当前已实现 Windows 命名管道服务和消息限制，并通过同机子进程离线验证；独立账号部署、跨用户负向测试和实际文件 ACL 验证仍是激活前阻断项，不得把此审查包当成已部署隔离。

## 离线工具完成与上线门槛
Shadow比较工具 scripts/shadow_evaluate.py 已可离线接收JSONL人工标注及baseline/candidate测量，输出漏检、误报、token和耗时总计；重复样本、非法类型和负数拒绝。报告固定accepted=false、HUMAN_REVIEW_REQUIRED，防止合成样本被当作上线验收。

真实Shadow验收必须由业务提供同一批具有代表性的已脱敏历史商品、独立人工标签，以及实际baseline/candidate运行记录。缺少这些外部输入时，不编造节省比例、准确率或验收通过。离线程序及测试完成与业务Shadow通过是两个独立状态。

迁移顺序：保留v1基线；运行v2 read_only并审阅Shadow；管理员部署隔离执行器且保持enable_writes=false；独立审批端签发短期单次票据；先dry_run，再经业务批准逐步启用写入。回退时停执行器、禁写、恢复v1只读入口，保留nonce数据库和证据日志，禁止删除nonce或复用旧密钥票据。
