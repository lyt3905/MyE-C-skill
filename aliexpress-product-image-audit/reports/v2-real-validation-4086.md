# PID4086真实审核与图片整改

日期：2026-11-15（Asia/Shanghai）。Shop7 / shana1，PID4086。新授权：“授权完整图片整改及写入”。真实Job：JOB_eefd545518a7411681bc975ab65a2b9b。

## 当前结论

实际已完成17张独立图片、19处原始引用的审核，以及2处详情图删除、1条有盒SKU图片引用更新和一次保存。图片更新及全部留存引用的字节回读均符合计划。Description不变。

**完整验收未通过：保存接口漏传presale，后端把原true重置为false。** 这是实际非图片字段副作用，不作为成功放行。除此之外仅updatedAt由服务器正常更新；价格、重量、状态、SKU规格与其他业务字段没有检测到变化。

另有1张纯促销文字条保持待复核；模型建议DELETE，但程序因文字归属UNKNOWN未放行。它不是置信度问题，也不在预售恢复提案中追加删除。

## 实际操作

| 项目 | 结果 |
|---|---|
| 真实模型 | 仅deepseek-v4.1-flash，17次，无自动重试，17条有效回复 |
| 原始模型建议 | 14 KEEP、3 DELETE |
| 最终独立图片决策 | 14 KEEP、2 DELETE、1 REVIEW |
| 删除 | 原详情第2张黄色“购买须知”；原详情第12张售后/买家说明整页 |
| 保留待复核 | 原详情第1张红色促销文字条，TEXT_OWNERSHIP_UNRESOLVED |
| SKU | 有盒SKU引用原主图第1张实际有盒素材，无盒SKU引用保留；原无ID行以整行哈希绑定 |
| 图片池 | 主图5→5，详情12→10，SKU池0→1 |
| 实际上传 / 保存 | 0 / 1 |
| 局部去水印 / LaMa / AI重绘 | 本商品NOT_RUN，没有REMOVE_TEXT候选；AI重绘按用户要求后置 |
| Token | 116355，17次usage均可用；仅记录，费用null |
| 独立回读 | 18处当前图片/引用字节全部通过，SKU引用精确匹配；Description精确；非图片保护失败：presale |

## 差异与修复

- presale：执行前true，保存后false。SiteWriteClient与Site.save的原字段白名单都没有此字段，保存接口对缺失字段使用false默认值。
- updatedAt：2026-10-31T14:09:21→2026-11-15T20:36:47，为服务器保存时间。修复后的验证器仅将这一时间字段单独记录，不排除presale或其他业务字段。
- 已完成本地修复：现有两层保存接口都按原值、原类型透传presale；没有该字段时不凭空新增。没有放宽对presale变化的检查。
- 本地201项相关回归通过（0失败/错误/跳过），运行ID a7369030a9e44f6b86f3c561cce046e9；源码绑定前后一致、网络尝试0。原真实执行时仍绑定上一版194项测试的302份源码，两版证据区分保留。
- 使用捕获的真实图片字节做离线恢复预演：当前presale=false继续判失败；仅恢复为true时18处图片/引用及其他业务字段比较通过。预演不是线上恢复结果。

## 等待独立恢复授权

具体提案：work/v2-presale-wire-fix-20261115/presale-recovery-proposal.md及.json。

仅将PID4086预售开关从false恢复为原true，保留全部已完成图片修改；额外保存一次并独立回读，不再调用模型、不上传、不重新删图，不改变Description或其他业务字段。原授权限于图片整改，恢复非图片字段需单独明确授权；当前尚未执行。

## 证据与状态

- work/v2-real-4086-20261115/run-status.json、execution.log、model-dispatches.jsonl：原运行记录。
- 原Job内full_ai_judgements.json、full_ai_metrics.json、auto_decisions.json、plan.v2.json、save_attempt.json及回读文件：真实证据。
- work/v2-real-4086-20261115/independent-readback.json：原独立回读失败证据，保持原样。
- reports/v2-presale-wire-fix-tests.log、tests-status.json、test-source-manifest.json：本地修复回归。
- work/v2-presale-wire-fix-20261115/recovery-offline-preview.json：离线预演。

真实读取/模型请求/两处删除/SKU引用更新/保存：REAL_VERIFIED。实际局部修复：NOT_RUN。非图片字段保护与完整商品整改验收：BLOCKED，预售未恢复；另1条审核暂缓。旧Job、响应、账本不改写，不commit/push。
