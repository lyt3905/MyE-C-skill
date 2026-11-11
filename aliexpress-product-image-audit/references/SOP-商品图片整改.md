# 商品图片整改 SOP（站内 https://39.107.244.239）

> 沉淀自 4050（TM14 手办）、4649（NEWAGE H80）、4049（AS08S）三个商品的实操，2026-11-06。
> 给一个商品链接时，按下面顺序走。

## 0. 先看现场（只读）
1. `GET /api/admin/products/{id}` → title / titleEn / identityJson.modelCode / skus / images.{main,detail,sku,ai,scene} / descriptionJson / status / presale / sourceUrl
2. `GET /api/admin/toy-image-workers/status` → 确认图片 worker 是否空闲（`pendingJobCount`、`totalDispatched`）
3. 把现有图全部下载到本地，拼一张总览图逐张看（不能只看缩略图，水印往往很小）
4. 改完一件商品后**必须**跑 `python check.py <pid>`（§5.7），FAIL 0 且残差拼图逐格看过才算交付
   - 同一件商品要重写英文标题时，走 **`SOP-商品标题重写.md`**（标题模板/替换表/120 字规则/落库与校验都在那边；写的是 `titleEn`，不是 `title`）
5. 有已知店铺水印模板时先跑一遍 `python wm_tpl.py scan <目录>`；再出一张高通拼图（见 **§W5**），专门抓「只有首尾字母露在边缘」的超宽淡字水印；**并跑 `python residcheck.py <pid> --all` 出残差图（见 §W8），淡字水印只有这一步能可靠看出**；残差图拿不准时再跑 `python vlmcheck.py <pid>` 让视觉大模型复核（§W9：glm-5v-turbo 首判 + kimi-k3-1 复核，只采信位置与有无；HIT/REVIEW 仍要人看残差图）
6. **写回一律用 `pipeline.Site.save()`（= 界面「保存」按钮，`PUT ?autoSave=true`）；要推进状态（生成 AI 封面等）单独调 `Site.status()`。两个动作绝不能合并** —— 见 §5 顶部 2026-11-07 纠正。

## 1. 主图审核（逐张看）
- [ ] 是否有**水印**（别家店铺店名/logo、微博号、淡色大字、重复贴字）→ 命中就走 **§W 水印处置**
- [ ] **超宽淡字水印**（肉眼几乎看不见、只有首尾字母露在左右边缘）→ 必须按 **§W5** 跑高通拼图 + `wm_tpl.py scan`，OCR 查不出来
- [ ] 是否有**横幅/贴纸**（红边框、In Stock 椭圆、促销条、中文「新品预定」等）
- [ ] **图文是否相符**：图上印的型号/商品名 vs 标题与 modelCode（4050 就是这样发现 Garuda/Galida 矛盾的）
- [ ] 尺寸是否 ≥800×800、是否重复图、是否有纯盒子图混在主图里
- [ ] 是否已有 AI 合成封面（`images.main[0]` 通常是站点生成的 .png）

## 2. 主图处置规则（用户 2026-11-06 定的）
- 加完 AI 主图后 **主图数 > 6 张** → **删掉那张带横幅的图**（按内容识别，不是固定删第 2 张）
- 加完 AI 主图后 **主图数 ≤ 6 张** → **裁掉横幅**（按行/列扫描纯色带定位，裁完按内容 bbox 居中重排回 800×800 白底）
- **盒照不要删（用户 2026-11-06 新增，硬规则）**：任何图一旦判定为「包装盒照片」（`pipeline.is_box_photo` / `vlmcheck.kind_of_file` 回 `box`），**DELETE 一律降级**——有横幅就只裁横幅（CROP_OR_DELETE），没横幅就 KEEP。理由：盒照是唯一能证明「带不带盒」的素材，有盒 SKU 图和纠纷举证都靠它，删了就再也拿不回来。
  - 代码已硬编码三处：`analyze()` 的盒照守卫（判 DELETE/CN_POSTER 时先问 VLM）、`apply_plan()` 兜底（plan 里 box=box 的 DELETE 强改 KEEP）、`set` 人工改判时打印告警。
  - 自动判据由 `check.py` **F1** 兜底：plan 里出现 `box=box` 且 action 为 DELETE/CN_POSTER 就 **FAIL**。
  - 判定成本：每张落在 DELETE/CN_POSTER/CROP_OR_DELETE 的图才调一次 VLM（约 2.7 s，结果缓存在 `work/sku_box.json`），不额外拖慢正常商品。
- **删图优先级（用户 2026-11-06 纠错后定的硬规则，务必按此顺序挑）**：主图超 6 张时，先删 **①装饰边框/拼版自制海报 ②别家店铺店名水印/店招横幅 ③中文促销海报**，再删 ④重复角度图 ⑤非方图；**官方棚拍（含带 © 摄影版权小字、© ALL RIGHTS RESERVED BY xxx STUDIO 的）永不删**。
  - 反例（真实事故，商品 4567/4568）：在 230px 缩略图上凭「内容重复」肉眼挑，删掉了 1000×1000 / 1280×1280 的官方棚拍，留下了银框 + 彩虹 W logo + 红字 ES10-ES11 / 银框 WW01 的自制拼版海报 —— 用户的判断是「带店名/装饰边框的先走，官方原始素材留着」。**删前必须放大（≥600px）复核候选**，不许只在缩略图拼版上下判断。
  - 代码支撑：pipeline.decor_frame(path) 新判据（四条边各取外侧 9~10% 找亮度台阶，**≥3 条边台阶 ≥40** 判为装饰边框/拼版海报；实测 4567/4568 官方棚拍单边最大只有 32.9，银框海报四边 46/163/102/100）。analyze 会写 it["decor"]=True 并把 reason 标成「装饰边框/拼版海报（超 6 张时优先删，官方棚拍不动）」；apply_plan 截断时按 盒照(0) → 普通(1) → 装饰边框(2) 排序，装饰类排最后，即最先被删。
- 中文促销条/中文文案：一律清理（外文站点）
- 其余水印一律走 **§W 水印处置**（不在这一步就地擦）
- **交付前复检（2026-11-06 五件复检后新增）**：把最终保留的每张主图过一遍 OCR，扫 in stock / preorder / store / shop / seller / contact / delivery / discount / coupon / wholesale 这些词。除 main[0] 自家 AI 封面（In Stock | PureSun Toys 是允许的）外，任何一张命中都要人工看：命中多半意味着竞品店招或促销拼版被漏在主图里（4570 就是这么漏的 —— 竞品拼版 Cybertron Preorder + 黄字 RT-07 + In Stock 条留在了 #1）。脚本：ocrscan5.py（逐件逐图 OCR + 可疑词命中）、finalchk.py（5 件 x 6 图总览拼版）。

## 3. SKU 审核

> **2026-11-06 商品 4758 事故（必读）**：主图 5 张全部换完、详情也处理了，**SKU 图原封不动**——两个规格（no retail box / with retail box）共用同一张 3072×3072 盒照，等于「有盒 / 无盒」都没换。用户当场发现。
> 根因：`pipeline.py` 的 `analyze()` 会把 `sku` 收进 plan，但 `apply_plan()` 当时写的是 `if it["kind"] not in ("main","detail"): continue`，**写回阶段直接把 SKU 丢掉了**，plan.json 里还留着一条无理由的 `sku 0 KEEP`，看起来像"没事"。
> 已修（2026-11-06）：apply 会写 `images.sku` + 改派 `skus[].skuImageUrl`；`verify()` 会打印 `skus=N sku_img=M`，共用一张时报 `[sku] !!`；新增 `pipeline.py skuset` 显式分派；apply 支持 `lock`，防止重复 apply 把手工改过的图冲回去。

> **SKU 图共用规则（用户 2026-11-06 明确，取代原来的"必须两张不同图"）**
> - ❌ **禁止**：无盒/有盒**共用同一张盒照**（等于给"无盒"买家挂盒图，是虚假描述，也是 4758 事故的误导来源）。
> - ✅ **允许**：无盒/有盒**共用同一张本体/人形图**（用户原话："无盒/有盒可以共用一张人形图，但是：无盒/有盒不能共用一张盒子图"）。
> - 判定不了"这张是盒照还是本体照"时，用 `vlmcheck.kind_of_file(path)`（glm-5v-turbo，回 `box` / `figure` / `None`）。

- [ ] 每个 SKU 的 `skuImageUrl` 都填了（缺图 = FAIL）
- [ ] 多规格共用一张图时，**必须确认那张是本体/人形图**；共用盒照 = 必须拆开
- [ ] **有盒 SKU** 优先用带包装盒的图；**无盒 SKU** 绝不能是展示盒子的图
- [ ] `images.sku` 数组（SKU 图池）是否有值，是否与各 SKU 对应
- [ ] 全库找不到盒照时 → 不要造，不要拿本体图冒充盒照；直接问用户要一张实拍

### 3.1 操作步骤（强制，不许跳）

```powershell
# 1) 看规格与现有图（有几个规格、各自 skuImageUrl 是否同一张）
.venv\Scripts\python.exe pipeline.py verify <pid>

# 2) 分派（右侧可以给线上图索引 main:i/detail:i，也可以给本地文件路径）
.venv\Scripts\python.exe pipeline.py skuset <pid> "no retail box=main:1" "with retail box=main:0"

# 3) 复查（skus 与 sku_img 必须相等，不能有 [sku] !! 警告）
.venv\Scripts\python.exe pipeline.py verify <pid>
```

判据（缺一不可）：
1. 每个规格都有 `skuImageUrl`（D1 PASS）
2. 若多规格共用一张图：那张图必须是**本体/人形图**（D2 回 "共用一张本体图（允许）"）；共用盒照 = FAIL，必须拆开
3. 有盒规格尽量挂盒照、无盒规格挂本体图（**不能反过来**）；确实没有盒照时可以共用本体图，但**不许**把盒照给无盒规格
4. 分派完必须跑 **§5.7 交付体检**，`D1/D2/D3` 全 PASS

### SKU 图规格（用户 2026-11-06 补充）
- 有盒 SKU：用带包装盒的实拍图；无盒 SKU：用纯商品本体图（不能是展示盒子的图）。
- 两个规格**共用一张本体图是可接受的**（用户 2026-11-06 明确），**共用一张盒照不可接受**。判断"盒照 vs 本体照"用 `vlmcheck.kind_of_file`，结果缓存在 `work/sku_box.json`。
- 实拍盒照常见 522×416 这类小尺寸：**等比放大 + 白底补边到 800×800**（用户 2026-11-06 确认此做法）。配方：resize(LANCZOS, min(800/w, 800/h)) → UnsharpMask(radius=2, percent=90, threshold=3) → 居中 paste 到 800×800 纯白画布；脚本 fix4049b.py。

## 4. 详情图审核
- [ ] 水印 / 微博号 / 他店链接（`descriptionJson` 里的 `targetUrl`）→ 水印走 **§W 水印处置**；每张都要过 **§W5** 的高通检查（4049 的 10 张详情图就是靠它确认干净的）
- [ ] 外链 vs OSS：**默认不改**（除非用户说转存）；若要转，下载→上传 OSS→替换 `images.detail` 与 `descriptionJson` 里的 URL（保留 `?width=…` 后缀无害）
- [ ] `descriptionJson` 里 `image` / `text-image` 块的图不在 `images.detail` 里，单独查

## 5. 写入与稳住（关键，两次被冲掉换来的）

### 5.0 写内容 ≠ 推进状态（2026-11-07 用户指出「保存不该把商品推进到待生图」后定稿）

| 调用 | 图片 | 状态 | AI 封面 |
|---|---|---|---|
| `PUT /api/admin/products/{id}?autoSave=true`（= 界面「保存」按钮、页面自动保存） | 只有你传上去的那几张换新 id，其余 id **不变** | **不动** | 不生成 |
| `PUT /api/admin/products/{id}`（**不带** autoSave，旧写法） | **全部图改名重传** | 可能自己跳到 EDITING / READY_TO_PUBLISH | 自动生成并插到 `main[0]` |
| `POST /api/admin/products/{id}/status {"status":"…"}`（= 界面「推进」按钮） | 不动 | 按你给的值推进 | `EDITING` 时由 worker 生成 |

状态中文对应：`PENDING`=待编辑 / `EDITING`=**待生图** / `READY_TO_PUBLISH`=待发布 / `DONE`=已定稿。
界面上看到的「待生图」就是 `EDITING` —— 无参 PUT 之后界面像被推进了，就是因为它真推了。
有任务在跑时推状态会被拒：**409**「商品存在正在执行的任务，请等待任务完成后再推进」。

代码入口（`pipeline.py`）：`Site.save(pid, images=None, desc=None, extra=None)` / `Site.status(pid, value)` / `Site.blacklist(pid, url)`（删图+拉黑，整店素材都带竞品水印时批量清）/ `Site.replace_links(pid)`。
接口全表：**`站点接口备忘.md`**。

下面 1、2 条是旧做法（当年只会无参 PUT，才需要「立刻拉回 PENDING」）；现在只在脚本没法用 `save()` 时兜底。

1. **写内容：`p.save(pid, images={'main': [...]})`** —— 只改图/描述/标题，状态不动、不重新分配图片 id、不生成封面、不清 `images.sku`。
2. **推状态：`p.status(pid, 'EDITING')`** —— 这是要 AI 封面时才做的一步，做完按 **§5.8** 复查 SKU 与 main 数量。
3. 之后 **+5s / +60s / +120s 三次复查**（status、updatedAt、main 数量、images.sku、图 URL）
4. 同时看 worker 的 `totalDispatched` 有没有上涨（涨了说明又被接管）
5. **SKU 图单独分派**（§3 的事故就出在这一步被跳过）：`python pipeline.py skuset <pid> "no retail box=main:1" "with retail box=main:0"`，跑完再 `verify` 确认 `skus=N sku_img=M` 且没有 `[sku] !!` 警告
6. 交付前 `python pipeline.py lock <pid> --reason "..."`，把 plan 锁住；否则下次谁再 apply 一遍旧 plan，SKU 图会被还原成旧的

### 5.7 交付体检 check.py（改完必跑，不跑不算交付）

```powershell
.venv\Scripts\python.exe check.py <pid>            # 结构+计数+逐图+SKU+description，约 40 s
.venv\Scripts\python.exe check.py <pid> --reviewed # 看完残差拼图后再跑一次，退出码 0 才算通过
```

检查项（脚本自动判定）：

| 组 | 检什么 | 判定 |
|---|---|---|
| A | status 是否 PENDING；6 s 内 updatedAt 是否被改写；worker.totalDispatched 是否上涨 | A1/A2 FAIL 就不能交 |
| B | main 1–6 张、detail ≥1、images.sku ≥1 且 skus 非空 | B1/B3 FAIL 就不能交 |
| C | 每张图能否解码（1×1 占位图/坏图）、main+sku 短边是否 ≥800、主图之间 pHash 是否近乎相同、字形笔画统计 | C0/C1 FAIL；C2/C3/C4 WARN/INFO |
| D | 各规格是否有图、规格数 == 唯一 SKU 图数、skuImageUrl 是否在 images.sku 里、各规格期望内容提示（盒照/纯本体） | D1/D2 FAIL（**4758 就是 D2 会亮红的那种**） |
| E | descriptionJson 块数、是否残留不在 images.detail 的旧图 URL | E2 WARN |
| F | **盒照保护**：计划里是否要删盒照（F1）、plan 标记为盒照的图清单（F2）、有「带盒」规格时图池里还剩几张盒照（F3） | F1 FAIL（用户 2026-11-06 规则）；F3 WARN |
| C6 | **残差拼图 resid_montage.jpg 必须有人逐张看** | 不加 `--reviewed` 时退出码 2 = 交付未完成 |

产物：`work/pp_<pid>/check/report.json`、`resid_montage.jpg`（残差×11 拼图，淡字水印只有这里能看出，判据见 §W8）。

**4758 的通过基线（2026-11-06 13:0x，可作为对照）**：`FAIL 0 / WARN 0 / 共 30 项`，exit 0。SKU 数值核对：`sku_1(有盒) ~ main_0(盒照)` pHash 距 **0**、`sku_0(无盒) ~ main_1(裸机)` pHash 距 **0** ⇒ 语义正确。残差拼图里唯一成片字形的格子是 `detail_0`（盒照，量到 44532 px），实为盒面厂牌「铁鼠 / MAUS / YW-2611 / 易玩天明」，**不是**别家店名；主图里 727/434/427 px 的 C3 计数落在产品轮廓与阴影上。

**为什么 C6 不自动化**：淡字水印在白底上比背景暗、在灰底上比背景亮，任何单极性阈值必漏一半（§W8 四次失败）；而"厂牌文案"（钢铁战魂/铁鼠 MAUS/YW2611/易玩天明）与"别家店名"在数值上无法区分——4758 的 detail_0 量出 44532 px 大字，实为盒面厂牌，不是水印。所以数值只报警，结论必须人看。

> 视觉大模型能补一部分（§W9：glm-5v-turbo 在 8 张真图上 8/8），但它对压在本体上的极淡字净检出只有 25–50%，且会把左下角厂牌印章误报成「店铺水印」（21 张干净图上 7 条误报全部是这种）⇒ **模型只做初筛，C6 仍是人的最终关口**。

### 5.8 推进到「待生图」之后必须复查（2026-11-06 五件批量实测）

> 入口只有一个：`p.status(pid, 'EDITING')`（§5.0）。**不推就不会有 AI 封面，main 也不会凭空变 7 张；一旦推了，下面的复查一项都不能省。**

`POST /api/admin/products/{id}/status {"status":"EDITING"}` → worker 生成 AI 封面：**main 从 5 张变 6 张**（首位插入 ai0 800×800 合成封面），`images.ai` 新增 2 张（800×800 + 750×1000），随后状态自动推到 `READY_TO_PUBLISH`（待导出）。队列忙时会在 `EDITING` 停留几分钟，属正常。

**坑（实测踩到）：worker 用「任务派发那一刻的快照」回写 SKU。** 4758 在 15:56 生成完成后，两个规格的 `skuImageUrl` 被改回整改前的旧盒照（共用 `Sf5335ae9d62d4ffd9…`），正是 §3 禁止的「共用盒照」。
⇒ 每次推进到待生图、生成结束后都要复查 SKU：
```powershell
.venv\Scripts\python.exe pipeline.py verify <pid>      # 看 skus / sku_img 两个数是否相等
.venv\Scripts\python.exe pipeline.py skuset <pid> "no retail box=main:2" "with retail box=main:1"   # 被回退就重新分派
.venv\Scripts\python.exe pipeline.py verify <pid>
```
注意 `skuset` 会把状态拉回 `PENDING`（待编辑），需要再推一次 `EDITING`；用新快照重新派发后 SKU 能保住（4758 于 16:02 修复后 main=6 / skus=2 / sku_img=2 稳定）。

**main 上限 6 张，AI 封面会挤掉一张旧主图**：本轮 4758（原 6 张主图）生成后丢了 detail_9 方裁图、4649 丢了裁过横幅的 main_0。想保住某张，就先把 main 缩到 5 张再推进（`pipeline.py set_actions` + apply，或直接在站上删一张）。

**不要重复置 EDITING**：worker 队列是全局的（`totalDispatched` 是所有商品的累计，不是本商品的），一件商品可能排十几分钟才轮到。反复推 EDITING 会**重复生成封面**：4049 被推了两次，生成后 main 变成 7 张（两张 AI 封面 + 5 张原图），超过 6 张上限，需手工删一张。⇒ 推一次就等，别催。

**AI 合成封面自带本店品牌条**：ai0/ai1 全部在底部有「PureSun Toys」横幅（16 张 AI 图 16 张命中）——这是**我们自己的合图模板**，不是竞品水印（§W 白名单见下）。

## W. 水印处置（主图、详情图共用）

> 触发点：第 1 步（主图审核）或第 4 步（详情图审核）发现水印。
> 执行点：写入站点（第 5 步）**之前**完成。水印不是独立步骤，是「审核 → 处置」里的子动作。

### W1 四分类（先判定，再动手）
| 类型 | 例子 | 处置 |
|---|---|---|
| 官方标注 | Takara「※画像は試作品の為…」、免责声明、版权行 | **不擦** |
| 别家店铺标识 | 「CT Figure Hobby Store」红字、淡色店名大字 | 换图 / 擦 |
| 社交账号水印（微博/微信/小红书 @ 号等） | 如 @莽姆森、@暗之帝王 等博主/账号署名（含别家的） | **不擦不换**（用户 2026-11-11 m00981 明确：「微博的这种不用擦」） |
| 品牌方自有账号水印（**允许保留**） | 厂牌官方图的「@TMT模玩社」微博小字、原盒底「@MS-TOYS 微信/微博」、钢铁战魂 / 易玩天明 / MAGIC SQUARE / FLEMING GALILEO 等厂牌标与型号 | **不擦不换**（用户 2026-11-06 m08411 明确：「这种不需要换掉」；与 §W1「官方标注」同性质） |
| 超宽淡字店名（**易漏**） | 店名拉到整幅宽、只有首尾字母可见（4049 main#2） | 见 **W5**：高通 + 模板匹配定位，优先换图 |
| 贴边横幅 | 红边框、In Stock 椭圆、中文促销条 | 不做擦除，走第 2 步的删/裁规则 |
| 压在商品图上的重复水印 | 同批图共享的 3×3 文字格（4050：行 y≈112/343/579，列 x≈90/315/575） | 擦（有前提，见 W3） |

判定硬标准：**同图重复 ≥2 次且长度 ≥3 的文字**才算水印；只出现一次的文案不算，归横幅规则。

判别「品牌方账号」vs「别家店铺账号」：看**图是谁出的**——厂牌官方棚拍/官方海报/原盒包装上带的 @账号 = 品牌方（保留）；自制拼版、促销横幅、店铺页截图上的 @账号 = 别家店铺（换/擦）。拿不准时问用户，不要默认删。**例外（2026-11-11 用户口径）**：任何社交平台账号水印（微博/微信/小红书 @ 号，含别家博主署名）一律**不擦不换**，只处理店名/店招/logo/横幅/中文海报。

### W2 处置优先级（2026-11-06 二次修订：用户要求「能本地擦就本地擦，找不到干净版先跳过，收工统一问要不要联网找图」）
1. **换图 · 站内孪生**（最省事）：同一张图在 detail/sku 桶里有无水印版本（pipeline 自动配对 phash ≤6）
2. **裁**：水印在边缘 / 角标 / 横幅内 → 裁掉（4649 在 y=680 切一条）
3. **擦 · 本地**（用户明确「优先本地擦除」）：整条带填平或 LaMa 逐笔，**必须过 VLM 复核**（§W3.2）；擦不干净的不许上线
4. **换图 · 本地图池**（不联网）：`imgpool.py` 里已下载的官方图按 pHash 命中同款（距离 ≤10）
5. **WEB_DEFER（跳过等确认）**：都不行 → **这张图保持原样**（保留原 URL，绝不能删成空 —— 4571 事故），待办记进 `work/web_pending.json`，收工一起问用户要不要联网换源
6. **外部官方原图**（仅在用户明确许可后执行，见 §9）：OCR 读到本商品型号（如 DK-99）+ phash 距离 ≤12，且不含店名/平台字样

判据经验：水印本质是「别人家的图」，纯技术上「换」优于「擦」；但用户 2026-11-06 明确要求**先试本地擦**（不引外部素材、不占网络），擦不动的就跳过等确认 —— 硬擦会在商品上留抹痕，比原水印更伤。

### W3 擦的技术边界（4050 实测）
- 背景区（白底/黑底/渐变）：TELEA inpaint 干净
- 压在商品本体：TELEA 会补出白斑（紫色躯干那几格）；用 LaMa（2026-11-06 已装并验证，见 W7），但仍会补白 → 只擦「白底上的部分」，机体上的残余不追
- alpha 反解路线**已证伪**（两次）：该水印不是干净的恒定 alpha 叠加；2026-11-06 在 4755 上再试"局部反解"，alpha 高估把白字变成深色字，更难看 → 不要再走这条路

### W3.1 白底白字的擦法（2026-11-06 商品 4557 一次成功，与 W8「擦不动」的分界）

**判据**：白/浅灰地台上的半透明白字，比局部背景**更亮**（g − medianBlur(g,31) ≥ +5）。先用残差图（`vis = 128 + (g−bg)×6`）确认字形位置，再取**列/行带**限定，只在这条带里判：

```python
y0, y1, x0, x1 = 640, 780, 200, 700        # 行带：先看残差图定位那一行
g, bg = gray[y0:y1, x0:x1].astype(int), medianBlur(gray, 31)[y0:y1, x0:x1].astype(int)
m = ((g > 205) & (g - bg >= 5)).astype(np.uint8) * 255
m = close(m, 3x7); m = dilate(m, 5x5, 1)    # 4564 型笔画 → 11606 px
# LaMa 只处理这一块（四周 pad 64）再回贴；注意 SimpleLama 输出会有 8px 对齐的尺寸差，回贴前 res[:ch,:cw]
```

**分界线**：判据**限定在行带内**就成功（4557 mask 11606 px，擦完残差图整行字消失、地台平滑）；判据放到**全图**就必然失败（同一个商品 mask 膨胀到 120033 px，把整片浅灰地台框进去，LaMa 涂成一片）。若字压在深色商品上（W8 的情形）→ 不擦，换图。

### W3.3 整段横幅 / 纯色底贴边字 —— 用 `clean_band.py`，别用 inpaint（2026-11-07 商品 4826 落地）

**判据**：①店名是**整条横幅**（任意底色，常见粉/白/灰条），且在顶边或底边；②促销字压在**纯色或渐变底**上（紫圆、色块、浅色地台）。这两种 inpaint 都会糊或留残影（4826 前两版就是这么废的）。

**配方**（skill `scripts/clean_band.py`，不依赖 pipeline）：

```python
import sys; sys.path.insert(0, r"~/.dsh/skills/aliexpress-product-image-audit/scripts")
import clean_band as cb, cv2
img = cv2.imread("work/pp_4826/src/main_0.png")
img = cb.crop_border(img, (17, 25, 778, 785))            # ① 先裁掉装饰边框（不留一圈彩边）
pink = img[0:16].reshape(-1, 3).mean(axis=0)             # ② 横幅底色取样（取前 16 行均值）
cb.wipe_band(img, cb.band_mask(img, pink, tol=60, y1=16)) # ③ 整段填白（比只填笔画干净）
text = cb.color_mask(img, (0, 600, 150, img.shape[0]), kind="red")
cb.fill_rowwise(img, text)                                # ④ 按行插值掉红字（不填白，避免补丁）
print(cb.check_residue(img, (0, 600, 150, img.shape[0]))) # ⑤ 自检 → (剩余像素, 是否干净)
cv2.imwrite("work/pp_4826/out/main_0.png", img)
```

**验收**：4826 用这套参数从原图复现线上结果（对线上图 PSNR 40.4 dB、目标色残留 0 px）；**边界仍需人眼**看放大图（横幅下沿与裁框接缝），再用 2× OCR 扫 `store/shop/official/in stock`。

**边界**：`fill_rowwise` 要求左右都有可插值的邻居（`max_span` 可设上限）；整幅宽、压在商品本体上的字不属于本配方，走 W5/W8。

### W3.2 「能不能擦」必须靠「试擦 + VLM 复核」定案（2026-11-06 四次翻车后定稿）

静态阈值一律不可靠，两条真实反例：
- **假阳性**：4571 的「BANDAI Model Play Factory Store」满图斜铺，平坦度判据给它 0.98（几乎必然可擦），实际只擦掉 find_band 找到的那一条横带，带外的字照样清清楚楚（`work/pp_4571/zoom_main_3.jpg` 1:1 对照可证）。**cover**（带内笔画 ÷ 全图笔画）只有 0.24–0.77，这条才是关键信号。
- **假阴性**：4557 main_0 的白底横幅 cover 只有 0.499（因为掩膜里混进了白底上的产品边缘），按 cover 阈值会被误杀。

⇒ **定案口径**（`erasetool.plan_erase`，已接进 pipeline 的 ERASE 决策）：

```
缩图到长边 700 → 先问 VLM「本来干净吗」→ 干净就直接 KEEP
           → ①整条带填平  → VLM 判干净？ → 用这条（method=fill）
           → ②LaMa 逐笔擦 → VLM 判干净？ → 用这条（method=lama）
           → 都不干净 ⇒ 判「擦不动」→ 走本地图池 / WEB_DEFER
```

两个必须记住的坑：
- **plan 里的 band 是缩图坐标**，用到原图上必须按 `H_full/H_small` 缩放（不缩放会擦错行，4557 实测：擦完 VLM 仍读得店名）。
- 整条带填平后 `resid_px/mask_px` 比率没有意义（分母混进产品边缘笔画，4557 是 0.53）⇒ `fill` 方法**跳过比率门**，直接以 VLM 结论为准。

整条带填平（`erasetool.fill_band`）= 用带上/带下各 6 行的平均色做垂直线性插值 + σ=1.2 噪声填掉整条带。**只对平坦背景成立**；白底横幅一次成功（4557 main_0：LaMa 逐笔擦 VLM 仍 HIT，改成填平后 VLM 立刻判干净 conf 0.95）。满图铺的水印填平也救不了（会把整片背景抹平、字仍在一半）。

### W4 验证
1. OCR 复检擦后文字框数 **必须为 0**（4050：9/10/10/10/9/8 → 全 0）
2. 看残差图，只允许剩商品高光
3. 交付擦前/擦后并排图 + 局部放大图

### W5 超宽淡字水印（整幅店名）— 2026-11-06 4049 实测翻开

**形态**：一句店名被拉到几乎整幅宽、透明度极低（残差只有 2–6 灰阶）。中间段压在商品本体上完全看不见，**只有首尾字母露在左右边缘的空白处**（4049 main#2：左边缘 "C"、右边缘 "e"）。这种图肉眼看像"干净"，人工复查很容易放过——4049 就是交付后被你当场指出「图3 还有水印」。

**为什么 OCR 抓不到**：对比度低于 rapidocr 的检测阈值。wm2.py 全图 OCR、wm_edge.py 左右边缘条 OCR 都是 0 条，但高通图上一眼就能看见。

#### 检测法一：高通放大（定性，靠眼睛）
- 原理：`res = gray − GaussianBlur(gray, σ=25)`，把 −8…+8 灰阶线性拉伸到 0…255。干净图的背景残差是平的；有水印的能看到字母轮廓。
- 脚本：`hp_cur5.py`（改 URL 列表，输出 work/hp_cur5.jpg）、`hp_detail4049.py`（整批详情图，500px 一格）、`band_detail4049.py`（只切水印所在的水平带，放大后最好判）。
- 做法：一个商品拼一张 5 列 × N 行的对比图，**逐张扫边缘**；重点看左右边缘和四角。

#### 检测法二：模板匹配（定量，可批量）
1. 取一张**已确认带该类水印**的图，在高通残差里框出露在边缘的那个字母：`python wm_tpl.py build <bad.jpg> <x0> <y0> <x1> <y1>`（4049 用 x12–48 / y372–428，56×36 的 "C"）→ 存 `work/wm_tpl.npy`
2. 扫描：`python wm_tpl.py scan <目录或文件列表...>` → 逐张输出 max NCC 和 CLEAN / SUSPECT / HIT
3. 判据（4049 实测分离度）：**有水印 1.000，干净图 0.52–0.62** → ≥0.80 判有水印；≤0.65 判干净；0.65–0.80 人工看
4. **必须的坑**：平坦窗口不计分。平坦区残差标准差为 0，归一化互相关会退化成 NCC=1.0 假阳性（main#4 就因此被误报过一次）→ 脚本内已加「局部标准差 <2 的窗口不计分」，改脚本时别把这层去掉

#### 成本（实测，这台机器）
| 项目 | 数值 |
|---|---|
| 单张 800×800 高通 | 9–18 ms（单核 CPU） |
| numpy 内存峰值 | 12.8 MB |
| 20 格拼图 + 存 JPG | 约 5 ms / 图 |
| 模板匹配扫描 | 约 20 ms / 图 |
| 对照：同图跑一次 OCR | 约 700 ms + 300–400 MB 模型常驻 |
⇒ 单商品（10–20 张）整体 **< 2 秒**；全库 6000 张纯计算约 1.8 分钟。真正的开销不在算法，而是下载（约 800 MB）和人工看 300 张拼图。

**处置**：仍按 W2 的「换图 > 裁 > 擦 > 问」。先查同类图池有没有干净原版——4049 的干净版就是 detail_7（phash 距 1），直接换图一步到位；没有干净版再考虑擦。

**局限**：模板只对**同一店铺同一款水印**有效，换店铺必须重取模板；模板匹配查不到字号/位置变体，所以批量扫完仍要用高通拼图人工过一遍。

### W7 极淡整幅店名水印的擦除配方（LaMa）— 2026-11-06 商品 4755 落地

**适用**：整幅宽的浅灰店名（如 "GT Cybertron Toy Store"），白底上约 #E0–E5、字高 ≈65px、笔画 ≈10px，OCR 完全读不到、模板比值无区分度。

**为什么能擦干净**：这类水印在**白底上对比度其实很高（±20 灰阶）**，只是被"淡"的直觉骗了；压在彩色机体上只有 +8，肉眼几乎不可见。所以只要把"白底上那部分"精确掩膜出来，LaMa 补白是无损的。

**掩膜配方 V13（erase_4755e.py / erase_4755f.py，逐图自适应，无需 OCR）**

> **坑（第一版为什么擦不掉）**：不要用 `bg = medianBlur(g,51); white = bg>249` 判白底——水印是**整行密集大字**，51×51 中值被字本身拉低到 ≈245，`bg>249` 直接失效，水印核心区根本没进掩膜。改用"相对暗度" `dd = g − medianBlur(g,41)`。

```
# 第 1 遍：白底上的暗字（A）+ 机体上的淡字（B）
yl   = 只保留 y ∈ [0.02h, 0.97h]
prod = dilate((g<215) | (S>45), 7x7)                # 商品/深色区
A    = ~prod & (dd < -5) & yl                        # dd = g - medianBlur(g,41)
A    = close(5x5) → 连通域保留 area≥40 且 20≤h≤130 → dilate(5x5)
band = A 的 y 范围 ±18（夹在 [0.02h,0.97h]）
dz   = dilate(g<150, 9x9)                            # 保护黑字：页脚免责声明 / 页眉 DMA logo
B    = band & ~dz & prod & 2<|dd2|<45 & ds<-2        # dd2/ds 用 medianBlur(31)
B    = close(3x7) → area≥25 且 8≤h≤110 → dilate(5x5)
mask = A | B  → LaMa
# 第 2 遍：对输出再跑低阈值残影检测（|dd| 2..28、Sobel grad<60、area≥30、10≤h≤120），
#        命中再 LaMa 一次；这一遍去掉"压在机体上的白影"，实测总残差笔画像素 3795 → 1936
```
**必须保留 `dz`（darkzone）**：第一版没有它，页脚 "Photos are prototypes… / This product doesn't include any official toys." 被整段擦掉。V13 验收口径：页脚带（y>0.86h）墨量保留率 ≥100%（实测全部 100%/100%+，擦掉水印后反而露出更多黑字）。

**修补**：`simple-lama-inpainting`（big-lama.pt，~196MB，首次从 GitHub 下载后缓存）→ `lama(PIL_img, PIL_mask)`。
**成本（RTX 4070 Laptop）**：模型加载 2.2 s，**1.0 s/图**（warmup 后 0.2 s/图）；20 张商品 ≈ 25 s。比 OCR（1.02 s/图且读不出）更划算，且不需要 OCR。

**验证（W4 的量化版）**：掩膜前后统计 `(bg>249) & (200<g<251) & (S<45) & ~darkzone` 的像素数，白底文字应大幅下降（4755：-32%…-72%，剩下的都是灰色塑料件本身）；再 1× 与 3× 各看一眼。

**已证伪的加强方案（别再试）**：(a) 只把机体上的字纳入掩膜 → LaMa 用周围白色去填，白影更明显；(b) 局部 alpha 反解 `(I−aC)/(1−a)` → alpha 高估，白字变深色字；(c) 整带局部对比度压制（k=0.3 + medianBlur 25）→ 整张糊；(d) 靠 OCR 提召回 → 淡字根本读不出，2× 放大 / 残差图 / CLAHE 都不行。**有效的是"两遍 LaMa + 相对暗度掩膜"（V13）**，残差自检 `letters()` 应 <30 px/图。

**写入**：擦完的图逐张 `POST /api/admin/uploads/images` 上传 → 按原顺序回填 `images.main` / `images.detail` / `images.sku` → `descriptionJson`（字符串）里做**整串 URL 替换**（不要按文件名拼）→ PUT → **立刻 POST /status PENDING** → +5s/+30s/+70s 复查（worker 会抢权重建）。

### W8 半透明淡字「擦不动」的判定 + 残差体检（2026-11-06 商品 4758 四次失败换来）

**判据冲突（这是擦不掉的根因）**：同一句淡字（"GT Cybertron Toy Store"，字高 ≈60–70px）
- 在白底（#F2–#F8）上比背景**暗**：dev = −6…−14
- 在灰底（#C8–#D2）上比背景**亮**：dev = +5…+15
⇒ **任何单极性阈值都会漏掉一半**；两图共识/更大掩膜又会把履带、厂标一起吞掉（实测 mask 膨胀到 1.6% 甚至 13.9k px，LaMa 把产品涂花）。
4758 试过的四条路全部不够好：V13 LaMa 掩膜（只抓到履带碎片）、白底抹平（flatten+55% 白，字仍可读，residual 2230→620 px 是**假好**）、共识掩膜、TELEA inpaint+白点曲线 wash v4/v5/v6。

**结论（写进 W2 优先级）**：这类「透明度极低 + 白/灰底极性相反」的字，**不做逐像素擦除**，直接进 W2 第 1/2 档换图；只有当整段落在纯白底且周围没有产品纹理时才值得试 W7 的 LaMa。

**残差体检（新的标准动作，比 OCR 和肉眼都灵）**
```
python residcheck.py <pid>          # 只看 main
python residcheck.py <pid> --all    # main + detail
# 产物 work/pp_<pid>/residcheck/resid_montage.jpg
# 原理 vis = 128 + (L − medianBlur(L,61)) * 11，800px 长边
```
看图规则：背景上出现**成串字形** = 有淡字水印；只剩厂牌 logo（钢铁战魂/METAL SOULS/铁鼠 MAUS/易玩天明）与产品轮廓/高光 = 干净。
- 4758 实测：主图 4 张带 "Cybertron Toy Store" 淡字，缩略图里只能看到极淡的一行，OCR（含 2× 放大 + CLAHE）**一个字都读不出**，残差图上一眼可见。
- 所以：**W5 的高通图 + 本脚本的残差图，是「淡字水印」的唯一可靠入口**；OCR 只能用来读**已看得见**的字（店名横幅、In Stock 条）。

**换图素材选择（4758 落地）**：detail 桶里的官方棚拍图也可能带淡字 → **拿 detail 图当主图素材前必须先跑 residcheck**（否则会像我第一轮那样把水印从 detail_9 搬进 main_4）。
最终选材：detail_2/details_3（机器人棚拍）、detail_9/detail_11/detail_12（坦克棚拍）→ 方裁 800×800（x0 居中或让厂牌 logo 完整/整块舍弃，**不要切半个字**）。

**apply_plan 的索引陷阱（踩过）**：plan.json 是整份重建，`new_main` 只按 plan 顺序收集，**DELETE 会让线上索引左移**。所以「线上第 N 张」≠「plan 里 main_N」：4758 删掉 main_0 后，线上 m0 对应 plan main_1。看线上图要按 URL 反查，不要按序号猜。

### W9 视觉大模型复核（VLM）— 2026-11-06 21 模型横评结论

**定位**：不替代 CV，只替代「等人看残差图」这一步。CV 毫秒级先筛（pHash 孪生 / OCR 店名 / wm_tpl 模板 / 残差笔画），只把**可疑图（正常 5–10%）**交 VLM 复核；判"有"或模型间不一致时仍回到人看 `resid_montage.jpg`。

#### 首选组合（实测，别自选）
| 角色 | 模型 | 依据 |
|---|---|---|
| 首判（高召回） | `glm-5v-turbo` | A 组 8 张真图 **8/8**、2.68 s/图、7380 token/8 图，唯一全对且最快 |
| 复核（高精度） | `kimi-k3-1` | 21 张已核干净图上误报 **0/21**；A 组 7/8（1 次没按 JSON 输出） |
| 别用 | deepseek-v4-pro（误报 10/21）、glm-5.3（11/21）、hy4std（7/8 但 17.2 s/图） | 误报/延迟不可接受 |

#### 完整结果（21 个模型，A 组 = 8 张真图判对；B 组 = 21 张已核干净图上的误报）
- **8/8**：glm-5v-turbo
- **7/8**：deepseek-v4-pro（B 误报 10/21）、kimi-k3-1（0/21）、kimi-k3.1-pro（0/21）、kimi-k2.8-preview、hy4std（17.2 s/图）
- **6/8**：minimax-m3、glm-5.2、glm-5.3（B 误报 11/21）、glm-5.3-flash、hy4-preview-f、hy3、space-bunny、mimo-v2.6-pro、glm-5.1、kimi-k2.7、step-5-preview、hy4free
- **5/8**：minimax-m3.1-flash、deepseek-v4.1-flash、kimi-k2.6

区分度最高的两格：**P4**（极淡斜向水印，多数模型漏）与 **N4**（左下角厂牌印章，多数模型误报）。

#### 生产用法（vlmcheck.py，2026-11-06 新增，一条命令跑完一件商品）
```powershell
cd C:\Users\shana\Documents\deepseek-harness\default-workspace\ae-img-audit
.venv\Scripts\python.exe vlmcheck.py 4758                       # 现行全部图（main+detail+sku），双模型
.venv\Scripts\python.exe vlmcheck.py 4758 --kind main           # 只看主图（快一半）
.venv\Scripts\python.exe vlmcheck.py 4758 --models glm-5v-turbo # 单模型（再省一半时间）
.venv\Scripts\python.exe vlmcheck.py --dir work/pp_4758/imgs    # 本地目录（未上传的候选图也能先查）
```
- 输出表：`图 tag / 判定(CLEAN|REVIEW|HIT) / 各模型 Y-n / 位置+文字`；汇总行 `==== 汇总：N 张 | CLEAN x / REVIEW y / HIT z | 秒 ====`；报告 `work/pp_<pid>/vlm/vlm_report.json`（含每模型原始响应前 600 字）。
- 判定：两模型都判有 → **HIT**；只有一模型判有、或置信度 <0.5 → **REVIEW**；都判无 → **CLEAN**。HIT/REVIEW 的图会列在「需要人看残差图」一行，**仍要人看** `resid_montage.jpg`。
- 退出码：0 = 全 CLEAN；2 = 有 HIT/REVIEW。
- 耗时：21 张 × 2 模型 = 42 次调用，4 线程 **67.8 s**（≈1.6 s/次）；单模型约 34 s。key 取 `VLM_API_KEY` 环境变量，缺省回落读 `bench_vl2.mjs` 里的 KEY；网关可用 `VLM_BASE` 覆盖。

#### 已验证（可作回归基线）
- `work/vlbench/in` 8 张标注图（4 正 4 负）：4 张负样本全 **CLEAN**，4 张正样本**全部被标记**（HIT 3 + REVIEW 1），21.6 s / 61.4 s 两次。**两次运行的 HIT/REVIEW 组合会变**（P4 极淡斜向水印从 HIT 变 REVIEW）⇒ 网关侧即使 temperature=0 也不保证逐字复现，所以 REVIEW 类必须人看，不能只看统计。
- 商品 **4758**（已整改、人工确认干净）21 张：**CLEAN 21 / REVIEW 0 / HIT 0**，67.8 s。
- **prompt 里加上「左下角厂牌印章不算水印」之后，glm-5v-turbo 的误报由 7/21 → 0/21** —— 横评那 7 条误报全是厂牌印章，说明误报主要靠 prompt 约束解决，不是模型能力不够。

网关 `http://127.0.0.1:8788/v1`（OpenAI 兼容），key 走环境变量，**不要写进仓库**。21 个模型全部支持图片输入（探针 `work/vltest/probe.png` 全部读出图内文字，仅 hy4free 把 12345 读成 1 2 3 4 5）。

#### 调用口径（三条硬要求，全是踩过的坑）
1. **`max_tokens ≥ 1500`（推荐 2000）**：推理型模型（hy4std / step-5-preview / deepseek-v4.1-flash / kimi-k2.7 / hy4free）在 max_tokens=400 时 `content` 全空、`finish_reason=length`，真答案在 `message.reasoning_content` 里 —— 看起来像"8 张全错"；放到 2000 后 hy4std 立刻 7/8。脚本已加「content 为空则回退解析 reasoning_content」。
2. **喂原图，不要喂残差图**：同一批 8 张，glm-5v-turbo 原图 **8/8** → 只给残差图 **6/8**（最难的 P4 直接漏、干净图开始乱报）。残差图是给人的，不是给模型的。
3. **temperature=0 + 强制 JSON**（`{watermark, location, text, confidence}`）+ **保存原始响应**（可复现、可审计）。

#### 采信规则（幻觉对策）
- 只采信 **位置 + 有/无**；模型给出的**店名文字一律不入库**——实测把厂牌印章「易玩天明」读成「异玩天阙 / 昊玩天開 / 易玩天開」，字全错，但"左下角"这个位置每次都对。
- 位置枚举固定为：底部横幅 / 左下角 / 右下角 / 画面中部横贯 / 整幅重复 / 边缘角标；给不出可读文字只能报"疑似"，不许报"确认"。
- 判"有"或两模型不一致 → 转人工看 `resid_montage.jpg`；**不做自动删除/自动擦除**。

#### 已知误报根因（写进 prompt，也写进人工判定）
**厂牌印章**。glm-5v-turbo 在 21 张干净图上的 7 条误报**全部**指向左下角「易玩天明」厂牌标。prompt 必须写清：「左下角的厂家/品牌 logo、型号、钢印文字（易玩天明 / 钢铁战魂 / METAL SOULS / 铁鼠 MAUS / YW-2611 这类）是**官方文案，不算水印**，不要报」。

#### 检出下限（别指望它兜底）
alpha 阶梯试验（8 张干净底图叠 0/0.04/0.06/0.08/0.11/0.15 白字）净检出率 glm-5v-turbo **25% / 38% / 50%**（α=0.06/0.11/0.15）。压在产品本体上的极淡字，α=0.15 也只有一半模型稳定判出 ⇒ 落在白底/纯色区的真水印好抓；压在机体上的仍必须靠残差图人看 + 换图（§W2 第 1/2 档）。

#### 成本
glm-5v-turbo ≈920 token/图、2.68 s。全库 4858 商品 ×7 图 ≈3.4 万张，6 并发单模型 ≈4.3 h、≈3100 万 token（**未做，需显式许可**）。日常量 = CV 初筛后的 5–10%。

#### 脚本与原始数据
```powershell
cd C:\Users\shana\Documents\deepseek-harness\default-workspace\ae-img-audit
node bench_vl2.mjs plain "glm-5v-turbo,kimi-k3-1" 2000        # 跑评测（plain|resid，断点续跑，写 results_<mode>.jsonl）
node bench_vl2.mjs plain2 "glm-5.3,hy4std" 2000
.venv\Scripts\python.exe score_vl.py                          # 按 work/vlbench/labels.json 出准确率矩阵
.venv\Scripts\python.exe score_sweep.py                       # alpha 分档净检出
```
- 素材 `work/vlbench/{in,res,big,sweep}/`；完整报告 `work/vlbench/视觉模型选型报告.md`（三组表 + 六条发现 + 复现命令）
- 坑：PowerShell 传空字符串参数会被吞（`node bench_vl2.mjs plain2 "" 2000` 会把 2000 当成 model 名），评测时显式列模型。

#### 标签坑（别信现成的"正样本"）
`work/pp_4755/imgs` 那 20 张曾被当成"全带水印"的正样本，实测 6 个模型 **0/20 检出**、rapidocr 也读不出一个 store/cybertron 字样 ⇒ **该目录不是带水印的版本**，已从评测集剔除。要扩正样本必须从站点重抓整改前的图。

### W6 不做
- 不擦官方免责声明/版权行
- 不为「看起来干净」用 AI 重绘整图（等于改商品外观）
- 不用别家店的图替换
- 不追"压在机体上、1× 不可见"的残余水印（加强反而更糟，见 W7）
- 2050 张级批量擦除需明确许可

## 6. 交付
- **必须附 §5.7 交付体检的汇总行**：`==== 汇总：FAIL 0 / WARN n / 共 m 项 ====`，FAIL > 0 一律不许交付（修完重跑）
- **必须附残差拼图的判定结论**：`resid_montage.jpg` 逐格结论（哪些格子有字、是厂牌文案还是别家店名）
- **交付前逐条核对 SKU**：每个规格 `skuName` ↔ `skuImageUrl`，无盒=纯本体图、有盒=盒照，两个规格的图 URL 不能相同（4758 就漏了这一步，`verify` 现在会报 `[sku] !!`）
- 前后对照图（before/after sheet）+ 新图 URL + 改动前快照 JSON（可回滚）
- 说清楚改了哪几张、为什么、还剩什么问题

## 不擅自做的事
- 改价、改标题、改 modelCode（除非你确认）
- 删主图（除「横幅规则」外），尤其是纯盒子照/实拍图
- 把状态推进到「待生图 / 待导出」
- 全库批量处理（必须提前报数量、耗时、产物位置并拿到明确许可）
- 发布到速卖通（提交按钮永远不点）

## 环境坑
- Pillow 9.5.0：`ImageDraw.text` 用 truetype（simhei/arialbd/msyh）会段错误 `0xC0000005`；打标签只能用 `ImageFont.load_default()`
- PowerShell 输出中文需 `$env:PYTHONIOENCODING='utf-8'`
- AliExpress 外链下载要 `User-Agent` + `Referer: https://www.aliexpress.com/`，否则 403；不加 `Accept: image/webp` 会拿到 AVIF

## 7. 水印检查脚本索引（都在 ae-img-audit\）
| 脚本 | 用途 | 典型调用 |
|---|---|---|
| wm_tpl.py | 店铺水印模板匹配（超宽淡字类，定量） | `python wm_tpl.py build work/edgechk/old_998b.jpg 12 372 48 428`；`python wm_tpl.py scan work/p4049` |
| hp_cur5.py | 一批图的高通放大拼图（定性） | 改脚本内 URL 列表后直接跑 → work/hp_cur5.jpg |
| hp_detail4049.py | 详情图整批高通拼图（500px 一格） | 改文件前缀复用 → work/hp_detail4049.jpg |
| band_detail4049.py | 只切水印水平带（y=360–460）逐张对比，最好判 | 同上 |
| edge_zoom.py | 左右边缘 3× 放大对照（看首尾字母） | work/edge_zoom.jpg |
| wm2.py | 常规重复水印检测/擦除（OCR + 斜虚线 + TELEA，支持 --store 模板） | `python wm2.py <dir> --outdir <out> --erase --store` |
| wm_edge.py | 边缘条 OCR（**对本类超宽淡字无效**，仅作辅助） | `python wm_edge.py <dir>` |
| wm_faint.py | 平坦区残差占比（**已证伪，别用来下结论**） | 仅留档 |
| maskw2.py | 极淡整幅店名的**白底掩膜**（W7 配方，带 darkzone 保护） | `python maskw2.py <img> <out_ov.png> 200 251 [y0 y1]` |
| erase_4755.py | 整商品擦除（掩膜+LaMa+去重，产出 wm_out/*.png 与前后总览） | 改脚本内目录后直接跑 |
| wm_write4755.py | 擦后图上传 + 回填 main/detail/sku + descriptionJson 替换 + PUT + 拉回 PENDING | 同上 |
| verify_4755wm.py | 写入后稳定性与「旧 URL 是否还在」复查 | 同上 |
| chk_erase4755.py | 逐图统计白底灰色文字像素，量化擦除幅度 | 同上 |
| **check.py** | **交付体检（必跑）**：结构/计数/尺寸/重复/字形笔画/SKU 分派/description，出 `check/report.json` + `resid_montage.jpg` | `python check.py 4758`；看完拼图再 `python check.py 4758 --reviewed` |
| **pipeline.py skuset** | 显式分派 SKU 图（无盒/有盒各一张） | `python pipeline.py skuset 4758 "no retail box=main:1" "with retail box=main:0"` |
| **pipeline.py lock** | 锁 plan，防重复 apply 冲掉手工改动 | `python pipeline.py lock 4758 --reason "已交付"` |
| **vlmcheck.py** | **视觉大模型复核（§W9）**：一件商品的图交 glm-5v-turbo + kimi-k3-1 双判，出 CLEAN/REVIEW/HIT 表与 `vlm_report.json` | `python vlmcheck.py 4758`；`--kind main`；`--dir <本地目录>` |
| **bench_vl2.mjs** | 视觉大模型水印复核评测（21 模型横评，口径见 **§W9**） | `node bench_vl2.mjs plain "glm-5v-turbo,kimi-k3-1" 2000` |
| **score_vl.py / score_sweep.py** | 按 `work/vlbench/labels.json` 出准确率矩阵 / alpha 分档净检出 | `python score_vl.py` |

### 2026-11-06 的实测基线（改脚本后可对比）
- 4049 旧 main#2（有水印）：模板 NCC **1.000**；干净图 0.52–0.62
- 4049 当前 17 张（5 主图 + 2 SKU + 10 详情）：全部 ≤0.62，判干净
- 4049 主图 5 张 + 详情 10 张尺寸 800×800；有盒 SKU 盒照补白到 800×800
- 视觉大模型横评基线（2026-11-06）：glm-5v-turbo A 组 **8/8** / B 组误报 **7/21**（2.68 s/图）；kimi-k3-1 A 组 7/8 / B 组误报 **0/21**（详见 §W9）
- vlmcheck.py 基线（prompt 已加厂牌排除）：8 张标注图 **8/8**（21.6 s）；4758 现行 21 张 **21 CLEAN / 0 REVIEW / 0 HIT**（67.8 s，双模型 4 线程）
- 4755（2026-11-06 01:49 写入）：20 张唯一图全部带 “GT Cybertron Toy Store”，白底掩膜 1.35%–6.55%，擦后白底文字像素 -32%…-72%；main 6 / detail 14 / sku 2 全部换成擦后图，descriptionJson 14 处 URL 替换，status 稳在 PENDING（worker dispatched 停在 11）

## 8. 一键流水线 pipeline.py（2026-11-06 起的主路径）

一条商品的标准动作从 35–40 步压到 6 步。脚本：`ae-img-audit\pipeline.py`（纯 stdlib + opencv/Pillow；指纹缓存 `work/pipeline_fp.db`）。

```powershell
cd C:\Users\shana\Documents\deepseek-harness\default-workspace\ae-img-audit
.venv\Scripts\python.exe pipeline.py auto 4049            # 0) 新：取数+判定+分类，一件一句话结论（§10）
.venv\Scripts\python.exe pipeline.py scan 4049            # 1) 下载+指纹+出方案（约 11 s / 20 张）
.venv\Scripts\python.exe pipeline.py scan --snapshot <before.json>   # 对历史快照回归，不联网
.venv\Scripts\python.exe pipeline.py set 4049 main_1=DELETE main_2=REPLACE:detail_6   # 2) 人工改判
.venv\Scripts\python.exe pipeline.py apply 4049 --dry-run  # 3) 预演
.venv\Scripts\python.exe pipeline.py apply 4049            # 4) 上传→PUT→自动拉回 PENDING
.venv\Scripts\python.exe pipeline.py verify 4049           # 5) +3/+20/+60 s 复查
.venv\Scripts\python.exe pipeline.py skuset 4049 "no retail box=main:1" "with retail box=main:0"   # 6) SKU 图分派（右侧也可给本地文件路径）
.venv\Scripts\python.exe pipeline.py lock 4049 --reason "已交付"                                     # 7) 锁 plan，防重复 apply 把手工改动冲回去
```

产物（`work/pp_<id>/`）：`plan.json`（每张图的判定、证据、动作）、`overview.jpg`（全部图一张看）、**`resid_sheet.jpg`（残差×12 总览，水印位置一眼可见，替代逐张看图）**、`apply_log.json`。

判定顺序：孪生干净版 → REPLACE；否则中文海报 → DELETE / CN_POSTER；否则整幅横幅 → CROP_OR_DELETE（加 AI 封面后 >6 张才删，≤6 张裁）；否则 REVIEW（有店名水印但无替代）。
**唯一例外（用户 2026-11-06）**：判成盒照（`box`）的图不参与「删」，最重只到「裁横幅」——`analyze` 会把 DELETE/CN_POSTER 改成 CROP_OR_DELETE（有横幅）或 KEEP（无横幅），`apply_plan` 再兜一层。

## 9. 外部找图换图 websrc.py（2026-11-06，与 §8 配套）

站内没有干净版时，去厂商/经销商图库找同款官方原图。脚本 `ae-img-audit\websrc.py`（被 pipeline 以 import 调用，纯 stdlib + 可选 rapidocr）。

```powershell
# 找图 + 打分（约 60–90 s：DDG 页面通道 + bing 图片通道 + OCR 校验）
.venv\Scripts\python.exe pipeline.py web 4755
# 已知好图库（本地已下载过的官方图）一起纳入候选池——命中率显著提升
.venv\Scripts\python.exe pipeline.py web 4755 --extra-dir "work/src4755/kapow/*.jpg"
# 选定后写入 plan 并落地
.venv\Scripts\python.exe setfix.py "main_1,main_3,detail_2,detail_3" 14
.venv\Scripts\python.exe pipeline.py apply 4755 --dry-run
.venv\Scripts\python.exe pipeline.py apply 4755
```

候选来源：①DuckDuckGo HTML 版 `html.duckduckgo.com/html/?q=` 解析 `result__a` 的 uddg 参数 → 打开结果页抓 og:image / srcset 最大图（**bing 网页搜索不可用，解析出的是无关结果**）②bing 图片异步接口 `www.bing.com/images/async?q=`（解析 `murl`）③`--extra-dir` 本地图库。

判定：只对 phash 距离 ≤22 的 top6 近邻跑 OCR（1 s/张，缓存 `work/pp_<id>/web_ocr.json`）；**STRONG = OCR 读到型号且 dist ≤12**，WEAK = 有命中但超阈值；候选 OCR 出现 店/shop/store/淘宝/天猫/aliexpress/amazon/ebay 一律丢弃。

**两个坑（都踩过）**
- `pipeline.py web <pid> --set …` 会**重新抓一轮**再写入，且会覆盖 `web.json` 与 `plan.json`。若上一轮用了 `--extra-dir`，这一轮忘了带 → 命中大幅减少、plan 被打回 KEEP。**改判请用 `setfix.py`**（只读缓存 `web.json`，不重抓）。
- 候选图是 2048×1743 这类非方形：主图走 `pad_square` 补成 800×800（白底，看不出接缝），详情图走 `fit_long(1200)` 只缩不放。

**4755 实测结果（混合方案，2026-11-06T02:53:52 上线）**：19 张里 16 张换成官方原图（主图 1/2/3/4 dist 12/14/8/8 + 详情 2..13 dist 0–2），主图 0/5 与详情 0/1 无同款官方图 → 保留 V13 LaMa 擦除版；descriptionJson 12 处旧 URL 自动 remap，18 块结构完整（1 标题 + 14 图 + 2 文本 + 1 shopFooter）。**换图后整页零水印，且没有一处 LaMa 补痕。**
**已知边界**：超宽淡字水印（宽度接近 800、透明度 <20%、OCR 只能读到半句）无法自动判定，**必须看一眼 `resid_sheet.jpg`**——四商品回归里 72% 自动正确，剩下 28% 全是这一类，在残差图上肉眼一清二楚。改判用 `set`，不要手动改 JSON。

### 9.1 整批主图换外部图（2026-11-06 商品 4564 实操，7 张主图全废时走这条）

主图**每一张**都带别家店横贯淡字、站内又没有干净版时（4564 = `Transform And Roll Out Store` 压在 7 张主图上），别再逐张擦，直接整批换外部官方图。

```powershell
# 1) 自写搜索（按 url 合并进 work/review5b/cands<pid>.json，不会顶掉前一轮）
.venv\Scripts\python.exe websearch.py 4564 "Age of the Primes Voyager Sky Byte|... |..."
# 2) 看候选拼版（6 列 260px + 序号）
.venv\Scripts\python.exe candsheet.py 4564          # -> work/review5b/cand4564_sheet.jpg
# 3) 把候选里**能用的**下载成统一编号，批量过水印
.venv\Scripts\python.exe pickcand.py 4564 03,05,07,25,28,61,77
.venv\Scripts\python.exe vlmcheck.py --dir work/review5b/web4564
# 4) 同款验证（两张图一起送 glm-5v-turbo，判 same_figure / same_product / box_series）
.venv\Scripts\python.exe cmpvl.py 4564 main_0 28,61,77
# 5) 落 plan：逐个 REPLACE_WEB（参数必须 name=path）
.venv\Scripts\python.exe patchweb.py 4564 "main_0=work/review5b/web4564/c28.jpg" ...
.venv\Scripts\python.exe pipeline.py apply 4564 --dry-run
.venv\Scripts\python.exe pipeline.py apply 4564
```

**找干净孪生（最高效的一招）**：先用 pHash 把候选和站上现存图配对（`matchlib.py` / `pair4564.py`），距离个位数就是**同一构图的干净版**——4564 的 main_1(盒照)~c61 距离 5、main_4~c77 距离 0，直接对上，构图完全不变。注意 main_0~c24 距离 0 但 c24 本身带水印（是 AliExpress 转图）⇒ **配对后仍要过一遍 vlmcheck**。

**图片源的水印风险清单（实测）**：transformers-universe.com 图库质量最高但**每张右下角都有自己的站名** `TRANSFORMERS-UNIVERSE.COM`（双模型一致 HIT）⇒ 整站不可用；干净源：transforverse.eu、playtoys.com.au、collectoverse.ca（G1019-detail 系列=哈斯布罗官方电商图）、nerdzoic、brincatoys、kidzstation。bwtf.com / thefwoosh 的老评测图多为 2014 Generations 同模具**不同系列**，必须 `cmpvl` 判 `same_product` 才能用。

**换图后的两个连带动作**：①主图超限要删时，删 figure、别删盒照（apply 的盒照保护会把 DELETE 顶回 KEEP，导致 7 张主图不收敛）；②换完必须重跑 `skuset`（apply 会把 images.sku 一起换掉，两规格易变成共用一张）。**F3 假警**：全量换图后 plan 里的 box 字段是旧的，check.py 的 F3 会误报「图池盒照 0 张」；2026-11-06 已改成对新 URL 现场判一次（`is_box_photo` 带缓存），4564 从 WARN 1 → WARN 0。

## 10. 批量与提速 pipeline.py auto（2026-11-06，用户问「怎么加快处理商品的速度」）

一条命令替代「scan → 看 plan → apply → verify」，默认**只出结论不写站**，加 `--apply` 才落地。

```powershell
cd C:\Users\shana\Documents\deepseek-harness\default-workspace\ae-img-audit
.venv\Scripts\python.exe pipeline.py auto 4049                      # 单件：scan + 分类，不写站
.venv\Scripts\python.exe pipeline.py auto --pending 20 --jobs 6     # 从站上按状态抓 20 件待编辑，6 线程并行 scan
.venv\Scripts\python.exe pipeline.py auto --batch "4572,4574,4644" --jobs 4
.venv\Scripts\python.exe pipeline.py auto --pending 20 --jobs 6 --apply   # 只写 AUTO 类，REVIEW 一律不动
.venv\Scripts\python.exe pipeline.py auto --pending 20 --reuse           # 复用已有 plan.json，不重扫
```

**分类（决定要不要花人力）**

| 类别 | 含义 | 是否写站 |
|---|---|---|
| `CLEAN` | 全部 KEEP、结构正常（main≥1、detail≥1、有 sku 图） | 不写，直接放过 |
| `AUTO` | 只有全自动动作（REPLACE / REPLACE_WEB / CROP_OR_DELETE / DELETE / SMALL）或结构缺项**且有可自动执行的动作** | `--apply` 时写 |
| `REVIEW` | 有 `REVIEW` 动作；或 SKU 异常（缺 skuImageUrl、多规格**共用盒照**）；或被判「中文海报」`CN_POSTER`；或结构缺项但**没有**任何可自动执行的动作 | **一律不写**，必须人看 |
| `DONE` | plan 已 `lock`（已交付） | 不写 |

**提速账（实测 2026-11-06）**

| 环节 | 改前 | 改后 | 依据 |
|---|---|---|---|
| 复查等待 | `waits=(3,20,60)` = 83 s 纯 sleep | `auto` 默认 `(3,20)` = 23 s | 后两次读数本来就是同一结论 |
| CLEAN 商品 | apply 35 s + verify 83 s + check 10 s + vlmcheck 68 s | **0 s**（不写站） | AUTO-PASS |
| 多件扫描 | 串行 5.9 s/件 | 6 线程 **4.5–6.9 s/件** | 下载串行化后 OCR/指纹并行 |
| 挑活 | 手工翻后台拿 id | `--pending N` 按状态直接取 | `GET /api/admin/products?status=PENDING&page=&size=50`（站上现有 304 件 PENDING） |

单图开销：OCR **1.32 s/张**（只对 main/sku 跑）≫ 解码+pHASH 11 ms ≫ 下载 0.16 s/张。OCR 结果按 url 缓存在 `work/pipeline_fp.db` 的 `fp` 表 30 天 ⇒ **同一件第二次扫几乎免费**（4754 冷 16 s → 热 3 s）。

**坑**
- 并行 scan 时 `Site.download` 被 RLock 串行化（HTTP 本来不是瓶颈）；`Site.instance` 是单例，别在多线程里各自 `login()`。
- `analyze` 会读 plan 的 `locked` 字段并**拒绝覆盖**（返回旧 plan），要重扫已交付商品必须 `--force-unlock`。
- `REVIEW` 不会被 `--apply` 写入，这是刻意的：水印无替代、SKU 语义反了这类动作自动落地等于制造事故。
- 批量 `--apply` 顺序写站（上传 + PUT + 拉回 PENDING + verify），不要并发写同一件商品。
- **`CN_POSTER` 不进 AUTO**：中文海报判据（≥2 行中文且面积 ≥4%）在 4758 上把厂牌官方文案「钢铁战瑰/铁鼠MAUS/YW2611/易玩天明」误判成海报 6 张，自动删就是删掉合法产品图 ⇒ 现在只提示、转人工（`REVIEW_ACTS`）。
- **`AUTO no-action` 不再出现**：结构缺项（少 main / 少 detail / 没 sku 图）但 plan 里没有任何可自动动作时，以前会显示 `AUTO no-action`（看着能自动落地，实际什么也不会做），现在直接判 `REVIEW` 并提示「需人工补图」。

**2026-11-06 实测发现的系统性问题**：11 件待编辑商品里 8 件最初判 REVIEW，原因都是"规格数 > 唯一 SKU 图数"。按用户当天定的新规则（**可以共用本体图、不能共用盒照**）复查后，这类大部分是**允许的**：4755 共用的那张经 `vlmcheck.kind_of_file` 判定为 `figure`（本体宣传图）→ D2 直接 PASS。
⇒ `sku_problem()` 现在只把两种情况算坏：①有规格缺 `skuImageUrl` ②**多规格共用了盒照**。判定盒照会调一次 VLM（约 2.7 s/图，结果缓存在 `work/sku_box.json`），所以 `auto` 的 SKU 检查只对"多规格共用一张图"的商品才付费。

**2026-11-06 复跑（同一批 11 件，`--reuse`，scan 0.2 s）**：`AUTO=3 CLEAN=3 REVIEW=5`（改判前 `AUTO=5 CLEAN=3 REVIEW=3` 里混着 1 件 CN_POSTER + 1 件 no-action）。
- AUTO 三件：4646 `CRO1`、4647 `SMA1`、4649 `CRO1`（都是整幅横幅裁方 + 尺寸补边这类纯几何动作）。
- REVIEW 五件：4571（review=11、`CRO2`、水印无干净替代）、4572（`REP2 CRO6` + **多规格共用盒照**）、4574（review=8 + **多规格共用盒照**）、4645（1 张判中文海报，需确认是不是厂牌文案）、4648（结构缺项、无自动动作）。
- 结论：**能安全全自动的只有"纯几何整形"**（裁横幅、补 800×800）；凡涉及"删图/判海报/判盒照/水印无替代"都必须留人工，这三类恰好也是人力开销所在。



### 10.1 省掉纯等待（2026-11-06 实测）

原来单件流水线里约 9 分钟是纯 sleep，现在压到 3–4 分钟（只剩站上 worker 生成）：

| 环节 | 原来 | 现在 | 怎么改的 |
|---|---|---|---|
| `verify` 稳定性核对 | 83 s（3/20/60 三点死等） | **约 13 s** | 连采两次快照一致且已过 10 s 就提前收工；默认 waits 改成 (3,12,25) |
| `check.py` 单件 | 约 40–50 s | 单件约 1 s（缓存热） | 图片改成 8 线程并行下载；`--stable 0` 跳过 6 s 稳定性等待（写入后 verify 已查过） |
| `check.py` 5 件两轮 | 约 4 分钟 | **6 s** | 新增 `--batch "4647,4758" --jobs 5`，多件并行 |

用法：

```powershell
.venv\Scripts\python.exe check.py --batch "4647,4758,4754,4049,4649" --jobs 5 --stable 0 --reviewed
```

两个配套修正：
- **check.py 的图片缓存改成按 URL 校验**（`work/pp_<pid>/check/.urls.json`）。之前按文件名缓存：整改/生成后 main_0 还是 main_0、URL 却变了，于是拿整改前的旧图做体检 —— 本轮就因此假报过一次「main_4 与 main_5 近乎同图」。
- **A1 现在接受 PENDING / EDITING / READY_TO_PUBLISH**，所以推进到待生图之后也能跑体检；status=DONE（已导出）才报 FAIL。

省不掉的：worker 生成 AI 封面 3–4 分钟（这段时间可以去写报告/处理下一件），以及人的两个判断点（看残差拼图、核 SKU 语义）。

### 10.2 五项并发/复用改造（2026-11-06 落地，配套 §10.1）

上一批 5 件实测 37 分钟（16:29:00→17:05:52，按文件 mtime 拉的时间线），耗时结构：扫描 89 s、VLM 双模型复核 210 s、拼版+盒照分类 90 s、看图定处置 225 s、写入 4 件 397 s、**4564 找图 870 s（占 40%，官方通道失效那次）**、体检 270 s。改造后同类批次的固定成本约砍掉 6–8 分钟：

| 改造 | 代码位置 | 收益 |
|---|---|---|
| 盒照分类并行 + 结果缓存 | `pipeline.box_kinds(pairs, workers=8)`，`sku_box.json` 写加锁 | 42 张 VLM 从 113 s → 约 20 s |
| VLM 复核批量化 | `vlmcheck.py --pids`（多件合并一个任务池、8 线程，报告 `work/vlm_batch/vlm_report.json`） | 5 件×2 模型从 210 s → 约 60 s |
| 本地官方图池 | `imgpool.py`（pHash 索引 `work/imgpool/index.json`，574 张已入库，建库 3.1 s） | 同类商品直接命中，省掉整轮联网找图（最贵的一项） |
| 一次时间轴复查 | `pipeline.verify_many(pids, waits=(3,12,25))` | 5 件从 5×(3+12+25) 串行 → 1 轮约 25 s |
| 体检提速 + 多件拼屏 | `check.py --fast`（=stable 0）、`mkmulti.py` | 体检 270 s → 约 40 s；看图从翻 5 个页面变成一张图 |

用法：

```powershell
.venv\Scripts\python.exe pipeline.py auto --pending 5 --vlm          # 扫描+VLM批量复核+并发盒照
.venv\Scripts\python.exe pipeline.py multi 4562,4563,4564,4565,4557 --pending 0   # 主图拼一屏
.venv\Scripts\python.exe check.py --batch "4562,4563" --jobs 5 --fast --reviewed
.venv\Scripts\python.exe imgpool.py build                            # 重建本地官方图池索引
```

两条硬约束（本轮踩出来的）：
- **`apply` 默认 dry-run**，必须显式 `--write` 才写站（4571 就是没加 --dry-run 被写进去的；写前快照 `work/pp_<pid>/before_apply.json` 是唯一救回来的凭据）。
- **`WEB_DEFER` 绝不留空**：保持原 URL，只登记 `work/web_pending.json`；删成空会让主图变少、sku 图为空。


## 11. 一件商品一个子任务（2026-11-07 用户明确要求）

- 用户原话：「为了避免偷懒，我要求你以后审核每个商品的时候 单独开一个子任务来处理」。⇒ **每件商品单独派一个 subagent**，禁止把多件合并成一次批处理。
- 子任务 prompt 用固定模板：**`子任务模板-单件商品.md`**（环境 / 九步流程 / 硬规则 / 交付物 / 已知坑 / 完成标准），把 `{{PID}}` 等占位符替换即可。不要凭记忆手写，会漏口径。
- 子任务只许写 `work/pp_<pid>/` 与该商品本身；`pipeline.py` 等共享脚本只读。
- 子任务默认把商品留在 `PENDING`（待编辑），**推进状态与「待发布」由 Lead 定**。
- **Lead 必须独立验收**，不许只看子任务自述：自己重下线上全部图、独立 OCR、核对张数/尺寸/main[0]/descriptionJson 死链，结论记进 `work/verify/验收记录.md`。
- 2026-11-07 首批 3 件（4571 / 4572 / 4574）的验收记录在 `work/verify/验收记录.md`，可作为写法样例。
