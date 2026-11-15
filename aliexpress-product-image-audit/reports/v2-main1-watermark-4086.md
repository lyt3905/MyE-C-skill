# PID4086主图1店铺覆盖字已擦除

日期：2026-11-15（Asia/Shanghai）。shana1 / Shop7 / PID4086。用户明确指出“主图1 这种肯定是要擦除的”，本次按这一确认执行定点局部修复，并沿用该商品已有的图片整改写入授权。

## 真实结果

- 本地完整训练LaMa对真实主图进行局部修复，去除中央“诚品Hobby”覆盖字；未调用外部AI重绘或搜索图片。
- DeepSeek独立比较候选与原图，返回MATCH，五项质量检查均true，实际请求1次、Token2698、费用null；置信度0.98仅记录。
- 真实上传1张PNG、保存1次；主图1、SKU池同源图片、有盒SKU图片引用共3处同步替换。
- 独立登录会话回读：18处当前图片/引用字节全部符合预期，所有SKU与图片字段符合目标，Description及其他业务字段保持不变，presale仍为true。
- 新图片URL：https://image-store-liu.oss-cn-beijing.aliyuncs.com/3ad04fe9-6d0c-44ca-8fec-4d42d10877e8.png
- 候选SHA256：2ecab119a9dc69382a5d3646aa86f1afa1a03c55d0bd55d43a35cf080d58ffbb。

## 局部修复证据

原DeepSeek初审曾因文字归属未知和盒面印刷重叠判KEEP。原始回复、HIGH重叠判断和旧Job全部保留，没有改写为低风险或伪造旧模型结论。

用户明确确认这处文字需要去除后，在对应范围内用像素边界细化字形掩膜。本次不是将整个盒面视为可改区域；最终Mask约占全图3.50%，掩膜外解码像素逐点保持一致。像素处理只用于已确认区域的Mask和修复，不用于商品语义分类。

第一版2.24%掩膜残留红色字边，被本地目视检查拒绝；保存在attempt-01，未上传。扩大到描边及阴影后生成第二版，再通过DeepSeek质量复核，最终使用第二版。

修复区域内部由LaMa补全；掩膜外可证明原像素一致。被水印遮挡的原厂印刷原像素没有独立真值，模型质量通过不等同于逐像素找回被遮挡内容。

## 范围与证据

本次为用户确认后的定点修复，未重跑17张全量审核，未全局放宽HIGH重叠限制，未把所有未知归属文字改为自动擦除。原先详情促销文字条待复核仍保留，没有追加删除。

- work/v2-main1-watermark-4086-20261115/human-instruction.json：当前指令与原图SHA绑定。
- original.png、mask-initial.png、mask-preview.png、LAMA_INPAINT.png、local-repair.json：原图、Mask、最终候选和本地推理记录。
- quality-jobs/JOB_5ac999798af5466684907123e08f54cf：真实DeepSeek质量回复、原始响应及新账本。
- publication-jobs/JOB_f25197862fe943b7b644cecffb8d435a：三处引用替换计划、保存请求、独立快照及18处字节校验。
- publication-status.json：FINISHED，实际上传1、保存1；发布阶段新增模型调用0。

本阶段LaMa实际推理、DeepSeek质量复核、上传、保存和独立回读均REAL_VERIFIED；不能据此宣称通用自动审核已能无需人工确认处理所有类似覆盖图。项目源代码未在本阶段修改，沿用201项测试绑定的303份源码。未commit/push。
