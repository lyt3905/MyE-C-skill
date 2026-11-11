---
name: aliexpress-product-image-audit
description: 站内后台商品的图片、标题、型号编号和品牌审核整改。适用于水印、边框、中文海报、低清/重复图、标题前缀、型号双格式、主图数量与SKU图片语义；一件商品一个子任务，写回只用 Site.save()。
---

# 站内商品信息审核（token-opt-v1）

当前流程版本：`token-opt-v1`。缺少该版本号、`run_metrics.json` 或严格 `plan.v1.json` 的子任务结果不得验收。
本入口只保留路由和不可违反的规则。不要默认加载全部历史判例；先跑机器预审，再按异常读对应 reference。

## 1. 固定环境与正本

- 项目：`ae-img-audit/`；Python：`.venv\Scripts\python.exe`；站点：`https://39.107.244.239`。
- 本流程所有 python 命令必须以**项目根**为 cwd（`cfg.local.json` 从 cwd 向上查找，否则报「缺少站点凭据」）。「当前店铺」是服务端会话上下文：商品 404 或列表不对时先 `PUT /api/admin/shops/current {"shopId": <id>}` 再重读。
- OCR 默认走 GPU：项目根 `.venv\Lib\site-packages\sitecustomize.py` 会自动把 `_gpuocr\ort_gpu12`（onnxruntime-gpu 1.20.2 / CUDA 12）插到 `sys.path[0]`，并 monkeypatch `RapidOCR` 用 CUDA、限制线程；运行时 stdout 应出现 `[gpu-sitecustomize] RapidOCR -> CUDA`，缺失即已回退 CPU，需检查 `_gpuocr\ort_gpu12` 与 `torch\lib` 的 DLL。**重建 venv 后必须重放该 sitecustomize 与 GPU 目录**，否则会静默退回 CPU 压满机器。
- shopId 7 `shana1` → 标题前缀 `Hot Sale`；shopId 4 `62店` → `In Stock`。
- 一件商品一个 subagent，只写该商品和 `work/pp_<pid>/`；共享脚本只读。
- 默认入口是“审核并整改后写站”：用户只要指定商品并要求审核，就视为已授权该 PID 在严格计划与 dry-run 通过后写回，不再二次确认。只有用户明确说“只读/不写站”时才停在 dry-run。
- 默认写站仅指整改内容经一次 `Site.save()` 保存；仍禁止 `Site.status()`、发布、生成 AI 封面或推进状态。
- 项目正本与 skill 副本必须同步；改完在项目目录跑 `python check_template_sync.py`。

## 2. Token 节省型路由

1. 先读 `templates/子任务模板.md`，运行：
   `.\.venv\Scripts\python.exe -X utf8 audit_one.py <pid> --shop <id>`
2. 运行 `apply_token_plan.py init <pid> --shop <id>`；它优先复用 `audit_product.json`，生成严格 `plan.v1.json`，不重复联网。
3. 默认只读 `work/pp_<pid>/audit_context.md`；仅有问题时读 `audit_flags.json` 对应段。`audit_raw.json` 是机器证据，不要整份贴进上下文。
4. 按 context/flags 加载：
   - 图片异常/要改图 → `references/SOP-商品图片整改.md`
   - 标题、编号或品牌异常 → `references/SOP-商品标题重写.md`
   - 写站前 → `references/站点接口备忘.md`
   - 水印、边框、OCR误报、低清、编号争议或接口坑 → `references/判例与陷阱.md`
5. `mode=fast`：仍需看拼版或异常缩略图，但 KEEP 只按池汇总；`mode=deep`：只对 flags 指向的图片/字段深审，不读取无关日志。
6. 全池先看低分辨率拼版，只对异常/不确定项打开原图（目标≤12次）；同一证据不重复读，不贴原始 OCR/完整 JSON/长日志。禁止 `s1→s15` 一次性脚本链，默认只改 `plan.v1.json`，异常修图最多 1 个商品内脚本；模型请求目标≤45。

## 3. 不可违反的规则

### 图片

- 全池审核；主图 ≤6，主图/详情/SKU 短边 ≥800；低清不靠上采样凑数。
- 盒照不删；`no retail box` 不挂盒照，`with retail box` 优先盒照。
- 别家店招/站标/促销/中文海报必须处理；厂牌 VI、摄影署名、包装自身印刷默认保留。
- **社交账号水印（微博/微信/小红书 @ 号等，含别家博主署名）一律不擦不换**（用户 2026-11-11 口径：「微博的这种不用擦」）；只处理店名/店招/logo/横幅/中文海报。
- 全店共用页脚模板图（如带 `wallpapers-den.com` 等第三方小水印）不单件改；用户 2026-11-11 裁定「不管」，只登记由 Lead 统一决策。
- 改图必须同步 `descriptionJson` 与 SKU 引用；擦/裁后重新 OCR，并看残差或对比图。

### 标题、编号、品牌

- `titleEn` 前缀跟店铺、≤120；改后调用 translate-title，默认最多 2 次。
- `modelCode` 有可靠来源就填；官方带横线优先，标题带横线+扁平双格式；找不到不编造。
- 品牌字段按用户最新规则：变形玩具/变形金刚 → Hasbro `200017853`；否则 → Bandai `200014695`。
- `identityJson.logoCode` 保持原值；原始 `title` 不动。

### 严格计划与写回

- 只用 schema=`token-opt-plan/v1` 的 `plan.v1.json`；旧计划不得交给 `pipeline.apply_plan()`。图片池用最终有序数组，描述只按完整 URL 精确操作。
- 写前必须 `validate` + dry-run；dry-run 零上传、零 save。默认写站模式下，用户指定商品并要求审核即授权该 PID 写回，Lead 派发任务时明确批准；dry-run 通过且确有改动后设置 `approval.site_write=true`，并用 `--apply --confirm-pid <pid>`，不再二次询问。用户明确说“只读/不写站”时必须保持 false 并停在 dry-run。
- 无实际改动时不得伪造字段变化或调用 save，直接报告无需写回。
- 执行器只允许一次 `Site.save()`；每次显式带完整 `identityJson`（JSON 字符串）和当前 `weight`，以完整状态哈希防漂移，写后立即回读。
- 禁止裸 PUT；禁止 `Site.status()`；禁止自行发布或生成 AI 封面。状态保持写前值。
- `titleTranslationZh` 只能用 `/translate-title` 生成且最多 2 次；`shippingFee` 永不手写。

## 4. 紧凑交付

- `audit_context.md`：默认模型入口，约 8–20 行；无问题不再读取 JSON。
- `audit_flags.json`：结构化预审摘要，仅异常时按段读取；`audit_raw.json` 只作机器证据。
- `plan.v1.json`：KEEP 在 `review.keep_summary` 按池汇总；异常只在 `review.actions` 逐图记录，实际写入只进严格 `desired`。
- `run_metrics.json`：记录缓存/下载/OCR/耗时/产物/写入计数；无法从 Python 获知的模型请求和 token 保持 `null`，不得猜数。
- `报告_<pid>.md`：用 `render_token_report.py <pid>` 生成 25–40 行报告，带流程版本、预算、改动、复检、遗留与回滚；不要逐张重复 KEEP。
- `ba.jpg`：只覆盖被处理图及关键结构变化。
- 给 Lead 的消息 ≤10 行，必须写 `流程版本：token-opt-v1 / 预算状态：PASS|WARN|UNKNOWN`；会话账本未补齐时只能写 UNKNOWN，不得假报 PASS。

## 5. Lead 独立验收

Lead 先拒收缺少版本、严格计划或 metrics 的结果；再运行 `audit_one.py <pid> --force`（重下图片，相同内容仍可命中证据缓存），读取紧凑 flags/verify JSON，核：status、张数、尺寸、主图0、死链、OCR异常、标题前缀与长度、modelCode双格式、品牌、logoCode/weight未漂；确认收据只有一次 Site.save、零 status 调用；再目视 `ba.jpg`。不得只采用子任务自述。

一句话：**先 flags、后按需深审；严格计划先 dry-run；图片/标题/编号/品牌一起审；内容只走一次 save，status 永不由本流程调用；一件商品一个子任务，Lead 独立验收。**
