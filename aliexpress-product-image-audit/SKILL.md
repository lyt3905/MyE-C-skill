---
name: aliexpress-product-image-audit
description: 站内后台商品的图片、标题、型号编号和品牌审核整改。适用于水印、边框、中文海报、低清/重复图、标题前缀、型号双格式、主图数量与SKU图片语义；一件商品一个子任务，写回只用 Site.save()。
---

# 站内商品信息审核（精简入口）

本入口只保留路由和不可违反的规则。不要默认加载全部历史判例；先跑机器预审，再按异常读对应 reference。

## 1. 固定环境与正本

- 项目：`ae-img-audit/`；Python：`.venv\Scripts\python.exe`；站点：`https://39.107.244.239`。
- shopId 7 `shana1` → 标题前缀 `Hot Sale`；shopId 4 `62店` → `In Stock`。
- 一件商品一个 subagent，只写该商品和 `work/pp_<pid>/`；共享脚本只读。
- 项目正本与 skill 副本必须同步；改完在项目目录跑 `python check_template_sync.py`。

## 2. Token 节省型路由

1. 先读 `templates/子任务模板.md`，运行：
   `.\.venv\Scripts\python.exe -X utf8 audit_one.py <pid> --shop <id>`
2. 默认只读 `work/pp_<pid>/audit_context.md`；仅有问题时读 `audit_flags.json` 对应段。`audit_raw.json` 是机器证据，不要整份贴进上下文。
3. 按 context/flags 加载：
   - 图片异常/要改图 → `references/SOP-商品图片整改.md`
   - 标题、编号或品牌异常 → `references/SOP-商品标题重写.md`
   - 写站前 → `references/站点接口备忘.md`
   - 水印、边框、OCR误报、低清、编号争议或接口坑 → `references/判例与陷阱.md`
4. `mode=fast`：仍需看拼版或异常缩略图，但 KEEP 只按池汇总；`mode=deep`：只对 flags 指向的图片/字段深审，不读取无关日志。

## 3. 不可违反的规则

### 图片

- 全池审核；主图 ≤6，主图/详情/SKU 短边 ≥800；低清不靠上采样凑数。
- 盒照不删；`no retail box` 不挂盒照，`with retail box` 优先盒照。
- 别家店招/站标/促销/中文海报必须处理；厂牌 VI、摄影署名、包装自身印刷默认保留。
- 改图必须同步 `descriptionJson` 与 SKU 引用；擦/裁后重新 OCR，并看残差或对比图。

### 标题、编号、品牌

- `titleEn` 前缀跟店铺、≤120；改后调用 translate-title，默认最多 2 次。
- `modelCode` 有可靠来源就填；官方带横线优先，标题带横线+扁平双格式；找不到不编造。
- 品牌字段按用户最新规则：变形玩具/变形金刚 → Hasbro `200017853`；否则 → Bandai `200014695`。
- `identityJson.logoCode` 保持原值；原始 `title` 不动。

### 写回

- 内容只用 `Site.save()`；每次显式带完整 `identityJson`（JSON 字符串）和当前 `weight`，写后立即回读。
- 禁止裸 PUT；禁止自行发布；没有 Lead 明确要求不调用 `Site.status()`、不生成 AI 封面。
- `titleTranslationZh` 只能用 `/translate-title` 生成；`shippingFee` 永不手写。
- 状态默认保持写前值，除非 Lead 明确指定。

## 4. 紧凑交付

- `audit_context.md`：默认模型入口，约 8–20 行；无问题不再读取 JSON。
- `audit_flags.json`：结构化预审摘要，仅异常时按段读取；`audit_raw.json` 只作机器证据。
- `plan.json`：KEEP 按池汇总；仅 CROP/ERASE/DELETE/REPLACE 等异常逐图列出。
- `报告_<pid>.md`：25–40 行，写结论、实际改动、标题/编号/品牌、复检、遗留与回滚；不要逐张重复 KEEP。
- `ba.jpg`：只覆盖被处理图及关键结构变化。
- 给 Lead 的消息 ≤10 行。

## 5. Lead 独立验收

Lead 重新运行 `audit_one.py <pid> --force`，读取紧凑 flags/verify JSON，核：status、张数、尺寸、主图0、死链、OCR异常、标题前缀与长度、modelCode双格式、品牌、logoCode/weight未漂；再目视 `ba.jpg`。不得只采用子任务自述。

一句话：**先 flags、后按需深审；图片/标题/编号/品牌一起审；save 写内容，status 单独且默认不动；一件商品一个子任务，Lead 独立验收。**
