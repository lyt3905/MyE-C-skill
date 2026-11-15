# V2置信度仅记录

日期：2026-11-15（Asia/Shanghai）。HEAD：756873e26235920669af3950222f89e66ae5fdb6。保留原分支、全部既有修改和历史证据，不暂存、commit或push。

## 用户要求与修改

所有模型置信度仅记录，不参与放行。正式V2移除了以下数值判断：

| 阶段 | 本次行为 |
|---|---|
| 初审 | 整体、字段、包装、玩具及文字区域分数低，不再转REVIEW |
| 水印修复 | 不因擦除区域分数低拒绝生成Mask；保留有效坐标、重叠和面积检查 |
| 整改质量 | 客户端及Inspector均不以分数决定通过；按MATCH、明确弃权和五项实际质量检查判断 |
| 包装素材留存 | 不因留存包装图的分数低而阻断删除；同款元数据继续按用户既有要求仅记录 |
| SKU选择 | 不以整体/包装/文字分数筛掉候选，也不按分数排序；按类别、尺寸、角度与稳定SHA排序及保留现有合格引用 |
| 准确率统计 | 不因分数低将已有动作改写为REVIEW，仍单独统计明确弃权 |
| 提示词和协议 | 不再要求0.80，明确RECORD_ONLY；新V2协议threshold=null |

原始响应、各字段分数与每个文字区域分数按实际值保留，不提高到0.80、不删除、不伪造。既有JSON字段和数值格式校验仍保留；合法的0.0分不阻断。明确REVIEW/abstain、无法判定的包装、缺少可执行区域、实际修复失败、商品非图片字段变化或回读失败不因此变成通过。

仍仅使用DeepSeek；未知归属文字保留；型号/结构/配色仅记录；无盒A/B可分别绑定现有无盒/有盒规格。当前正式入口共用V2。旧legacy库保留其历史阈值和Fake测试契约，本次未把全局旧阈值设为0，旧Job/真实响应/账本与旧报告没有重写。

## 回归证据

新增tests/test_v2_confidence_record_only.py共8项，修改前出现预期阻断，修改后全部通过。覆盖：0分KEEP/DELETE/REMOVE_TEXT；0分Mask；SKU资格与排序不受分数影响；0分包装选图；有ID/无ID的完整修复、质量复核、SKU分配、上传保存和独立回读；低分不能覆盖明确修复失败；统计不重写低分动作；低分包装留存证据。

相关回归194项通过，失败/错误/跳过0，耗时56.281秒。范围为全部V2测试、snapshot_sku、三个编译器模块及完整审核整改桥接；未重新运行整个项目全量测试，旧860项不冒充本版全量验收。

运行ID：0d1c4c705d5f4dab8232697466dd21e8。测试期间源码未变，网络尝试0。日志reports/v2-confidence-record-only-tests.log；状态reports/v2-confidence-record-only-tests-status.json；源码绑定reports/v2-confidence-record-only-test-source-manifest.json。按新业务规则更新旧低分断言，同时保留明确弃权、坐标非法、保护区域、实际质量失败、非图片字段与回读等回归；未删除或跳过测试。

## 保留的完整Fake任务

| 场景 | 模型分数 | 模拟上传/保存 | 结果 |
|---|---:|---|---|
| 初审、区域、质量、SKU全链路分数均0 | 0.0 | 1 / 1 | AUTO_VERIFIED，独立回读通过，Description不变，两条SKU图片不同 |
| 分数0，但明确原图细节未保留 | 0.0 | 0 / 0 | FAIL_IDENTITY，原图保留，REVIEW_REQUIRED |

证据work/v2-confidence-record-only-20261115/retained-fake-results.json；完整Job、模型模拟响应、原分数、Mask、候选、Plan、回执及独立快照保存在retained-fake子目录。

## 状态与交付

IMPLEMENTED / FAKE_VERIFIED。本轮新增真实模型请求、线上读取、上传和保存均0；真实商品执行新置信度规则NOT_RUN，不冒充PRODUCTION_READY。

增量Diff：reports/v2-confidence-record-only.patch，相对本轮开始前工作区副本，在临时副本应用并逐文件比较；交付与历史证据校验：reports/v2-confidence-record-only-manifest.json。
