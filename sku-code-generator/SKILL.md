---
name: sku-code-generator
description: |
  Generates unique, convention-compliant SKU codes for the user's cross-border toy stores
  (Morph Toys Store / Childhood Memories / PureSun). The code format is
  STORE-CATEGORY-SERIES-SERIAL[-VARIANT] (e.g. MTS-TF-SS86-0001-RD). Supports shorthand
  auto-completion (type "s86" → SS86, "r" → RD), a local ledger that guarantees serial
  numbers never collide, single-item CLI mode, interactive mode, and batch generation from
  CSV/TSV/XLSX product tables. Series and variant dictionaries live in a JSON file so new
  lines can be added without touching code.
  ALSO ships a resident Windows global-hotkey mode, which is the default daily workflow and
  needs NO setup at all: launch it and press Ctrl+B — a timestamped serial
  (20261006142305-00001, 20261006142341-00002, ...) is pasted straight at the cursor,
  incrementing on every press. The number is unique down to the second, yet the sequence
  keeps counting up within the same day (it does NOT reset every second) and rolls over to 1
  on the next day; the counter survives restarts. The
  prefix / separator / zero-padding are configurable
  (`--prefix "{date}{time}"|"{date}"|"MTS"|"MTS-{ts}"|""`,
  `--sep "-"`, `--width 5`, `--from N`). Optionally switch to full SKU-code mode with
  `--set "mts tf ss86 r"` to emit store-category-series-colour codes (MTS-TF-SS86-0001-RD);
  Ctrl+Shift+B switches mode from the clipboard.
  It also packages into a single-file Windows exe (scripts/build_exe.py) that lives in the
  system tray: launch it and press Ctrl+B anywhere. Tray icon double-click = emit + paste;
  right-click menu = emit/copy, show status, open data folder, view log, exit.
  Triggered when the user asks for SKU 编码 / SKU 生成 / 生成货号 / 编码规则 / 批量生成 SKU /
  "给这批商品编个号" / "SKU 代号" / 热键出号 / Ctrl+B 自动粘贴 / "按一下就来一个编号" /
  "每次按一下自增" / 打包成 exe / 托盘 / 右下角 / "做成一个双击就能用的程序" /
  wants to add a new series or colour to the SKU dictionary /
  or asks what a generated SKU means.
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

## 热键模式（Ctrl+B 自动粘贴）—— 日常就是用这个

**不开终端、不打命令、不需要任何设置**：双击 `dist/编号出号器.exe`（打包好的单文件，推荐）
或 `scripts/start_hotkey.bat` 让它常驻，之后按一下 Ctrl+B，下一个编号直接粘在光标处。

### 默认：日期时间流水号（主人确认的口径）

```
20261006142305-00001 → 20261006142341-00002 → 20261006150112-00003 → …
```

- 默认前缀 = **当天日期 + 时分秒**（`{date}{time}`，即 14 位 `YYYYMMDDHHMMSS`），连接词 `-`，序号 5 位补零
- **隔天自动换日期、序号重新从 1 开始**：第二天第一个号是 `20261007090133-00001`
- ⚠️ **计数器按「天」分组，不是按秒** —— 编号外观精确到秒，但同一天内无论隔了几秒，
  序号都接着往上加（`…142305-00030 → …142341-00031`），不会每秒归 1。
  实现见 `group_key()`：先把模板里的秒级占位符（`{ts}/{time}/{hh}/{mi}/{ss}`）剔除再当计数器 key。
  **改代码时别退回按完整前缀分组**，否则序号会永远停在 00001；`selftest.py` 有专项回归。
- 序号记在 `data/hotkey_state.json`（按分组 key 存放），关掉重开接着往下走，不会重号
- 不写台账，只管出号 —— 最省事

### 改编号长相（设一次就一直记住）

| 命令 | 出号长相 |
|---|---|
| `--prefix "{date}{time}"` | `20261006142305-00001`（默认） |
| `--prefix "{date}"` | `20261006-00001`（只要日期，旧行为） |
| `--prefix "{date}-{time}"` | `20261006-142305-00001`（带分隔更好读） |
| `--prefix "MTS"` | `MTS-00001` |
| `--prefix "MTS-{ts}"` | `MTS-20261006142305-00001` |
| `--prefix ""` | `00001`（不要前缀） |
| `--sep "_"` | 换连接词：`20261006142305_00001` |
| `--width 3` | 换补零位数：`20261006142305-001`（`--width 0` = 不补零） |
| `--from 1200` | 把下一个号设为 `20261006142305-01200`（只影响当前分组） |

前缀模板里可用的占位符：

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{date}` | 年月日 | `20261006` |
| `{time}` | 时分秒 | `142305` |
| `{ts}` | 年月日时分秒（= `{date}{time}`） | `20261006142305` |
| `{yy}` `{mm}` `{dd}` | 年 / 月 / 日 各两位 | `26` `10` `06` |
| `{hh}` `{mi}` `{ss}` | 时 / 分 / 秒 各两位（注意分是 `{mi}` 不是 `{mm}`） | `14` `23` `05` |

### 可选：SKU 编码模式（需要带前缀时才用）

```
Ctrl+B          → 按已有规格出下一个编码 → 写剪贴板 → 自动 Ctrl+V 粘贴
Ctrl+Shift+B    → 把剪贴板里的速记符设为新规格（复制「jcs r」按一下，就切到 JCS）
```

```bash
S_HK="C:/Users/shana/.workbuddy/skills/sku-code-generator/scripts/sku_hotkey.py"

"$PY" "$S_HK"                          # 启动（默认日期时间流水号，什么都不用设）
"$PY" "$S_HK" --status                 # 当前前缀 + 下一个编号（只算不写）
"$PY" "$S_HK" --prefix "MTS" --width 4 # 改前缀与位数（立即生效）
"$PY" "$S_HK" --plain --from 1200      # 切流水号模式，并把下一个号设为 1200
"$PY" "$S_HK" --set "mts tf ss86 r"    # 切到 SKU 编码模式
"$PY" "$S_HK" --stop                   # 停止热键程序
"$PY" "$S_HK" --probe                  # 环境自检（热键/剪贴板/按键注入/解析）
```

> ⚠️ `--set` / `--plain` / `--prefix` / `--sep` / `--width` / `--from` 改完**立即生效，不用重启常驻程序**。
> 这是个修过的真坑：守护进程原先只在启动时读一次状态文件，外面改了不生效，
> 而且按一次 Ctrl+B 还会把内存里的旧值写回文件、把刚做的设置覆盖掉。
> `selftest.py` 第 13 节有专项回归，别改回「只读一次」。

SKU 模式的出号规则：

| 规格 | 连按 Ctrl+B 的结果 |
|---|---|
| `ss86`（无变体） | 0001 → 0002 → 0003（每次一个新流水号） |
| `ss86 r`（单变体） | 0001-RD → 0002-RD → 0003-RD |
| `ss86 r,b`（多变体） | 0001-RD → 0001-BL → 0002-RD → 0002-BL（同款先出齐颜色） |

- SKU 模式每次出号**都写进同一份台账**，和命令行模式共用流水号，绝不会撞号；流水号模式不写台账
- 日志窗口留着能看见每次出了什么号；不想要日志就加 `--quiet`
- 只复制不粘贴（比如手动 Ctrl+V）加 `--copy-only`
- 开机自启：`Win+R` → `shell:startup` → 把 `start_hotkey.bat` 的**快捷方式**放进去

### 打包成 exe（双击即用，缩在右下角托盘）

不想开命令行时用这个。产物是**单文件 exe**，双击就缩进托盘，不占屏幕。

```bash
PYX="C:/Users/shana/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
"$PYX" scripts/make_icon.py    # 生成 assets/sku_hotkey.ico（已入库，一般不用重跑）
"$PYX" scripts/build_exe.py    # 打包 → dist/编号出号器.exe（约 7 MB）
```

产物目录 `dist/`（已 gitignore，随时可重建）：

| 文件 | 说明 |
|---|---|
| `编号出号器.exe` | 单文件；图标、字典兜底副本、托盘图标全部内置 |
| `使用说明.txt` | 给最终用户看的简版说明 |
| `data/` | 运行时数据（序号、pid、日志），**换机器时整个文件夹拷走** |

托盘操作：**双击图标 = 出号并粘贴**；右键菜单 = 出号复制 / 查看状态 / 打开数据目录 / 查看日志 / 退出。

命令行参数全部照旧可用（`--prefix`、`--set`、`--status`、`--stop`、`--probe`）。
带这类参数运行时程序会自动附一个控制台显示结果，跑完停住等回车；脚本调用时加 `--no-pause`。
`data/` 落在 exe 同目录（不可写时自动回退到用户目录），只读资源走 PyInstaller 的 `_MEIPASS`。

**不想在本地装 PyInstaller？让 GitHub 帮你编译。** 工作流 `.github/workflows/build-sku-exe.yml`：

| 触发方式 | 行为 |
|---|---|
| 推 `sku-code-generator/**` 的改动到 `main` | 自动跑「自测 → 打包 → 启动校验」，产物存成 artifact（保留 30 天） |
| 推 `sku-exe-v*` 标签 | 额外自动发 Release，把 exe 挂成附件（换机器直接下） |
| Actions 页面点 *Run workflow* | 手动跑一次 |

> tag 推送不受 `paths` 过滤影响（GitHub 不评估 tag 推送的路径过滤器），所以打标签一定会完整走一遍。
> 校验步骤不只检查文件存在，而是真跑一次 `--status` 并确认它写了 `data/hotkey.log` ——
> 否则「打出来的 exe 一启动就崩」这种问题会漏到用户手里。
> ⚠️ Release 附件用 **ASCII 名**（`<tag>.exe`）：`softprops/action-gh-release` 解析不了中文文件名，
> 会把附件退化成 `default.exe` / `default.txt`（已踩）。所以发布前先复制一份 ASCII 名到 `release/` 再上传。

### 怎么验证热键真的能用（改完代码后）

改完 `sku_hotkey.py` 一定要跑 `--probe`（校验 Ctrl+B 可注册、剪贴板中文往返、`INPUT` 结构体布局 40 字节、
规格解析与非规格拒绝、日期时间流水号自增 / 跨秒连续 / 跨天归 1、前缀占位符、模式判定）。自检结果会同时写进 `data/probe.log`
—— 打包成 windowed exe 后控制台是临时附加上去的，窗口一关就没了，必须落盘才查得到。

想验证整条链路（真热键 → 出号 → 剪贴板），做法是**注入真实的 Ctrl+B**，而不是只调函数 ——
注入的按键同样会触发 `RegisterHotKey`（已实测通过，实测数据：注入后 **0.25s** 编号就已进剪贴板）。
三条纪律：

1. 测的时候给常驻进程加 `--copy-only`，否则测试编号会被粘到当前前台窗口里。
2. **验证脚本自己不要写剪贴板。** 一个进程写的剪贴板数据（`GlobalAlloc` 私有 HGLOBAL）
   在多个进程反复交替读写时，内容可能"回退"成旧值，看起来像产品 bug，实际是验证脚本的副作用。
   正确姿势：`scripts/press_only.py` 只注入按键、不碰剪贴板，再用**独立工具**读
   （PowerShell `Get-Clipboard`）。已实测：出号后连续 5 次读取（跨 2.5s）内容稳定不变。
3. 端到端走一遍完整清单：启动 → 出号递增 → `--stop` 优雅退出（pid 清理、热键释放）→
   重启续号（不重号）→ `--set` 切 SKU 模式（对运行中进程即时生效）→ `--status`。


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
- 改完**跑一遍自测**：`"$PY" scripts/selftest.py`（40 项检查，全在临时目录，不碰正式台账）

## 文件结构

```
sku-code-generator/
├── SKILL.md
├── agents/openai.yaml
├── config/sku_config.json      # 字典（进 git）
├── assets/sku_hotkey.ico       # 程序/托盘图标（进 git，打包输入）
├── scripts/sku_gen.py          # 命令行主脚本
├── scripts/sku_hotkey.py       # 全局热键出号器（Ctrl+B，日常就是用这个）
├── scripts/tray.py             # 系统托盘（纯 ctypes，无第三方依赖）
├── scripts/make_icon.py        # 生成多尺寸 .ico
├── scripts/build_exe.py        # PyInstaller 打包 → dist/
├── scripts/press_only.py       # 端到端验证：只注入 Ctrl+B，不碰剪贴板
├── scripts/start_hotkey.bat    # 热键启动器（不打包时双击即用）
├── scripts/selftest.py         # 冒烟自测（40 项）
├── dist/                       # 打包产物（已 gitignore，可重建）
├── build/                      # PyInstaller 中间件（已 gitignore）
└── data/                       # 本地数据（已 gitignore）
    ├── sku_ledger.json         #   台账（仅 SKU 编码模式使用）
    ├── hotkey_state.json       #   当前模式 + 前缀模板 + 按前缀分组的计数器
    ├── hotkey.pid              #   运行中的热键进程
    ├── hotkey.log              #   运行日志（托盘模式下的唯一排查线索）
    └── probe.log               #   最近一次 --probe 自检结果
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
| 常驻程序读一次状态就不管了 | 外面 `--set` 改了规格，按 Ctrl+B 还是老号，还会把旧值写回文件覆盖设置 | 常驻进程必须**每次按键前重读** state 与台账（`HotkeyDaemon.refresh()` + `Ledger.reload()`）。`selftest.py` 第 13 节有回归 |
| pid 文件残留 | 进程被强杀后 `hotkey.pid` 还在，`--status` 会误报「运行中」 | 用 `OpenProcess` 探活（`daemon_running()`），并顺手清理残留 pid |
| `OpenProcess` 未声明签名 | 64 位下句柄被默认 `restype` 截成 32 位，`CloseHandle` 失效 | 已显式声明 `argtypes`/`restype`，新加 Win32 调用时照做 |
| 自己写脚本注入按键测试 | `ctypes` 的 `INPUT` union 里只放 `KEYBDINPUT` 时 `sizeof(INPUT)` = 32，`SendInput` **静默返回 0** | union 必须含最大成员 `MOUSEINPUT`（32 字节），64 位下 `sizeof(INPUT)` = 40；`--probe` 专门校验这一项 |
| 编号格式换代后旧计数残留 | 老 state 的 `next`/`count` 被新结构继承，`--status` 报出「已出 10 个」却一个都没出过 | `load_state()` 里 `migrate_state()`：发现旧 `next` 且无 `seq` 就作废旧计数（幂等） |
| 托盘 exe 启动即秒退（无任何提示） | `--windowed` 打包后没有 stderr，异常等于静默消失 | `wintypes.MSG` 的字段名是 **`hWnd`**，写成 `hwnd` 会抛 `AttributeError` 把消息循环打死 —— 引入托盘时踩过。现用 `install_excepthook()` 把未捕获异常写进 `data/hotkey.log` |
| 打包只报"退出码 1" | 看不出失败原因 | 九成是 `dist/*.exe` 正被运行中的实例占用（中文进程名用 `tasklist` 过滤不可靠）。`build_exe.py` 先探测占用并提示先 `--stop`，失败时打印 PyInstaller 输出的真实尾部 |
| 托盘留"幽灵图标" | 程序退了图标还在，鼠标划过才消失 | 退出路径必须 `Shell_NotifyIconW(NIM_DELETE)`（`TrayIcon.destroy()`）。`--stop` 走窗口 `WM_CLOSE` 优雅退出，不强杀进程 |
| windowed exe 的 `--probe`/`--status` 结果看不到 | 控制台是临时附加的，窗口一关输出就没了 | 自检结果同时写 `data/probe.log`，`--status` 顺手记一条进 `hotkey.log` |
| 验证脚本自己写剪贴板 | 出号正常但读回旧值，像是剪贴板内容"回退" | 跨进程交替读写 `GlobalAlloc` 私有 HGLOBAL 会互相遮挡。验证时**只注入按键不碰剪贴板**，用独立工具（PowerShell `Get-Clipboard`）读 |
| `--windowed` 的 exe 在 PowerShell 里调用 | `& .\编号出号器.exe --status` 之后 `$LASTEXITCODE` 是**空的**，脚本误判成「启动失败，退出码 」 | GUI 子系统程序 PowerShell 不会同步等待。用 `Start-Process -FilePath <exe> -ArgumentList ... -Wait -PassThru` 取 `$p.ExitCode`；或者干脆看它写的 `data/hotkey.log`（CI 里就同时做了这两件事） |
| GitHub Release 附件名变成 `default.exe` | 中文名文件上传后名字丢了 | `softprops/action-gh-release` 处理不了非 ASCII 文件名。先 `Copy-Item` 成 `<tag>.exe` 这类 ASCII 名再上传（`release/` 目录已 gitignore） |
