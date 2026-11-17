# 分级视觉请求与精简字段

0.2.39。正式配置驱动的商品流程默认使用staged-v1，沿用现有CLI、Job、客户端、模型、预算/Token账本、修复、OCR备选、保存和独立回读。没有增加第二套Runner。未配置的底层JudgeClient旧库调用继续保留legacy-v2兼容；新网关配置和正常CLI默认分级。

## 请求顺序

1. 每张SHA唯一原图只初审一次（结构错误按既有上限有限重试）。只要求decision、visual_class、retail_box_status、sku_suitability、abstain、reason六个顶层字段。
2. KEEP、DELETE、REVIEW不询问去水印细节。REMOVE_TEXT优先经过已有干净同照片匹配；能REPLACE_TWIN时不询问擦除规划，不运行LaMa。
3. 无干净替代版本且已授权整改，才请求watermarks、preserve_regions、reason。去除目标/类别/归属由DeepSeek判断；程序选择实际掩膜与算法。初审原始回复不改写，规划单独保存。
4. 实际候选由DeepSeek复核五项检查。这里只返回decision、abstain、checks、residual_watermarks、reason，不索取分数、包装/SKU重复判断或风险预测。
5. 已有OCR备选仍共享最多两轮本地候选，始终从原图处理；第二轮实际复核不通过继续REVIEW，不因格式合法或生成文件而通过。

## 实测固定输入

旧完整初审业务提示词+Schema为29754字符。新初审3059字符（减少89.7%）、规划3795字符、实际复核3555字符。均不含图片、当前商品上下文及动态区域数据，不等于API实际Token或耗时。初审必填顶层字段26→6；规划3个，复核5个，SKU/区域/检查各有必要子字段。

新阶段Schema从现有V2字段枚举派生，仍进行完整结构与业务验证。业务动作和类别不重定义。旧V2 Schema和长提示词保留给显式旧模式/历史记录，不进入新请求，不把精简回复伪装成完整V2回复。

## 字段处理

- ID、图片SHA、图池类型、协议版本和证据绑定由程序根据实际输入建立，不让模型照抄；实际绑定仍验证，模型原文仍保留。
- 新请求不再索取root/区域/包装/玩具/分项置信度、同款/结构/配色观察、box_relation、盒子位置说明。旧历史字段及分数不删除、不改写。Token账本不受影响。
- 初审不索取watermarks、preserve_regions、retail_box_bbox、toy_present、subject_complete、clear、angle、background_complexity。包装/SKU仍由六字段中的明确观测决定。盒照没有盒外玩具时可用于有盒SKU，图面实际内容不伪造。
- 旧SKU逻辑曾用angle挑选第二张图：新阶段未采集角度时，保留已有尺寸/内容SHA顺序，选择不同内容的第二张；不补UNKNOWN冒充模型观察。
- 掩膜执行仍可在旧执行适配器中使用UNKNOWN背景路由，以选择保守后端；它是程序的缺省路由状态，不写回为模型画面判断。源观察没有该字段，也不补分数0/1。
- 新规划只给目标ID、同组ID、action、kind、owner、content_type和bbox/polygon，不让模型指定字形样本、修复模式、搜索比例、后端或风险值。派生执行标注单独记录REGION等程序选择，保留原回复。

## 配置与证据

在原model.local.json中可显式指定：

```json
{"vision_protocol": "staged-v1"}
```

设为legacy-v2可明确恢复旧完整请求。协议不因模型输出不合规而自动切换。分阶段缓存包含阶段、提示词、输入上下文、模型/参数和所有图片SHA；业务冲突不通过重新询问绕过，质量阶段不自动重试。

初审证据保留在full_ai_judgements.json和原账本/metrics；规划在v2_candidates/<SHA>/planning/中保存原响应、派生观察和绑定；发布验证会检查初审、源SHA、规划原文和派生结果一致。实际候选、保护对比和OCR证据继续纳入原计划完整性校验。

本轮仅本地开发与Fake验证，没有新真实模型对照，不能据提示词更短宣称定位准确率或整体耗时已提高。验收见reports/staged-vision-report.md。
