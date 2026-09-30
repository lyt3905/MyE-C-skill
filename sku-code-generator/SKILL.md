---
name: SKU编码生成
description: |
  Generates unique, convention-compliant SKU codes for the user's cross-border toy stores
  (Morph Toys Store / Childhood Memories / PureSun). The code format is
  STORE-CATEGORY-SERIES-SERIAL[-VARIANT] (e.g. MTS-TF-SS86-0001-RD). Supports shorthand
  auto-completion (type "s86" → SS86, "r" → RD), a local ledger that guarantees serial
  numbers never collide, single-item CLI mode, interactive mode, and batch generation from
  CSV/TSV/XLSX product tables. Series and variant dictionaries live in a JSON file so new
  lines can be added without touching code.
  ALSO ships a resident Windows global-hotkey mode: press Ctrl+B and the next SKU code is
  pasted straight at the cursor (no terminal, no command line), reusing the last spec and
  auto-incrementing the serial every press; Ctrl+Shift+B switches spec from the clipboard.
  Triggered when the user asks for SKU 编码 / SKU 生成 / 生成货号 / 编码规则 / 批量生成 SKU /
  "给这批商品编个号" / "SKU 代号" / 热键出号 / Ctrl+B 自动粘贴 / "按一下就来一个编号" /
  wants to add a new series or colour to the SKU dictionary / asks what a generated SKU means.
agent_created: true
---

# SKU 编码生成器（sku-code-generator）

## Purpose

把「给商品编号」这件事从手敲变成一条命令。核心是**一致性**和**不撞号**：
只要经过这个脚本，同一款商品的编码规则永远一致，流水号由台账统一分配，跨店铺/跨系列互不干扰。

> **主人关心的是「别再让我手写编号、也别重号」**，不是编码美学。因此：
> 优先保证**编号绝不重复**（台账 + 计数器只增不减），其次才是输入够快（速记符）。

## 编码格式

```
店铺-品类-系列-流水号[-变体]
MTS - TF - SS86 - 0001 - RD
```

| 段 | 含义 | 字典 | 示例 |
|---|---|---|---|
| 店铺 | 哪个店 | `store` | MTS / CMT / PST |
| 品类 | 什么类型的货 | `cat` | TF 变形玩具 / AF 可动人偶 / AC 配件 / MD 合金 / RC 遥控 |
| 系列 | 产品线 | `series` | SS86 / JCS / TAKARA / PX / MSB / DW / NB / TFX / SXX / TX / DX9 / CW / ST / BLK |
| 流水号 | 按 `serial_scope`（默认 店铺+系列）独立递增，4 位补零 | 台账自动分配 | 0001、0002 |
| 变体 | 可选。颜色 / 版本 / 数字色号 | `variant` | RD 红 / BL 蓝 / BK 黑 / 01、02 |

无变体的商品编码就停在流水号（如 `MTS-TF-JCS-0001`）。同一款的多色 SKU **共用同一个流水号**，
只在末尾区分变体。

## 速记符（省输入的核心）

所有字段都能用速记符，**大小写不敏感，支持前缀补全，歧义会拦下让你补全，绝不瞎猜**：

| 输入 | 结果 |
|---|---|
| `mts` / `m` / `62店` / `主店` | MTS（Morph Toys Store） |
| `s86` / `86` / `ss` | SS86（Studio Series 86） |
| `r` / `b` / `k` / `sl` | RD 红 / BL 蓝 / BK 黑 / SL 银 |
| `01`、`02` | 数字色号原样透传 |

⚠️ 输入 `s` 会报歧义（SS86 / SXX / ST 三个候选）——这是故意的，避免编错货。
输入 `?` 可随时打印该字段的完整字典。

热键的模式匹配用的是**跨字典判定**：先找「精确匹配」的字段（`w` 精确命中变体 WH，而不是前缀命中系列 WFC），
找不到再退回前缀匹配；且要求每个 token 都能识别，否则整条作废 —— 商品标题、闲聊文本不会被误当成规格。

## 用法

脚本：`scripts/sku_gen.py`。**跑之前先确认用哪个解释器**：

```bash
# 零依赖（纯标准库）—— 交互模式 / CSV / 台账查询都用它
PY="C:/Users/shana/.workbuddy/binaries/python/versions/3.13.12/python.exe"

# 需要读写 XLSX 时用装了 openpyxl 的隔离环境
PYX="C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

S="C:/Users/shana/.workbuddy/skills/sku-code-generator/scripts/sku_gen.py"
# 或仓库路径：C:/Users/shana/Documents/GitHub/MyE-C-skill/sku-code-generator/scripts/sku_gen.py
```

## 热键模式（Ctrl+B 自动粘贴）—— 日常最省事的用法

**不开终端、不打命令**：脚本常驻后台，按一下 Ctrl+B，下一个编号直接粘在光标处。
跑 `scripts/start_hotkey.bat` 启动（或 `"$PY" "$S_HK"`）。

```
Ctrl+B          → 按上次的规格出下一个流水号 → 写剪贴板 → 自动 Ctrl+V 粘贴
Ctrl+Shift+B    → 把剪贴板里的速记符设为新规格（比如复制「jcs r」后按一下，就切到 JCS）
```

首次使用先设一次规格（之后就不用再管了）：

```bash
S_HK="C:/Users/shana/.workbuddy/skills/sku-code-generator/scripts/sku_hotkey.py"

"$PY" "$S_HK" --set "mts tf ss86 r"    # 设定规格，之后每次 Ctrl+B 都是 SS86 的下一个号
"$PY" "$S_HK" --status                 # 看当前规格 + 下一个会出什么号（只算不写）
"$PY" "$S_HK" --stop                   # 停止热键程序
"$PY" "$S_HK" --probe                  # 环境自检（热键/剪贴板/按键注入/解析）
```

出号规则（与主人确认过的口径一致）：

| 规格 | 连按 Ctrl+B 的结果 |
|---|---|
| `ss86`（无变体） | 0001 → 0002 → 0003（每次一个新流水号） |
| `ss86 r`（单变体） | 0001-RD → 0002-RD → 0003-RD |
| `ss86 r,b`（多变体） | 0001-RD → 0001-BL → 0002-RD → 0002-BL（同款先出齐颜色） |
| 换商品 | 复制新速记符 → Ctrl+Shift+B 切换（或 `--set`） |

- 每次出号**都写进同一份台账**，和命令行模式共用流水号，绝不会撞号
- 日志窗口留着能看见每次出了什么号；不想要日志就加 `--quiet`
- 只复制不粘贴（比如手动 Ctrl+V）加 `--copy-only`
- 开机自启：`Win+R` → `shell:startup` → 把 `start_hotkey.bat` 的**快捷方式**放进去

### 怎么验证热键真的能用（改完代码后）

改完 `sku_hotkey.py` 一定要跑 `--probe`（校验 Ctrl+B 可注册、剪贴板中文往返、`INPUT` 结构体布局 40 字节、
规格解析与非规格拒绝）。想验证整条链路（真热键 → 出号 → 剪贴板），做法是：
**用 `SendInput` 注入真实的 Ctrl+B**，而不是只调函数 —— 注入的按键同样会触发 `RegisterHotKey`
（已实测通过）。测的时候一定加 `--copy-only`，否则测试编号会被粘到当前前台窗口里。

### 1. 交互模式（日常首选）

```bash
"$PY" "$S"
```

逐项提示，速记符自动补全，`?` 查字典，店铺/品类直接回车取默认值（MTS / TF），
预览后回车确认写入。输入的每个字段都会回显解析结果，例如 `✓ 系列「s86」→ SS86（Studio Series 86）`。

### 2. 单条生成

```bash
"$PY" "$S" -s mts -c tf -e s86 -v r,b -n "SS86 擎天柱"      # 一次出两个变体
"$PY" "$S" -s mts -c tf -e s86 -n "SS86 声波" --dry-run     # 只预览不写台账
"$PY" "$S" --reuse-base MTS-TF-SS86-0002 -v sl,gd            # 给已有商品追加变体
```

### 3. 批量（CSV / TSV / XLSX）

```bash
"$PYX" "$S" -i 商品表.xlsx -o SKU结果.xlsx
"$PY"  "$S" -i 商品表.csv  -o 结果.csv
```

输入表表头**中英文都可**，至少要有「系列」列：

| 名称 | 店铺 | 品类 | 系列 | 变体 |
|---|---|---|---|---|
| SS86 红蜘蛛 | mts | tf | ss86 | r |
| JCS 三变 | mts | tf | jcs | |
| MSB 合金 | 62店 | md | msb | 01,02 |

也可以用一列**「速记」**替代多列，按「店铺 品类 系列 变体」顺序写、空格分隔：
`mts tf ss86 r`、`ss86 r`（只写两项时店铺/品类走默认值）、`62店 md msb 01`。

输出列：`序号｜SKU｜基础编码｜名称｜店铺｜品类｜系列｜流水号｜变体｜状态｜备注`，
状态为 `新增` / `复用` / `已存在` / `失败`，Excel 里带底色。**解析失败的行不会中断整批**，
会带着原因写进输出表，修好字典或速记符再重跑。

### 4. 台账

```bash
"$PY" "$S" --list            # 最近 SKU
"$PY" "$S" --find SS86       # 搜索
"$PY" "$S" --stats           # 按店铺/系列统计 + 当前计数器
"$PY" "$S" --export 台账.csv  # 全量导出
```

## 防重机制（重要，别手动改）

- 台账 `data/sku_ledger.json`：`counters`（各作用域当前最大流水号）+ `items`（全部已生成 SKU）
- 每次写入前**自动备份** `data/sku_ledger.json.bak`，原子写入（先写临时文件再替换）
- 生成前比对台账：SKU 已存在 → 标 `已存在`，不重复入库、不推进计数器
- 同店铺+品类+系列+名称 → **复用**原流水号（`reuse_on_same_name`），重跑同一张表不会撞号
- 计数器 **只增不减**（`max(旧值, 新值)`）——这是个真实踩过的坑：复用旧流水号时如果直接赋值，
  计数器会被回写变小，下一次分配就撞号。`scripts/selftest.py` 里有专门回归项，别改回去。
- ⚠️ **不要手工编辑 `counters`**。真要改，先停手、备份、然后只调大不调小。

## 维护字典

改 `config/sku_config.json`，不用动代码。新增一个系列：

```json
{ "code": "MP", "name": "Masterpiece", "alias": ["mp", "mp系列", "大师级"] }
```

- `code` 是写进 SKU 的编码，`alias` 是速记符（可多个），`name` 是显示名
- `serial_scope` 改流水号按什么字段独立计数（默认 `["store","series"]`）
- `serial_width` 改流水号位数（默认 4）
- `defaults` 是缺列/回车时的兜底值
- 改完**跑一遍自测**：`"$PY" scripts/selftest.py`（19 项检查，全在临时目录，不碰正式台账）

## 文件结构

```
sku-code-generator/
├── SKILL.md
├── agents/openai.yaml
├── config/sku_config.json      # 字典（进 git）
├── scripts/sku_gen.py          # 命令行主脚本
├── scripts/sku_hotkey.py       # 全局热键出号器（Ctrl+B）
├── scripts/start_hotkey.bat    # 热键启动器（双击即用）
├── scripts/selftest.py         # 冒烟自测
└── data/                       # 本地数据（已 gitignore）
    ├── sku_ledger.json         #   台账
    ├── hotkey_state.json       #   热键当前规格
    └── hotkey.pid              #   运行中的热键进程
```

## 环境坑（已踩过，别重踩）

| 坑 | 现象 | 结论 |
|---|---|---|
| Windows 无 `readline` | 想用 Tab 补全实现「输入快捷键自动填充」会失败（`pyreadline3` 也没装） | 改用**速记符 + 前缀解析**，更稳且跨平台 |
| 管理版 Python 无 `openpyxl` | 读写 XLSX 报 ImportError | 已建隔离 venv：`C:/Users/shana/.workbuddy/binaries/python/envs/default`（openpyxl 3.1.5）。纯 CSV/交互用管理版即可 |
| 控制台中文乱码 | 中文提示变问号 | 脚本内 `setup_console()` 把控制台代码页切 UTF-8；管道输入测试时加 `PYTHONIOENCODING=utf-8` |
| 路径给原生 Windows Python | 传 `/tmp/...` 会失败 | 一律用 `C:/...` 形式 |
| Ctrl+B 与办公软件冲突 | WPS/Excel/Word 里 Ctrl+B 是「加粗」，在表格里按会先加粗 | 在**输入框/表单**里用（无冲突）；非要在表格里用就改 `sku_hotkey.py` 里的 `VK_B`/`MOD_CONTROL` 常量 |
| 剪贴板被别的程序占着 | `OpenClipboard` 失败 | 已做 20 次重试（每次 30ms），仍失败会报「写剪贴板失败」并保留 SKU 在日志里 |
| 热键被占用 | `RegisterHotKey` 返回 1409 | 启动时会明确报错并提示关掉占用的程序；`Ctrl+Shift+B` 被占用则只降级提示，不影响 `Ctrl+B` |
| 多变体规格的字段判定 | `w` 既能前缀匹配系列 WFC、又是变体 WH 的速记符 | `classify()` 采用**跨字典精确匹配优先**：`w` → WH（变体），而不是 WFC |
| `--stop` 强杀进程 | `finally` 不执行、热键不显式注销 | 无影响：进程退出时系统自动回收热键注册（已实测杀掉后能立刻重新注册） |
