# DeepSeek单模型与同款判断仅记录

日期：2026-11-15（Asia/Shanghai）。HEAD：756873e26235920669af3950222f89e66ae5fdb6；分支codex/8788-contract-local-fix-20261114。保留本轮开始前全部未提交修改。没有暂存、commit或push。

## 本轮实现

1. 型号是否可见、型号/结构/配色是否匹配、same_product_as_context以及field_confidences.product_identity均仅记录。程序不要求YES或0.80，不伪造未知值或提高分数，SKU候选资格同步取消这些条件。
2. V2初审与整改后质量复核均仅选择DeepSeek。默认JudgeClient和三个正式网关示例切为单模型；旧双模型配置仍可读取以保留历史兼容，但V2不会调用MiMo、备用模型或二次观察。MiMo在实际模型HTTP派发边界被禁用。
3. 提示词明确同款观测不决定动作，不因这些观测降低动作置信度；记录原始字段及实际分数。归属未知文字仍默认保留，动作置信度仍至少0.80。
4. V2报告和协议记录实际单模型，不将配置过但未调用的MiMo冒充已审核。删除执行证据同步单模型要求，避免审核通过却被旧双模型数量检查挡住。
5. 整改质量复核仍比较候选与SOURCE，确认没有改坏原图结构、颜色、包装、印刷和署名；这是编辑质量保护，不是与商品资料的同款匹配。Description及所有非图片字段保护、独立回读保持有效。

## 验证证据

- 新增tests/test_v2_deepseek_only.py：单模型、历史双模型配置不触发MiMo、初审和质量复核、派发禁用、同款字段低分/NO/UNKNOWN原样留存、SKU及完整Fake修复上传保存回读。
- 旧双模型业务断言按用户新要求改为单模型断言，保留低动作置信度、明确REVIEW、非法区域、受保护文字、包装不确定、修复损伤、未知保存与Description/SKU回读等测试。历史legacy算法测试显式使用Fake双模型配置，不依赖当前正式默认值；未删除或跳过测试。
- 修改前的新增测试失败日志、改造中旧契约失败日志均保存在work/v2-deepseek-only-20261115；不将中途失败算作通过。
- 全量离线测试860项通过，失败/错误/跳过均0，耗时641.765秒，测试期间源码未变，网络尝试0。运行ID：29ef0f03c05949b99dc4a4c87446e3f4。状态：reports/v2-deepseek-only-tests-status.json；原始日志：reports/v2-deepseek-only-full-tests.log；源码绑定：reports/v2-deepseek-only-test-source-manifest.json。旧842或136数字不冒充本轮结果。
- 额外保留完整Fake证据JOB_aa5290595a7a4b0e95f65873e19634a1：同款为NO、结构/配色UNKNOWN、同款字段置信度0.20时，仍完成本地修复、模拟上传1次、模拟保存1次及独立Fake回读。图片初审和候选复核仅DeepSeek，Description与非图片字段不变；结果PARTIALLY_AUTO_FIXED，保留平台单URL引用限制，不冒报完整生产成功。入口work/v2-deepseek-only-20261115/retained-fake-result.json。

## PID5097旧回复离线复算

原真实Job JOB_14123e2084e941f1a5bfb4ef098dd6e6不变。新离线Job JOB_ba39ae4d8f084601a51bb7d613bc4da8仅重放原有5份DeepSeek回复，5份有效，全部KEEP；动作置信度依次0.80、0.80、0.85、0.92、0.85。

此次没有重新调用模型，没有线上访问、上传或保存。历史MiMo超时/分歧不参与新结果，原始证据仍完整保留。保留不等于执行整改：没有删除或擦除计划，也没有将新提示词视为已做真实供应商验证。

证据：work/v2-deepseek-only-20261115/offline-replay-result.json、offline-replay.log及新Job的replayed-decisions.json。离线重放usage不能累加为新增费用。

## 交付状态

代码与提示词：IMPLEMENTED / FAKE_VERIFIED，860项完整回归通过。新提示词真实验证和本轮真实商品写入：NOT_RUN。完整生产整改验收不因本次离线KEEP而标为PRODUCTION_READY。

本轮增量Diff：reports/v2-deepseek-only.patch，基准为本轮开始前的工作区副本；交付清单：reports/v2-deepseek-only-manifest.json，修改文件列表：reports/v2-deepseek-only-modified-files.json。补丁只在临时副本检查应用并逐文件比较，不修改Git索引或工作分支。
