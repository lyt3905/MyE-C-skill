# 商品英文标题重写 SOP（站内 https://39.107.244.239）

> 沉淀自 2026-11-06 READY_TO_PUBLISH 23 件批量重写 + 用户的 7 条修订。
> **2026-11-07 用户修订（最新，覆盖旧口径）**：
> 1. **前缀按店铺，不写死**：`62店`（id=4，1105382170）→ `In Stock`；`shana1`（id=7，1105641114）→ `Hot Sale`。
> 2. **型号编号有就必填**（`identityJson.modelCode`），**写法优先带横线**（`NA-H74` 优于 `NAH74`），标题里双格式带出。
> 3. **品牌字段按商品类型审核，商品 logo 不审**：标题/商品属于变形玩具或变形金刚 → `brand=200017853`（孩之宝/Hasbro）；否则 → `brand=200014695`（万代/Bandai）。`identityJson.logoCode` 保持原值。
> 4. 写回统一走 `s.save(pid, extra={...})`，**禁止裸 PUT**（见 §5）。
>
> **维护口径（2026-11-07 分层去重）**：**本文是标题与编号规则的唯一正本**——字段口径、模板结构、分支判定、编号规则、字数与压缩顺序、替换表、判例库、坑都写在这里。
> 派单文件 `子任务模板-单件商品.md` 只保留执行清单（占位符与店铺前缀、写回 API、十一 步流程、交付物、完成标准）并对本文 §1–§4 起指针，**不再复制判据**；skill `SKILL.md` 的 §2/§3 是入口摘要。
> ⇒ **改规则只改本文 + skill 摘要，别在模板里加判据**；三处若冲突，以本文为准。
>
> 历史线（只作记录）：11-06 全部用 `In Stock`；11-07 09:54 把当时 70 件 `READY_TO_PUBLISH` 的 `titleEn` 批量换成 `Hot Sale`（旧值在 `work/title_hotsale_log.json`）。那批没区分店铺，若其中混有 62店 商品，需按 §1 回改。§6 判例库保留 `In Stock` 写法作为历史记录。

## 0. 字段口径（先搞清楚写哪儿）

| 字段 | 含义 | 要不要改 |
|---|---|---|
| `title` | 原标题（淘宝源是中文，速卖通源是卖家英文原文） | **不动**，作溯源 |
| `titleEn` | 英文标题 —— 站点表单里带「AI 标题生成」按钮的那个，**上架用的是它** | **改这个** |
| `titleTranslationZh` | 中文回译（**服务端生成，表单不可编辑**） | 每次改完 `titleEn` **必须调翻译接口重新生成**（见下方 ②） |
| `identityJson.modelCode` | 型号编号 | **有就必填**；优先带横线写法；挖不到留空不编 |
| `identityJson.logoCode` | 商品 logo 编号 | **不动**（用户明确：logo 不用管） |
| `brand` | 品牌属性字典 code | **审核**：变形玩具/变形金刚 → `200017853`（孩之宝/Hasbro）；否则 → `200014695`（万代/Bandai） |
| descriptionJson 里的 `SHOP_TITLE` 文本块 | 详情页顶部店招标题 | **不用手工改**：服务端按新 `titleEn` 自动重算（2026-11-06 实测 4/4 同步） |

写回接口（2026-11-07 在 4826 单件实测校准，**标题与中文标题分两条路，别混**）：

**① 标题 + 编号 → `Site.save()`**

```python
import json
s.save(pid, extra={'titleEn': t,
                   'identityJson': json.dumps({'logoCode': lc, 'modelCode': mc})})
# = PUT /api/admin/products/{id}?autoSave=true，额外字段在 site_client.py 的 Site.save() 里 body.update(extra)
```
- `identityJson` 必须传 **JSON 字符串**：传 dict 服务端回 `HTTP Error 400` 且报错体为空，很难自查。
- `logoCode` 原样透传（不改它，只是必须带在同一个 JSON 里）。

**② 中文标题 → 翻译接口，不要写字段**

```python
s.call('/api/admin/products/%d/translate-title' % pid, {'titleEn': t}, method='POST')
# → {"success":true,"data":{"titleTranslationZh":"热销 变形金刚 工作室系列 SS86 …"}}，服务端直接落库
```
- 4826 实测：改前 `titleTranslationZh = None` → 调完回读得到中文，`titleEn` 不变。
- `save(extra={'titleTranslationZh': ...})` **完全无效**：前端提交体里根本没有这个字段，服务端也就不认。

**③ 回读校验**：`s.product(pid)` 确认 `titleEn == t`、`titleTranslationZh` 非空且与新标题语义一致、`identityJson` 里编号正确；**挖不到编号时 `identityJson` 就是 `{"logoCode":""}`、没有 `modelCode` 键，这是正常形态，不是写入失败**（前端序列化器只在编号非空时才写该键）。
**不要**再用 `s.call('/api/admin/products/%s'%pid, d, method='PUT')` 裸写：会触发全量重传 + 自动生成封面 + 状态跳 `EDITING`（「待生图」）。
⚠️ **`weight` 必须随 body 回传**（2026-11-07 查清）：`autoSave` 的 PUT 是「缺字段填默认值」的全量覆盖，body 缺 `weight` 就把重量重置成默认 **0.3**，并重算 `shippingFee`（0.2→0.3 时 7.43→8.8）。`Site.save()` 现已自动回传当前重量，正常改标题不会动重量；要改重量才写 `extra={'weight': x}`，`shippingFee` 是派生值**不要手写**。历史漂移用 `scripts/restore_weight.py` 复原。

---

## 1. 模板与分支

`{PREFIX} [Transformation] [品牌] [系列] [编号] [角色] [修饰1 修饰2] [属性] Action Figures Collection Gifts`

`{PREFIX}` 按店铺取（先确认商品归属，见 §0 备注 / 站点 `/api/admin/shops`）：

| 店铺 | id | shopAccount | 前缀 |
|---|---|---|---|
| 62店 | 4 | 1105382170 | `In Stock` |
| shana1 | 7 | 1105641114 | `Hot Sale` |

两个前缀等长（8 / 8 字符），换店不影响字数预算。

**分支 A（加 `Transformation`）**——满足任一：
- 原文出现变形金刚角色名（擎天柱/威震天/大黄蜂/红蜘蛛…）
- 原文出现「变形 / 变形玩具 / 变形金刚」
- 原文出现第三方变形品牌（银河玩具社 / MFT / 梦星 / X-TRANSBOTS / 威双 / 吴医生 / 魔方 / NewAge / MMC / 招财猫 / 大匠社 / BINGOTOYS / RT / ToysMage / Collection Space…）

**分支 B（不加 `Transformation`）**——都不是时：手办 / 机娘 / PVC / 可动人偶（AniMester、万代、GSC、蜗之壳、APEX、LIMEPIE、Action Toys…）。

---

## 2. 字段规则（含 2026-11-06 用户修订）

### 2.1 品牌（标题内的品牌词）
- **只取原文明确出现的品牌**，不得从搜索结果补入制作方/发行方。
- `孩之宝 / Hasbro` → **删除，不输出**（KO/第三方款尤其要删）。
- `Collection Space / 收藏空间` → 固定 `Collection Space`；`原子盒` → `O&BOX`（原文写 Atom Box 才输出 Atom Box）。
- 多个品牌 → 只留第一个；原文没品牌 → **省略**，不用搜到的品牌填。
- 未收录品牌 → 保留原文（英文名明确的不用标 ⚠️，中文未收录才标）。
- **例外（用户 2026-11-06 指令）**：用户点名要写的品牌可以补进去，如 4560 的 `FLEMING`（品牌方海报上印的 FLEMING GALILEO）。
- 注：本节只管**标题里的品牌词**；商品 `brand` 字段另按 §0 的商品类型规则核对，不能把字段 code 机械写进标题。

### 2.2 角色名
1. 先查 §3 替换表 → 2. 变形金刚官方角色用官方英文名 → 3. 非变形金刚专有名词可联网搜标准名 → 4. 搜出歧义标 ⚠️ 并列候选，不许静默猜。
- 多个角色按原文顺序排，空格分隔；统称 + 具体同时出现时只留具体。
- **用户 2026-11-06 修订：原文没写角色名时，若同型号的姊妹 listing / 商品图能确认角色，就补上；实在找不到才省略。**（例：4558 与 4573 同为 `TMT-02`，4573 原标题写明 `Beetle Wasp` → 4558 补 `Beetle Wasp`。）

### 2.3 编号（2026-11-07 修订：带横线优先，且必须落库）

**两条硬要求**
1. **`identityJson.modelCode` 有就必填**：能从 原文标题 / SKU 名 / 描述区参数表 挖到型号编号，就必须写进 `identityJson.modelCode`；挖不到留空并在报告写「原文无编号」，**不许编造**。
2. **写法优先带横线**：`NA-H74` 优于 `NAH74`；`SS86-05` 优于 `SS8605`。原文写法不统一时先统一成带横线再判断。

**标题里的双格式**：带横线的在前、去分隔符的在后（与 11-06 的「原文格式在前」顺序对齐，统一为横线优先）：
`NA H74` → `NA-H74 NAH74`；`MS-01` → `MS-01 MS01`；`MF35` → `MF-35 MF35`；`DW-E09T` → `DW-E09T DWE09T`；`MC02-ICE` → `MC02-ICE MC02ICE`；`RT07EX` → `RT-07EX RT07EX`；`DX9D08` → `DX9-D08 DX9D08`。
多编号按原文顺序；错误编号过滤掉。

**超字数时**（与 11-06 指令相反，以 2026-11-07 为准）：**保留带横线版本，删去分隔符版本**；主编号必留，适配编号/次要编号可整条删。**绝不许为了字数把编号全删掉。**

### 2.4 修饰词 / 属性 / 系列
- 修饰词查表，多个只留前两个。
- `变形机器人 / 变形玩具` → 省略（与前后缀重复）；`手办摆件周边` → `Figure Set`；`手办 / 手办摆件` → `Figure`。
- **配件包必须有 `Upgrade Kit`（用户 2026-11-06 硬规则）**：只要原文/商品性质是配件包、升级件、改造件，标题里**必须**出现 `Upgrade Kit`，任何字数压缩都不许删它。同理 `Figure Set` 这类承载核心卖点的属性也不许为凑字数删掉。
- 系列查替换表（传世→Legacy、天尊世代→Age of the Primes、SS86→Studio Series SS86、围城→WFC Siege、领袖之证→TFP、起源→ONE、Masterpiece→MP…）。

### 2.5 缺字段
直接省略，不占位、不用默认词填。

---

## 3. 替换表（合并版）

| 中文 | 英文 | 类型 |
|:---|:---|:---|
| 银河玩具社 / 银河社 | Galaxy Toys | 品牌 |
| x社 | X-TRANSBOTS | 品牌 |
| 大漫匠 | AniMester | 品牌 |
| 梦星 | DREAM STAR TOYS | 品牌 |
| 吴医生 | DrWu | 品牌 |
| 威双 | Weishuang | 品牌 |
| MFT | MFT | 品牌 |
| 魔方 | MS-TOYS | 品牌 |
| 招财猫玩具 | Lucky Cat Toys | 品牌 |
| 大匠社 | Dajiang Studio | 品牌 |
| Collection Space / 收藏空间 | Collection Space | 品牌 |
| 原子盒 | O&BOX（默认）/ Atom Box（原文 Atom Box 时） | 品牌 |
| 孩之宝 / Hasbro | **删除** | 品牌 |
| Masterpiece | MP | 系列 |
| 传世 / 传世遗产 | Legacy | 系列 |
| 天尊世代 | Age of the Primes | 系列 |
| 领袖之证 | TFP | 系列 |
| 起源 | ONE | 系列 |
| 围城 | WFC Siege | 系列 |
| 传世联合 | Legacy United | 系列 |
| SS86 | Studio Series SS86 | 系列 |
| SSONE | Studio Series ONE | 系列 |
| 少女前线2:追放 / 少前2 | Girls' Frontline 2 Exilium | 系列 |
| 塞伯世界 | CyberWorld | 系列 |
| 擎天柱 | OP Commander | 角色 |
| 大黄蜂 | Bee | 角色 |
| **威震天** | **Megatank**（绝对强制，任何场景不用 Megatron） | 角色 |
| 钢索 | Grimlock | 角色 |
| 红蜘蛛 / 星星女王 | Starscream | 角色 |
| 震荡波 | Shockwave | 角色 |
| 机器昆虫 | Insecticon | 角色 |
| 反冲 | Kickback | 角色 |
| 炸弹 | Bombshell | 角色 |
| 弹片 | Shrapnel | 角色 |
| 挽歌 | Dirge | 角色 |
| 喷气机 | Ramjet | 角色 |
| 冲锋 | Thrust | 角色 |
| 三尖头 | Seekers | 角色 |
| 飞机小队 | Seeker Squad | 角色 |
| 警力神 | POLICE CAR WARRIOR | 角色 |
| 可露凯 | Klukai | 角色 |
| 蔚蓝轨迹.Ver | Azure Trajectory.Ver | 角色 |
| 神光 / 星之光 / 柱哥（神光版） | Star Convoy | 角色 |
| 鳄鱼精 / 鳄龙 | Skullcruncher | 角色 |
| 飞标 / 淤泥 / 铁渣 / 嚎叫 | Swoop / Sludge / Slag / Snarl | 角色 |
| 银霹雳 / 背离 / 变速箱 / 探长 / 千斤顶 / 营救车 / 消防车 | Silverstreak / Swerve / Gears / Hound / Wheeljack / Hoist / Inferno | 角色 |
| 吊车 / 拖斗·翻斗车 / 搅拌机 / 清扫机 / 推土机 / 铲土机 / 超载 | Hook / Long Haul / Mixmaster / Scrapper / Bonecrusher / Scavenger / Overload | 角色 |
| 浪客 / 挡板 / 天狼 / 闹翻天 / 惊天雷 / 天火 / 补天士 | Runabout / Tailgate / Fangry / Skywarp / Thundercracker / Jetfire / Rodimus | 角色 |
| 加强级·D级 / 航海家级·V级 / 核心级 / 领袖级·L级 / 指挥官级 / 泰坦级 / 传奇级 | Deluxe / Voyager / Core / Leader / Commander / Titan / Legends | 修饰 |
| 迷你版·极小迷你版 / 小比例·极小比例 | Mini / Small Scale | 修饰 |
| 再版·再再版 / 原创 / 动画色 / 金属色 | Reissue / Original / Animation Color / Metallic | 修饰 |
| 会场限定 / 战损版 / 限定版 / KO | Convention Exclusive / War Damage Version / Limited Edition / KO | 修饰 |
| 配件包 | Upgrade Kit | 属性 |
| 手办 / 摆件 / 周边 / 手办摆件周边 | Figure / Ornament / Merchandise / Figure Set | 属性 |
| 变形机器人 / 变形玩具 | **省略** | 属性 |

---

## 4. 字数（≤120）与压缩顺序

判据：`assert len(title_en) <= 120`（字符数，不是字节）。

超过 120 时按序删，每删一级重测：
1. 删 [修饰词]
2. 删 [系列名]
3. [品牌名] → `TF`
4. 仍超 → 把角色统称/次要角色按原文顺序从后往前删
5. 仍超 → **编号去分隔符版本**（保留带横线版；这条排在最后，2026-11-07 修订）

**不许删**：固定前后缀（`{PREFIX} … Action Figures Collection Gifts`）、`Upgrade Kit`、主编号。
**保底**：产品名 + 固定前后缀必须在。

判例（旧）：4647（配件包，超限 121 字）→ 保住品牌 `DNA`，删掉带横线的编号版本（`DK-52` → 只留 `DK52`），得 115 字。
**该例的取舍顺序已于 2026-11-07 反转**：现在宁可把品牌降 `TF`、删修饰/系列，也要留住编号的横线版。

---

## 5. 操作流程（每批都这么走）

1. **取清单**：`GET /api/admin/products?status=READY_TO_PUBLISH&size=50&page=N`（响应形状 `{success, data:{items:[...]}}`）。
2. **取全量**：逐件 `GET /api/admin/products/{id}`，记 `title`、`titleEn`、`titleTranslationZh`、`identityJson`（modelCode/logoCode）、`brand`、`sourceUrl`。
3. **判店铺**：确认这件属于 62店（`In Stock`）还是 shana1（`Hot Sale`）；旁证看 `descriptionJson` 里的店铺链接账号（`_shopread.py`），拿不准问 Lead。
4. **备份旧值**：`work/title_<批次>.json` 存 `{id: {old_titleEn, old_titleTranslationZh, old_modelCode, old_updatedAt}}`；改完写 `work/title_apply_log.json`。
5. **出标题/编号**：按 §1~§4 判，写进脚本 dict，先 `assert len(t) <= 120` 再 dry-run 打印（含新旧对比、前缀、编号两格式）。
6. **写入**：先 `s.save(pid, extra={'titleEn': t, 'identityJson': json.dumps({'logoCode': lc, 'modelCode': mc})})`，再 `s.call('/api/admin/products/%d/translate-title'%pid, {'titleEn': t}, method='POST')` 生成中文回译；最后 `s.product(pid)` 回读确认 `titleEn`、`titleTranslationZh`、编号都对上、`status` 未变、`descriptionJson` 里 SHOP_TITLE 已同步。
7. **交付**：出「id / 店铺 / 字数 / 新标题 / 编号(old→new)」表 + ⚠️ 待确认项，写明备份路径以便回滚。

模板脚本：`titles23.py`（批量，旧版用裸 PUT，需改为 `s.save(extra=...)`）、`fix_titles.py`（个别修正）。都用 `from pipeline import Site; Site.instance = Site()` 复用登录态。

---

## 6. 判例库（2026-11-06 首批 23 件 + 4 件修正）

> 下表是**历史记录**，当时前缀统一 `In Stock`。现按 §1 依店铺取前缀；编号顺序按 §2.3 改为横线在前。

| 商品 | 新标题 | 备注 |
|---|---|---|
| 4556 | In Stock Transformation MS-TOYS MS-B11 MSB11 Overlord Original Action Figures Collection Gifts | 魔方=MS-TOYS |
| 4560 | In Stock Transformation FLEMING BT08-05 BT0805 Galileo Action Figures Collection Gifts | FLEMING 用户指定补入 |
| 4566 | In Stock Transformation DX9 MP DX9-D08 DX9D08 Blitzwing Reissue Original Action Figures Collection Gifts | DX9 未收录但英文名明确 |
| 4558 | In Stock Transformation TMT TMT-02 TMT02 Beetle Wasp Action Figures Collection Gifts | 角色取自同型号姊妹 listing 4573 |
| 4569 | In Stock Transformed Toys Juggernaut Action Figures Collection Gifts | 分支 B（1/12 可动人偶），Hasbro 按规则删 |
| 4568 | In Stock Transformation WW-01 WW01 Bee Original KO Action Figures Collection Gifts | 大黄蜂→Bee |
| 4567 | In Stock Transformation DrWu DW-ES10 DWES10 DW-ES11 DWES11 Artillery Air Burst Action Figures Collection Gifts | 双编号；Small Scale 因超限删 |
| 4570 | In Stock Transformation ROBOTToys RT-07 RT07 OP Commander Caesar 2.0 Small Scale Action Figures Collection Gifts | 两品牌取 ROBOTToys |
| 4559 | In Stock Transformation Lucky Cat Toys JGM-SKP02 JGMSKP02 Mini Asura Volcanicus Core Action Figures Collection Gifts | Toys Laser Cat → Lucky Cat Toys |
| 4561 | In Stock Transformation Studio Series SS86 Starscream Upgrade Kit Action Figures Collection Gifts | 配件包 |
| 4565 | In Stock Transformation FansToys MP FT-33C FT33C Pythagoras Action Figures Collection Gifts | MP Scale→MP |
| 4564 | In Stock Transformation Age of the Primes Sky Byte Voyager Action Figures Collection Gifts | Hasbro 删；天尊世代 |
| 4557 | In Stock Transformation DrWu DW-ES03 DWES03 DW-ES08 DWES08 Devastator Action Figures Collection Gifts | 六件套 |
| 4563 | In Stock Transformation DNA DK-26 DK26 MPM-05 MPM05 MPM-10 MPM10 Roadblock Upgrade Kit Action Figures Collection Gifts | 配件包 + 三个适配编号 |
| 4562 | In Stock Transformation CT CT-01 CT01 OP Commander Action Figures Collection Gifts | |
| 4649 | In Stock Transformation NewAge NA-H80 NAH80 Perceptor Animation Color Original Action Figures Collection Gifts | 感知器→官方名 Perceptor（编号顺序按新规已调整为横线在前） |
| 4049 | In Stock Transformation AS-08S AS08S Studio Series SS86 OP Commander KO Action Figures Collection Gifts | 编号顺序按新规 |
| 4755 | In Stock Transformation DNA Generation Select DK-99 DK99 Core Upgrade Kit Action Figures Collection Gifts | 配件包 |
| 4754 | In Stock Transformation Studio Series Ironhide Action Figures Collection Gifts | Iron Sheet → Ironhide |
| 4647 | In Stock Transformation TF DK-52 DK52 SS98 SS103 Cheetor Rhinox OP Commander Upgrade Kit Action Figures Collection Gifts | 120 字顶格；**新规下应改为保住横线版、先降品牌/删修饰** |
| 4050 | In Stock Transformation Diaclone TM-14 TM14 Galida Turbo Booster Action Figures Collection Gifts | Daiya Clone → Diaclone（用户确认） |
| 4573 | In Stock Transformation TMT TMT-02 TMT02 Beetle Wasp Action Figures Collection Gifts | |
| 4355 | In Stock Transformation NewAge Generation 2 NA-H2G NAH2G Jazz Action Figures Collection Gifts | 修饰因超限删 |

---

## 7. 坑

1. **前缀一刀切**：62店 商品写成 `Hot Sale`（或 shana1 写成 `In Stock`）是最常见的错。改前先判店铺（§1）。
2. **标题品牌词不许从搜索结果补**：正文出现厂牌 ≠ 原文有品牌；KO 款尤其别把 Hasbro 补进标题。`brand` 字段则只按 §0 的两类 code 规则核对，二者不是同一口径。
3. **`title` 不是标题真值**：改 `title` 没用（那是原标题），上架读 `titleEn`。
4. **只改 `titleEn` 不改 `titleTranslationZh`**：中文回译会与新标题对不上，视为未完成（§0）。
5. **编号被「美化」掉横线**：`SS86-05` 存成 `SS8605` 会和别处对不上；`identityJson.modelCode` 与标题里都以带横线为主。
6. **超字数先砍编号**：错。先砍修饰/系列/品牌（降 `TF`），编号双格式最后才动，且保留横线版。
7. **`identityJson` 传 dict 必 400**：必须是 `json.dumps(...)` 字符串，报错体是空的，别以为是网络问题。空编号时回读只有 `{"logoCode":""}`、**没有 modelCode 键属正常**，别当成"没写进去"反复重试。
8. **`titleTranslationZh` 写不进去不是 bug**：该字段由 `POST /api/admin/products/{id}/translate-title` 生成（§0 ②），`save()` 传它服务端直接忽略。
9. **`descriptionJson` 的 SHOP_TITLE 会自动重算**：不要手工 remap，保存一次就同步；回读时 `t in descriptionJson` 为 True 即验证通过。
10. **同型号姊妹 listing 是角色名的合法来源**（4558 的 `Beetle Wasp` 来自 4573，同 `TMT-02`），但要在报告里注明来源，方便用户否掉。
11. **裸 PUT 事故**：`s.call(..., method='PUT')` 会重传全图 + 自动封面 + 状态跳「待生图」。只用 `s.save(..., extra=...)`。
12. **`weight` 被重置成 0.3 / `shippingFee` 跳到 8.8**：根因是 body 缺 `weight` 时服务端填默认值（全量覆盖），不是站点"重算"。`Site.save()` 已回传当前重量；旧脚本或历史写入留下的漂移用 `scripts/restore_weight.py` 复原（`shippingFee` 是派生值，永不手写）。
13. PowerShell 跑脚本用 `.venv\Scripts\python.exe xxx.py 2>&1`；脚本内先 `sys.stdout.reconfigure(encoding='utf-8')` 防乱码。
14. **`save()` 不带 `identityJson` 会把 `modelCode` 清掉**（2026-11-09 九件实测复现）：body 缺该字段时服务端写成 `{"logoCode":""}`，`modelCode` 键直接丢。每次 `save()` 显式带 `extra={'identityJson': json.dumps({...})}`、写后回读；`Site.save()` 现已自动并入当前 `identityJson`，但**改编号时仍必须显式传**。
15. **`translate-title` 角色名会译错**：该接口是 LLM 直译且不稳定（`Wheeljack` 多次译成「救护车/变速箱」）。字段是内部回译不展示给客 → 可接受；重试到带上英文括注即可，不要因译名反复重写 `titleEn`。
