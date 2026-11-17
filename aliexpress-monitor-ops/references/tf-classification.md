# 变形玩具判定标准（看图复核口径）

> 用途：`scripts/triage.py` 只做**关键词初筛**，真正的取舍必须按主图逐张看。本文是「看什么算通过、什么必须排除、哪些容易误判」的唯一口径。
> 出处：2026-11-12 run 45 实测（33 新品 → 22 通过 / 1 剔除 / 10 排除全对）+ run 43 历史样例。
> **2026-11-16 用户口径变更（m00171）**：判定标准从「是不是变形金刚 IP」改为「**是不是变形玩具**」——只要能变形/可合体就算，不限 TF 授权 IP。本文件已按新口径改写。

## 1. 判定原则

1. **看主体，不看标题**。标题含 `Hasbro` / `Transformation` / 角色名，但图里是别的品类 → 排除。反过来标题只写代号（`NA H77`、`MMC OX PS-24A`、`BT-08-05`、`DW-E64M`、`BWM-10`、`CS-02`、`RT-07`），图是变形玩具 → 通过。
2. **核心标准 = 是不是「变形玩具」**（用户 2026-11-16 定调：`有变形玩具就判定为变形金刚系列，属于变形玩具即可`）。
   - **算**：能变形、能合体、能变形成载具/武器/基地的机器人玩具；官方线、第三方厂牌、KO 复刻、TF 升级配件包、原创变形机甲，以及**非 TF 授权 IP 的变形合体机器人**（盖塔 Getter、魔神 Z Mazinger、超机列传 Super Robot Legend SRL、Voltron / 百兽王 / Megazord 合体系等）。
   - **不算**：明确**不可变形**的品类——人形兵人（G.I. Joe、Warhammer、NECA、四骑士）、机娘/机娘改造件、雕像/景品、不可变形合金成品（Muscle Bear 之类）、头盔/变身器/道具、非玩具（T恤/海报/钥匙扣）。
   - 判定顺序：先问「这个东西本身能不能变形或合体」，能 → 通过；不能 → 再看是不是 TF 角色授权周边（如 Hasbro RED、Threezero MDLX/DLX，见 4.3）→ 是则通过；都不是 → 排除。
3. **拿不准就保留 `pending_review`**，在汇报里单列「仍拿不准」，不要硬标。
4. **准确性优先于速度**：宁可少标一条，不要错标一条。错标会让远程玩具库进脏数据，事后清理成本高。
5. **存量不翻旧账**（用户 2026-11-16 决定）：新口径只作用于之后的新品；历史 `pending_review` 不做批量回扫，除非用户另行要求。

## 2. 通过（算变形玩具）

| 类别 | 代表 |
|---|---|
| 官方主线 | Hasbro / Takara Tomy：G1、Masterpiece(MP/MPM)、Studio Series(SS/SS86)、War for Cybertron(Siege/Earthrise/Kingdom)、Legacy、Titans Return、Combiner Wars、Power of the Primes、Age of the Primes、Beast Wars、TF One、电影线(DOTM/ROTF) |
| 官方周边线 | Hasbro RED（6 寸可动，仍是 TF 角色）、Threezero DLX / MDLX / Robo-Dou、Flame Toys 铁机巧、Yolopark、Blitzway、T-SPARK 钢铁机神（Star Saber 等）、Overgear |
| 第三方厂牌 | Newage(NA)、MMC / OX、Magic Square(MS)、FansToys(FT)、DX9、IronFactory 铁工厂、MFT 型模坊、Zeta、APC Toys、Dr.Wu、DNA 配件包(DK-xx)、DMK、Toyworld、MTCD、TFC |
| 配件/改件 | 升级配件包（DNA DK-69B 之类）、滑翔翼套、替换头/手型，只要是给 TF 用的 |
| KO / 复刻 | G1 复刻 KO（OP/Menasor/横炮/钢锁/震荡波/机器昆虫）、JCS-001D 太阳风 SS86 KO |
| 原创变形机甲 | 能变形的原创机甲（如 YIWANTIANKAI YW2611 钢铁战魂 MAUS）——**存疑项**，按同品牌历史口径收，汇报里注明 |
| **非 TF IP 的变形/合体机器人**（2026-11-16 新增） | 盖塔 Getter（含 超机列传 SRL-02 蓋塔燼鬼、AC KO 山口式 Getter 1）、魔神 Z / Mazinger ZERO（SRL-03）、Voltron / 百乐王 Golion / 战神金刚、Power Rangers 合体 Megazord（MC-03C Daizyujin、MC-05 Dragonzord、MZ-0101 Dino Megazord）、超时空要塞/变形战机类、勇者系、合体金刚类原创 IP —— 判定依据是「**能变形/能合体**」，不看 IP 归属 |

## 3. 排除（不算变形玩具）

> 新口径下排除项只剩「**明确不可变形**」与「非玩具」两大类。旧口径里按 IP 排除的 Voltron / Power Rangers / Zord / 高达 / 龙珠等，**只要本身能变形合体就不再排除**（见 §2 最后一行）。

- **明确不可变形的可动人偶**：G.I. Joe 蛇兵、Warhammer、NECA、S.H.Figuarts（非 TF 且不可变形）、Figma、黏土人 Nendoroid、四骑士 Four Horsemen / Mythic Legions、Marvel / 漫威、龙珠悟空/贝吉塔等可动人偶、星战 Black Series / Vintage Collection
- **不可变形合金成品/雕像**：肌肉熊 Muscle Bear（MC-07 WZT 等，`Non-transforming die-cast action figure`）、龙珠/动漫雕像、景品
- **机娘 / 机娘改造件**：Megami Device 类、玄繭工作室 Xcocann 賽博鬥士 CFC 系列（如 CFC05 黑蓮 Black Lotus 1/12 可動人偶）、核金重构玄冥缄魄 1/12 机娘成品、Acid Rain 系列
- **纯拼装不可变形 / 固定造型**：Gunpla 高达拼装（MG/HG/RG/PG、30MM）、Q 版固定造型拼装人偶（如无变形机构的 Brickman/Blockpals 类）
- **道具/周边/非玩具**：头盔、变身器、权杖等道具复刻；T恤/贴纸/海报/钥匙扣/鼠标垫
- **其它 IP 人偶**：Ghostbusters / Ecto-1、Funko、Hot Wheels、Lego（非变形合体款）

## 4. 实战误判案例（务必记住）

### 4.1 该排除却被初筛判 HIGH —— 必须看图剔除
- **id 6742｜TF BOYS Figures Store**｜标题 `New Original Hasbro G.I. Joe Classified Series 153 Frag-Viper Action Figure Model Toys Gift`｜https://www.aliexpress.com/item/3256813432781980.html
  → 图是 **G.I. Joe 蛇兵人形兵人**，仅因标题含 `Hasbro` 被关键词判 HIGH。处置：保持 `pending_review`，汇报里单列。

### 4.2 该通过却被初筛判 SKIP —— 从排除表捞回
- `[DP ROBOT Store] [IN STOCK NOW] APOLLO TOYS AT-01 Silverstreak AT-02 Prowl AT-03 Smokescreen`（run 43）
  → 标题只有 `AT-01/02/03` 代号 + 角色名，无 `transformers`/`hasbro` 等强词。处置：捞回标 `to_process`。
- 常见代号形制：`NA H77`（Newage）、`MMC OX PS-24A`、`BT-08-05`、`DW-E64M`、`BWM-10`、`CS-02`、`RT-07`。

### 4.3 容易看错的
- **Hasbro RED 系列**：6 寸可动人偶，但确实是变形金刚角色 → **通过**（run 45 的 6741 BW 猩猩队长）。
- **Threezero MDLX / DLX**：不可变形但属官方授权 TF 线 → **通过**。
- **DNA / Dr.Wu 配件包**：小零件图，看着不像机器人 → **通过**（是 TF 升级件）。
- **T-SPARK 钢铁机神 Star Saber**：日系官方线 → **通过**。
- **超机列传 SRL-02 蓋塔燼鬼（id 6889）**：标题写 `Steel Romance Manufacturing SRL02 Office Black Getter Ember Demon`，图是黑色盖塔机器人。2026-11-16 核实官方/代理商均标「**變形合體**」→ 新口径下 **通过**（旧口径曾误判为排除）。
- **非 TF 变形玩具的识别方法**：查官方/代理商页面是否写「变形」「合体」「可變形合體」「Combining」「Transformable」；写了就算，别因为 IP 不是 TF 就排除。

### 4.4 run 49（2026-11-16）确认的排除项
- **6886 MC Muscle Bear MC-07 WZT Megatron**：`Non-transforming die-cast action figure`（Show.Z Store 原文），不可变形合金成品 → 排除。
- **6888 CFC05 黑蓮 Black Lotus 1/12**（玄繭工作室 Xcocann 賽博鬥士系列）：可動人偶，不可变形 → 排除。
- **6890 NS Studio GT 绿袍悟空** / **6894 NS Studio NS012-014 WIK Toys**：龙珠雕像/可动木偶，不可变形 → 排除。
- **6903 核金重构 玄冥缄魄 玄缄 1/12**：机娘成品，不可变形 → 排除。
- **6883 BRICKMAN/BLOCKPALS BM-009「骑士柱」**：Q 版拼装可动、擎天柱造型但无变形机构、无孩之宝授权标识；**用户 2026-11-16 明确决定保留 `to_process`**（造型是 TF 角色即收）。同类 Brickman 系列按此口径处理。

## 5. 复核操作步骤

```powershell
$py  = "D:\GitHub\AliExpressMonitor\.venv\Scripts\python.exe"
$alm = "<本skill目录>\scripts\alm.py"
$tri = "<本skill目录>\scripts\triage.py"

# 1) 初筛 + 出对照表（runId 用 scan-start/scan-watch 拿到的那个）
& $py -X utf8 $tri classify --run 45 --out .\triage-45

# 2) 逐张看图：sheet-*.jpg（主对照表）+ sheet-skip-*.jpg（排除表抽查）
#    编号 → 商品：thumbs\index.txt（编号 TAB id TAB 等级 TAB 店铺 TAB 标题）

# 3) 看图定夺后一次性标记（只标看过图的）
& $py -X utf8 $alm set-state --ids 6722,6723,6724 --to to_process

# 4) 误判回退
& $py -X utf8 $alm set-state --ids 6742 --to pending_review

# 5) 复核：应标的是否都到位
& $py -X utf8 $alm products --state to_process --run 45
```

验收点：
- 主对照表每张都看过（不能只看缩略图标题）；
- 排除表至少抽查一遍（重点找只写代号的，以及 Voltron/百兽王/Megazord/Getter/魔神 Z 这类**非 TF 授权但能变形合体**的）；
- 标记后 `products --run <id>` 复核数量与看图结论一致；
- 汇报里必须出现：run id/耗时、成功失败店数、新品数、通过并标记数、剔除的误判（店铺+标题+链接）、捞回的漏网、仍拿不准的条目。
