# P1/P2 回归记录（进行中）

开工基线：Windows Python 3.12，相邻ae-img-audit/.venv；313次/49.652秒/OK，退出码0。旧日志未覆盖，见p1p2-baseline-tests.log。

Phase1 RED：新增scope采集/非法Description/上传回填原值保护测试先出现3失败1错误；计划v2/v3及旧权限测试先出现3失败；直接保存Description覆盖测试先出现2失败。修复后7个新增范围测试通过。

中间完整回归：318次/49.344秒，5失败3错误，退出码1。原始日志p1p2-scope-intermediate-tests.log。涉及旧Description URL联动/批量删图Description变更/六图池审核预期；下一步逐项保留有效业务断言并迁移冲突部分，不能认为完整回归已通过。

代码已收敛审计采集/证据与候选/计划权限和Schema/自动编译联动/最终快照模拟/直接保存原值保护/回滚字段/旧check的Description内容报告。Phase1尚未完成全部执行链验收，Phase2账本和账号绑定待后续。

本轮开发全Fake/Mock，不执行真实商品写入。

Phase1续行：旧联动测试已迁移为Description原值保护/旧动作拒绝，图片和SKU断言保留。批量删图与旧授权专项10项通过；新增audit_one Fake入口证明8图+Description10URL/非法JSON均不额外下载或HEAD；辅助图池不解析但保持不变。9项scope测试全部通过。新完整回归日志p1p2-scope-regression-tests.log正在运行；compileall scripts/tests通过。

Phase1全量回归：322 tests / 49.013秒 / OK，退出码0，日志p1p2-scope-regression-tests.log。未删除或skip旧测试；仅迁移Description冲突预期。

Phase2账本RED：3项新用例复现预留即APPLY_UNKNOWN、缺少prewrite_failed与begin_side_effect状态切换接口，1失败2错误。当前为主动暴露未修缺口，不计作已通过；下一步连通执行器副作用边界和恢复流程后再全回归。

Phase2账本衔接全回归：328次/57.821秒/OK，退出码0，日志p1p2-ledger-intermediate-tests.log。新增GET失败/Shop错误零写入后可新Job受限重试、上传超时未知不可释放、重启保留RESERVED/UNKNOWN防重放；保存超时现有Workflow仍通过。

账号指纹初步：服务端HTTPS地址+auth/me稳定principal ID；缺失/冲突拒绝，用户名或Shop相同不等于账号相同。5项身份与执行器负例已RED/GREEN。Job/Plan可承载指纹，但标准Workflow自动采集/编译/全链绑定尚未接完，不能视为P0账号验收完成。Schema已同步可选指纹字段。
