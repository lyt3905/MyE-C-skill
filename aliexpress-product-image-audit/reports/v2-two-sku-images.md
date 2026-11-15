# 两张无盒图片分配两个现有SKU

日期：2026-11-15（Asia/Shanghai）。HEAD：756873e26235920669af3950222f89e66ae5fdb6；保留原分支、既有修改与所有历史证据。不暂存、commit或push。

## 用户规则与实现

没有包装盒照片时，系统选出两张不同且合格的玩具照片，可以分别绑定现有“无盒”和“有盒”SKU。每行SKU仍只有一个图片URL，平台无需支持单SKU多图。

复用现有sku_assignment.select_v2与既有Plan、上传、保存和回读模块：

- 存在一条无盒、一条有盒规格时，分配两张不同照片；已有合格且不同的引用优先保留。
- 真实ID映射与明确启用的无ID整行哈希映射均支持两行。不会添加SKU、伪造ID或修改规格/价格。
- logical_sku_group记录目标购买规格；source_retail_box_status保留图片真实ABSENT观测。不是把无盒照片谎报为有盒照片。
- 第二张已经绑定另一个SKU时，不再添加SITE_SINGLE_IMAGE_REFERENCE暂缓项；单SKU、图片不足、未知/重复规格等情况不伪造第二条分配。
- 两张候选继续进入图片池，修复上传后的URL分别写入两条引用。原有真实盒照分支保持有效。
- 仍仅DeepSeek，0.80动作门槛，同款字段仅记录，Description及非图片字段保持原值原类型。

## 验证

新增tests/test_v2_two_sku_images.py共7项，覆盖规格顺序、已有不同引用保留、无ID两行哈希、缺图不重复、两条引用保存与回读，以及两张修复图片上传后的实际引用替换。修改前6项失败；修改后全部通过。

本次相关回归186项通过，失败/错误/跳过0，耗时52.781秒；范围为全部V2测试、snapshot_sku、三个现有编译器测试模块和完整审核整改桥接。不是重新执行整个项目全量回归。运行ID：92f6e5d9b198453fb22a373328ea07b6，测试期间源码未变，网络尝试0。

本地测试驱动初次多填了一个不存在的测试模块名，产生一次ImportError，未计为通过；原日志保留于work/v2-two-sku-images-20261115/tests-initial-runner-import-error.log，修正驱动后完整执行上述186项。

原平台兼容测试同步新业务要求：从只验证第一行赋图，改为验证两行赋图，同时严格比较名称、价格、originalBox等全部非图片字段。保留原文件副本、已有断言和失败证据，不删除或跳过测试。

## 保留的Fake闭环

| 场景 | 模拟上传 | 模拟保存 | 独立回读 | 结果 |
|---|---:|---:|---|---|
| 有真实ID，两张KEEP图 | 0 | 1 | 通过 | AUTO_VERIFIED |
| 无ID，两行哈希绑定 | 0 | 1 | 通过 | AUTO_VERIFIED |
| 无ID，两张局部修复后赋图 | 2 | 1 | 通过 | AUTO_VERIFIED |

三种场景均两条SKU图片引用不同，原SKU属性和Description不变。证据入口work/v2-two-sku-images-20261115/retained-fake-results.json，完整Job、计划、修复候选、回执及独立快照保存在retained-fake子目录。这些均为Fake，不是线上商品验收。

## 状态与交付

IMPLEMENTED / FAKE_VERIFIED。真实商品执行本次分配规则：NOT_RUN。新增真实模型请求、线上访问、上传和保存均0。原真实Job、响应、账本和旧报告保持原样。

- reports/v2-two-sku-images-tests.log、tests-status.json、test-source-manifest.json：本次回归与源码绑定。
- reports/v2-two-sku-images.patch：相对本轮开始前工作区副本的Git增量，临时副本应用并逐文件复验。
- reports/v2-two-sku-images-manifest.json：交付哈希清单及历史证据校验。
