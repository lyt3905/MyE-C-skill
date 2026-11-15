# PID5097真实验证结果

本轮已按新的明确授权验证shana1 / Shop7 / PID5097。首轮10次真实请求（DeepSeek5、MiMo5），5张独立图覆盖14个业务引用；8条有效输出、1次超时、1条因附加说明字段被原契约拒绝。最终5 REVIEW，没有获准的删除、擦除或SKU变更，因此上传/保存均0。使用独立登录会话重新读取商品和图片，数据与前置快照一致。真实自动整改验收尚未通过。

## 原始运行与费用记录

真实Job：JOB_14123e2084e941f1a5bfb4ef098dd6e6，原源码对应831项测试，运行时297份绑定前后一致。新兼容修复对应842项完整回归通过，失败/错误/跳过0，运行ID 4b5f2bb26c674bcc9dec4ac2f0996535，298份源绑定未变，网络尝试0。两版证据分别保留。

本轮已知网关Token 74353；1次usage未知，总量null，USD费用null；Token仅记录，不据此阻断。离线复算的历史usage不累加为新的供应商消耗。无自动重试、无Kimi、无AI重绘或外部找图。实际10个请求体与账本提示词SHA逐条核对，完整文字位于本轮work/exact-real-model-prompts.json，Description未进入Payload。

| 独立图片 | 原引用 | 首轮结果 | 模型原始建议 | 主要原因 |
|---|---|---|---|---|
| f58ef0242d07 | MAIN_000, DETAIL_000 | REVIEW | KEEP, KEEP | FIELD_CONFIDENCE_BELOW_THRESHOLD, KEY_FIELDS_CONFLICT, MODEL_NOT_DECISIVE, PRODUCT_IDENTITY_UNRESOLVED, TEXT_OWNERSHIP_UNRESOLVED |
| e9a1233b0d4e | MAIN_001, DETAIL_001 | REVIEW | KEEP, None | MODEL_OUTPUT_INCOMPLETE, PRODUCT_IDENTITY_UNRESOLVED, TEXT_OWNERSHIP_UNRESOLVED |
| 4292661510e4 | MAIN_002, DETAIL_002, SKU_001, SKU_ROW_000 | REVIEW | KEEP, KEEP | KEY_FIELDS_CONFLICT, PRODUCT_IDENTITY_UNRESOLVED, TEXT_OWNERSHIP_UNRESOLVED |
| b001256f3778 | MAIN_003, DETAIL_003 | REVIEW | KEEP, KEEP | KEY_FIELDS_CONFLICT, PRODUCT_IDENTITY_UNRESOLVED |
| 0fd90100f20a | MAIN_004, DETAIL_004, SKU_000, SKU_ROW_001 | REVIEW | KEEP, None | MODEL_OUTPUT_INCOMPLETE |

## 为什么没有写入

原始建议主要为KEEP，但身份/配色/文字归属未确认、低置信字段、关键模型差异及输出缺失导致协调器不能放行。现有商品元数据未提供可核验配色，SKU仅区分有盒/无盒且rawSkuJson为空；不能把color_match UNKNOWN或低于0.80补成YES/通过。没有候选就不生成测试性变更或无意义保存。

说明字段兼容修复后，离线重放接纳9条输出，仍5 REVIEW；最后一图从格式原因转为真实身份/归属/字段冲突原因。它是原始响应的离线重放，不是新增真实模型验收，也没有重写原Job、响应或账本。

## 真实平台能力核实

实际API返回两行SKU：no retail box / with retail box，id/skuId/externalSkuId均无有效值，skuImageUrl为字符串。当前实际加载的前端bundle使用原有行或包装组更新skus数组，并为每行渲染一个skuImageUrl；未发现skuImageUrls/skuImages。公开OpenAPI/Swagger地址返回404。证据为本轮platform-public-metadata.json与platform-sku-code-observations.json。该结论限定当前前端和保存协议，不推断所有隐藏后端接口。

已复用snapshot_sku的整行哈希定位接入V2，明确启用allow_snapshot_sku_rows时支持该站点模式，不生成假ID；两张候选都能进入图片池，实际SKU仍一个URL。新真实写入未执行，因为本商品尚无满足图片审核条件的候选。

## 独立回读

新会话重新读取后的状态SHA b994f6e94324be5ffce262f2214648c41a0f685c7875d446765777c7a06538da，与执行前一致。14条图池/真实SKU引用逐项按原始SHA核对；Description原值/原类型、全部非图片字段、全部SKU引用均未变。由于没有上传保存，这证明真实读取、审核记录及未写入期间的数据一致性；不作为写入成功或真实修复质量证明。

## 功能证据等级

| 阶段 | 状态 | 限制 |
|---|---|---|
| 新鲜商品读取、下载、SHA索引 | REAL_VERIFIED | 本商品5图/14引用 |
| 双模型调用与审计记录 | REAL_VERIFIED | 调用已执行，语义通过率/生产准确率未验收 |
| SKU实际协议与当前前端 | REAL_VERIFIED | 单URL、现有行更新；其他后端能力不作全称结论 |
| 新无ID绑定、修复/删除替代引用与强回读 | IMPLEMENTED / FAKE_VERIFIED | 新增11项回归，未产生真实可执行候选 |
| 本商品本地修复与候选AI质量复核 | NOT_RUN | 没有满足0.80与证据要求的整改候选 |
| 本商品上传与保存 | NOT_RUN | 有授权，但无可执行操作，不是权限缺失 |
| 真实AI重绘 | NOT_RUN | 用户明确后置 |
| 完整真实自动整改验收 | BLOCKED | 模型关键判断不确定/冲突，不能冒报AUTO_VERIFIED |
| 生产就绪 | BLOCKED | NOT PRODUCTION_READY |

## 人工标签与下一步

旧标签库47张保留，当前5图匹配3张水印归属标签。它们没有本次完整五动作/身份/配色真值，不能据此把图片判为可自动整改；不要求用户重标已确认的Q/R记录，标签未送入模型。下一步需要可核验的商品身份、配色和文字归属依据，继续使用0.80门槛。当前授权范围仍为shana1/7/5097，其他商品未获授权。

## 交付

- v2-real-validation-5097-result.json：实际调用/用量/逐图原因及前后状态。
- v2-real-platform-compatibility.md：现场代码缺口和修复。
- v2-real-platform-full-tests.log、tests-status.json、test-source-manifest.json：最新完整回归及绑定。
- v2-real-validation-incremental.patch、v2-real-validation-patch-verification.json、v2-real-validation-delivery-manifest.json：本轮增量与校验。

未add/commit/push，不扩大Shop/PID，不改旧Job、真实响应或原账本。
