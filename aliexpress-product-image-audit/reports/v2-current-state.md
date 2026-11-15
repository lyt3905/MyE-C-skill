# V2.0 当前状态审计

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

完整目标仍未完成：G/H真实阶段、独立人工真值和生产门槛缺少证据。当前代码已补齐多处本地主流程缺口。

HEAD 20ecfe83e307bbe15e7e298954a7c57d90dcdca6，分支 codex/8788-contract-local-fix-20261114。保留全部已有修改，未git add/commit/push，单Agent。初轮435份源快照及续作482份源码/报告快照分别保存在 work/v2-local-20261115/baseline 与 work/v2-followup-20261115/baseline。历史433+11份文件复核未变。

run和full-audit默认进入V2统一视觉链，legacy需显式指定。原调度、JobManager、JudgeClient、BudgetManager、编译器、执行器、账户锁和幂等账本继续复用；没有另建一套架构。

新增修复：上传地址解析后的SKU回读、引用专用图片修复/删除、删图同步SKU重绑、最后包装证据保护/保留图片SHA回读、缺少实际SKU ID时保持原引用并继续独立主图修复、两张无盒候选实际进入images.sku池、配置式图像编辑适配器、LaMa两种TorchScript契约、RGBA mask外透明度保护。

完整LaMa权重仍未发现，默认缓存只有两份.partial；实际编辑服务/能力未核实。配置入口及Fake适配器通过不代表这两项已真实可用。依赖版本见 v2-followup-local-runtime.json。
