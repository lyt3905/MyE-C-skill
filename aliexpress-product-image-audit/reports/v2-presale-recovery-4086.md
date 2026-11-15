# PID4086预售开关已恢复

日期：2026-11-15（Asia/Shanghai）。用户新增明确授权：“授权仅恢复预售开关并回读”。范围：shana1 / Shop7 / PID4086，仅presale=false→原true，保留已完成图片修改，额外保存一次并独立回读。

## 真实结果

- 恢复状态FINISHED，真实保存1次，presale已独立读回true。
- 当前图片池和两条SKU引用与恢复前精确一致，18处当前图片/引用字节检查全部通过。
- Description原值原类型、价格、重量、状态、SKU规格及其他业务字段与恢复计划一致；仅服务器updatedAt自然更新时间另行记录。
- 新增真实模型请求0，上传0，删除0；未重跑图片审核，没有重复计算原17次请求的116355 Token。
- 原图片整改结果保留：主图5、详情10、SKU池1；已删除的2张说明图和有盒SKU引用修改未回滚。

## 与原任务的区别

原真实Job JOB_eefd545518a7411681bc975ab65a2b9b执行17次DeepSeek请求、一次图片保存；其原始失败报告/响应/账本及83份文件均保持原样。本次依独立授权额外恢复预售，累计两次保存，不把恢复说成原首次保存已成功保护所有字段。

恢复后的独立内容核验通过，证明已批准的图片计划和预售原值现已符合预期。**仍有1张促销文字条待复核**，本次授权未追加删除它；不把恢复成功当作整件商品审核全部结束。

## 代码与验证

保存漏传presale的修复已通过201项相关离线回归，失败/错误/跳过0，源码绑定303份。恢复执行前逐份核对与测试版本一致。保留原始分数、DeepSeek单模型及置信度仅记录规则。

## 证据

- work/v2-presale-wire-fix-20261115/recovery-authorization.json：本次新增授权。
- recovery-before.json、recovery-desired.json、recovery-independent-product.json：恢复前、批准目标和独立回读。
- recovery-status.json、recovery-execution.log：一次真实保存与最终状态。
- recovery-independent-readback.json：18处字节/引用、Description及业务字段核验。
- verification-copy/：原Job的只读核验副本，另有用途说明；副本不代表新审核、新调用或新增费用，不修改原Job。

当前结论：本次预售恢复及独立回读REAL_VERIFIED。原1条审核待复核继续保留。未暂存、commit或push。
