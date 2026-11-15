# shana1 / Shop 7 / PID5085 真实只读审核

2026-11-15；仅deepseek-v4.1-flash，置信度和Token仅记录；无删除、擦除、上传、保存。
正文尾部附加内容按用户要求豁免。正文7张商品图均与详情图片列表逐URL对应，已显式检查覆盖。

23个图片池/SKU业务引用，10份成功读取的不同图片内容；详情图1读取两次均HTTP429，未取得模型结论。因此完整审核尚未完成。
真实模型请求10，Token 92783，费用未知。商品前后状态一致：True。

本次发现一处规则执行偏差：主图1/详情图2原始DeepSeek为KEEP，程序因box_relation=POSSIBLY_SAME_PRODUCT而RETAIL_BOX_UNRESOLVED。该同款关系拦截与用户“同款仅记录”要求冲突；本次如实记录，不伪造为模型REVIEW，不修改源码或覆写原结果。

## 逐张结论

以下同时保留DeepSeek原始动作与程序最终动作；KEEP不代表没有水印。

| 对应位置 | DeepSeek原始动作 | 程序最终动作 | 原始置信度（仅记录） | 程序原因 |
|---|---|---|---|---|
| 主图1、详情图2 | KEEP | REVIEW | 0.78 | RETAIL_BOX_UNRESOLVED |
| 主图2、详情图3 | KEEP | KEEP | 0.62 |  |
| 主图3、详情图4 | KEEP | KEEP | 0.9 |  |
| 主图4、详情图5 | KEEP | KEEP | 0.9 |  |
| 主图5、详情图6 | KEEP | KEEP | 0.96 |  |
| 主图6、详情图7 | KEEP | KEEP | 0.97 |  |
| 主图7、SKU池1、SKU引用1 | KEEP | KEEP | 0.96 |  |
| 主图8、SKU池2、SKU引用2 | KEEP | KEEP | 0.95 |  |
| 主图9、SKU池3 | KEEP | KEEP | 0.87 |  |
| 主图10、SKU池4 | KEEP | KEEP | 0.96 |  |
| 详情图1（正文第1张） | 未调用 | REVIEW | 无 | 图片源HTTP429 |

## 模型原始说明

### 主图1、详情图2

The image is a decorated promotional composite showing four Transformers RED retail boxes across the top and four loose figures below, plus a bottom store/promotional banner reading 'In stock' and 'GK Robot Toy Store'. The product and packaging content is clear and useful, so the image should be retained. Retail packaging is visibly present but shows multiple characters from the line, making exact same-product relation to the listing context uncertain and record-only. The bottom banner is a visible store/promotional text region, but its ownership relative to the listing cannot be resolved from pixels alone; do not remove unknown attribution from an otherwise usable product image.

### 主图2、详情图3

White-background product photo of a purple grid-patterned Decepticon-style robot figure posed with a large gun, a pink cube and a spiked pink flail, plus four alternate hands laid out at lower left. No retail packaging, carton or box is visible, so retail box status is ABSENT and box relation UNRELATED. A faint, semi-transparent cursive script watermark is spread across the mid-left to mid-right of the frame and passes over the figure's torso, arm and leg, giving MEDIUM-to-HIGH overlap risk with real product detail; ownership cannot be determined from pixels, so this unknown-owner text is retained unchanged per default KEEP policy rather than edited or deleted. The image is a usable, essentially complete same-class toy photograph with useful product information (sculpt, accessories, colour), so KEEP is chosen; identity fields are recorded as UNKNOWN/not directly verifiable from context and did not drive the action.

### 主图3、详情图4

Clear, complete front-view toy action figure on a smooth white background with no retail box visible. A faint unknown watermark overlaps the lower product area; ownership is unresolved and overlap risk is high, so the usable toy photograph should be kept with the text left unchanged. Context identity details are uncertain but are record-only and do not justify deletion.

### 主图4、详情图5

The image is a clear, complete front-view product photograph of the black, white, and red ape-like robot figure on a smooth white background. No retail box, shipping carton, or display box is visible, so retail packaging is absent and the image is suitable for the WITHOUT_RETAIL_BOX grouping. The figure matches the listing context in visible structure and color; model, structure, color, and same-product observations are record-only and do not gate the action. A faint text-like watermark is visible across the middle of the image, overlapping the figure; its ownership is unresolved, so it is retained unchanged rather than removed. The image has useful product reference value and does not meet DELETE or REMOVE_TEXT conditions.

### 主图5、详情图6

The image is a clear front-facing product photograph of a Transformers Generations R.E.D. Coronation Starscream figure inside its retail box; the toy is visible through the window and the packaging is same-product retail packaging. The context title/model mentions a different character/model (Ape Captain/BEE3C), so product_identity is recorded as mismatched, but product identity matching is record-only and the mismatch alone does not require deletion of this otherwise usable product image. Visible text and marks are manufacturer/packaging branding, product-line logos, character name and legal packaging print; no removable store or promotional overlay is evident. Keep the image and retain all packaging print and manufacturer marks unchanged.

### 主图6、详情图7

Main image shows a complete Hasbro Transformers R.E.D. Optimus Primal action figure inside its matching red retail window box. The packaging is same-product and contains useful toy-with-box reference information; no removable store overlay is visible. Keep unchanged.

### 主图7、SKU池1、SKU引用1

The image is a clear front-facing retail-box photo showing a Transformers Generations R.E.D. Beast Wars Cheetor figure inside its window box. Visible text is packaging/manufacturer branding, product/packaging print, age labeling and fine print, not a removable store overlay. No actionable store watermark region is present; preserve the image and all packaging/model details. Product-title context has some character/model ambiguity, but identity fields are record-only and do not make this otherwise usable product image unsuitable.

### 主图8、SKU池2、SKU引用2

Clear front-facing product photo of a Transformers Generations War for Cybertron Optimus Primal action figure inside its same-product retail box. The box, figure, manufacturer logos and packaging text are visible and should be preserved. No store overlays or promotional watermarks requiring removal are visible, so the image is usable as a with-retail-box MAIN reference.

### 主图9、SKU池3

The image clearly shows a complete Transformers R.E.D. retail box with the figure visible through the window. The visible text and logos are manufacturer or packaging print, not removable store overlays, and no explicit store watermark is detected. The context includes a with-retail-box SKU, so this image has retail-box reference value. Some listing-identity details are uncertain or inconsistent between the title and the visible Megatron packaging, but identity matching is record-only and not a reason to delete a useful product image. Keep the image and retain all packaging text unchanged.

### 主图10、SKU池4

Visible image is a front view of a Transformers R.E.D. Coronation Starscream retail box with the figure visible through the window; packaging and Hasbro branding are intact, the subject is complete, and the background is simple. No store or promotional overlay is evident, so no text removal is warranted. Product-identity comparison to the supplied Ape Captain/BEE3C context is recorded as NO/NO/NO but is record-only and does not by itself require deletion; the image remains a usable retail-box/toy reference. Decision KEEP.

## 证据与限制

工作目录：work/v2-audit-5085-20261115。status.json记录真实请求和结果；jobs/JOB_537ac52336e24fe9ab0dae64599df248保留原图、队列、响应、账本及证据清单。
description-scope.json与body-judgements.json记录正文覆盖和尾部豁免；detail-1-fetch-recheck.json记录第二次429。prompt-*.txt保留实际发送提示词，不包含密钥。
审核运行结束不等于全部图片通过。缺失图片、模型格式失败或程序暂缓单独列出；未执行整改，也未部署或提交代码。
本轮没有修改应用源码或重跑本地测试，核实审核前后源码哈希一致。历史PID4086原Job的83份封印文件保持不变。
