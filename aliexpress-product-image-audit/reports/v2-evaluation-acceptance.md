# V2 离线评估续作验收

完整目标保持进行中。此次补齐了现有离线评估工具，不新增Runner、客户端、账本或站点写入器。

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

12项新增V2测试及旧评估相关测试共17项定向通过；完整回归包含新增测试。空真实数据输出NOT_EVALUATED，五条合成样例输出SYNTHETIC_ONLY。真实样本为0，准确率无分母保留null，所有真实发布统计门槛未满足；release_authorized和real_provenance_independently_verified始终false。

新增能力：跨主图/详情/SKU按SHA去重与冲突拒绝；真实声明样本必须绑定可解码本地图及SHA；五动作分组、REVIEW暂缓、严重错误、修复通过率；包装双向误判与有盒/无盒SKU分组；Fake不能满足真实统计门槛。REMOVE_TEXT定位与修复由人工合并判定，项目通过率不预设。

历史433+11份真实证据重新SHA核对无变化（v2-evaluation-historical-evidence.json）。保留23个Fake Job及1163份证据未改。783项日志及源绑定保留为历史。

尚未完成：真实Shadow、独立人工真值及准确率验收、实际编辑服务/真实修复效果、线上Canary和生产独立审查。当前不调用真实模型、不写线上商品；不使用旧PID5097授权。完整目标未完成，不标记PRODUCTION_READY。

代码变更：scripts/shadow_evaluate.py，tests/test_v2_accuracy.py。说明与样例：docs/v2-offline-evaluation.md，work/v2-evaluation-20261115/datasets/。Git增量及交付哈希：v2-evaluation-incremental.patch、v2-evaluation-delivery-manifest.json。无add/commit/push、无子Agent。

## 补丁交付复验

增量补丁已改为Git生成，避免CRLF重复转义和无末尾换行引起的损坏。使用 git -c core.autocrlf=false apply 在隔离临时副本中检查并实际应用，39个目标文件逐字节一致。项目工作区未应用补丁，应用源码及795项测试绑定不变。详见 v2-evaluation-patch-verification.json；无效旧补丁仅保留为 work/v2-evaluation-20261115/incremental-before-packaging-fix.patch 历史副本。
