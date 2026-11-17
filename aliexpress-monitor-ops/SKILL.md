---
name: aliexpress-monitor-ops
description: |
  AliExpressMonitor（本地选品监控控制台，http://127.0.0.1:18765）的日常运维与操作总纲。
  覆盖：启动/重启控制台服务（Python 3.12 venv + WMI 分离进程，避免随会话被杀）；
  发起/查看/重试店铺扫描（扩展通道、验证码自愈、LOGIN_REQUIRED 重试、每店 40 条上限）；
  新品分诊（关键词初筛出对照表 → 逐张看图复核「是不是变形玩具」→ 标记状态，判定口径见 references/tf-classification.md）；
  商品状态筛选与批量改状态（待判断/待处理/已忽略/已完成，带乐观锁）；
  把商品批量采集并上传到远程玩具库 toy-item-prod（Item Picker 扩展队列，含 service worker 休眠卡 opening-tab 的处置）；
  以及商品库数据核查（AliExpress 多套 item id 形制导致"假新品"重复入库的去重诊断与修复）。
  触发场景：用户说「启动/重启 AliExpressMonitor」「跑一次扫描」「筛选变形金刚/分类新品/看图挑变形金刚」
  「把今天的商品改成待处理」「调用批量采集/采集到远程系统」「今天新品怎么这么多/是不是统计错了/查重复」等。
  Use this skill for any operation or troubleshooting of the local AliExpressMonitor console at 127.0.0.1:18765:
  start/restart the service, run shop scans, triage new products (keyword pre-screen → visual review → state marking),
  change product states, batch-collect and upload products to the remote toy library via the Item Picker extension,
  or audit the product DB for duplicate / inflated "new product" counts.
agent_created: true
---

# AliExpressMonitor 运维操作（aliexpress-monitor-ops）

本地选品监控控制台。滚动店铺新品 → 人工/规则分诊（改状态）→ 批量采集详情并上传到远程玩具库。
本 skill 是这套流程的**唯一权威口径**，沉淀自一次完整的实战（含重装系统后修复、扫描、假新品去重、批量采集排障）。

## 0. 先读：环境与铁律

- 项目根：`D:\GitHub\AliExpressMonitor`；解释器：`.venv\Scripts\python.exe`（Python **3.12**，勿用系统其它版本）。
- 控制台地址：`http://127.0.0.1:18765`；健康检查 `GET /api/health` → `{"service":"AliExpressMonitor","status":"ok"}`。
- 数据库：`data\products.db`（SQLite）；扩展采集档案：`data\browser_profile`；令牌哈希：`data\settings.json`。
- 快捷脚本：`scripts\alm.py`（本 skill 自带，封装了以下所有 HTTP 操作）。**优先用它**，别再手搓 curl/httpx。
  ```powershell
  $py = "D:\GitHub\AliExpressMonitor\.venv\Scripts\python.exe"
  $alm = "<本skill目录>\scripts\alm.py"
  & $py -X utf8 $alm health
  ```

铁律：
1. **重活先申请许可**。全量扫描（31 店）、批量采集（几十上百件）都属重活：先给用户「量/预计耗时/占用/产物/如何中断」，得到明确同意再跑。（见全局 AGENTS.md）
2. **改 Chrome 页面绝不用盲 SendInput/点击**。本机前台常被 DSH 桌面/微信占据，盲点击会打到别的窗口。要用 Chrome 就命令行/API 控制；确需真鼠标键盘见 `aliexpress-image-editor` skill 的口径。
3. **写接口需要 CSRF**。所有 `POST/PATCH` 必须带 `x-csrf-token`（从 `GET /` 页面正则取）+ `Origin: http://127.0.0.1:18765` + `Content-Type: application/json`。`alm.py` 已自动处理。
4. **删数据前必备份**。任何 DELETE/去重清理前先复制 `data\products.db` 到 `backups\`。
5. **只改不提交**：改代码/DB 后不要自行 `git commit`，除非用户明说。

## 0.5 端到端标准作业流程（SOP）：监控 → 初筛 → **看图复核** → 上传

一条链把「当天最新品」从扫描一路送到远程玩具库。每步都有验收点，别跳步（重活先按第 0 节申请许可）。

```text
0) 服务在线     alm.py health                         → status ok（没起按第 1 节 WMI 启动）
1) 监控·扫描    alm.py scan-start                     → 拿 runId
                alm.py scan-watch <runId>             → 等到 status=succeeded
                alm.py scan-retry <runId>             → 若有失败店（LOGIN_REQUIRED 常见，重试即恢复）
                验收：run 成功；当天 newCount 用 db-dups 核一遍，确认不是「假新品」
2) 初筛·出表    triage.py classify --run <runId> --out .\triage-<runId>
                → 关键词分层 HIGH/MAYBE/SKIP + 下主图 + index.txt
                + 主对照表 triage-<runId>\sheet-NN.jpg
                + 排除对照表 triage-<runId>\sheet-skip-NN.jpg
                验收：对照表张数 × 20 ≥ 待判数；index.txt 行数与主图数一致
3) 看图复核     ⚠️ 必做，不可跳过（准确性优先于速度）
                逐张 read_image 看 sheet-NN.jpg，编号→商品查 thumbs\index.txt
                判定口径见 references/tf-classification.md
                再抽查 sheet-skip-NN.jpg，找「只写代号被误排除」的（NA H77 / MMC OX PS-24A 等）
                验收：主表每张都看过 + 排除表抽查过；每条结论能说出理由
4) 标记·分诊    alm.py set-state --ids <看过并通过的 id> --to to_process
                误判回退：alm.py set-state --ids <id> --to pending_review
                （非目标品类/存疑件保留 pending_review，汇报里单列）
                验收：alm.py products --state to_process --run <runId> 复核数量与看图结论一致
5) 上传·采集    前置：picker-status.online=true + toy-item-prod 已登录 + 单件试采通过
                alm.py picker-queue --state to_process --from-date today
                alm.py picker-watch                   → 盯到 queued=0 且 inFlight=0
                验收：这些商品 state=completed，今日 completed 数 = 应上传数
6) 收尾         alm.py db-stats                       → 今日 completed 对上、今天待处理清零
                汇报：run id/耗时、成功失败店数、新品数、看图通过并标记数、
                     剔除的误判（店铺+标题+链接）、从排除表捞回的漏网、仍拿不准的条目
```

**为什么必须看图**：关键词只能挡住明显品类（高达/龙珠/星战），挡不住「标题写 Hasbro 但图是 G.I. Joe 蛇兵」这种；也会漏掉「标题只有代号但图是 TF」这种。历史实测：run 45 有 1 条 HIGH 是误判（G.I. Joe），run 43 有代号件被误排除。**禁止批量标记未经看图确认的条目。**

**判定口径（2026-11-16 用户定调）**：`有变形玩具就判定为变形金刚系列，属于变形玩具即可` —— 核心问题是「**这个东西本身能不能变形/合体**」，不看 IP 归属。盖塔、魔神 Z、超机列传 SRL、Voltron/百兽王/Megazord 等非 TF 授权但能变形合体的，一律通过；明确不可变形的（兵人、机娘、雕像、不可变形合金成品、道具）排除。存量 `pending_review` 不翻旧账，新口径只作用于之后的新品。

变异处理：只采部分（`picker-queue --ids`）、只改部分（`set-state --ids`）、按某次扫描圈定（加 `--run <runId>`）。
积压/历史件：`--from-date` 换成具体日期或不加日期；量大会是重活，先申请许可。
整条链无人值守跑（定时任务形态）：把 0→6 串成一个 .ps1 后台跑，脚本只负责跑+出图，**看图与标记必须由人/agent 做**。

## 1. 启动 / 重启服务

**必须用 WMI 完全分离进程**，否则进程会随本会话结束被杀：

```powershell
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = 'cmd.exe /c "cd /d D:\GitHub\AliExpressMonitor && .venv\Scripts\python.exe -m alimonitor.launcher >> logs\launcher-now.out.log 2>> logs\launcher-now.err.log"';
  CurrentDirectory = 'D:\GitHub\AliExpressMonitor'
}
```

约 3–5 秒后 `alm.py health` 返回 ok 即成功。单实例互斥锁 `Local\AliExpressMonitorDashboard`，重复启动只会「打开已有实例」。
> 坑：`Start-Process -RedirectStandardOutput` 在本机会因 `NO_PROXY/no_proxy` 字典冲突失败；用 .NET Process 管道启动的进程会随父 shell 退出而死。**只用 WMI 法**。

Python 环境坏了（报 `No Python at '...Python312\python.exe'`）：`winget install --id Python.Python.3.12 -e --scope user`，装回原路径后 venv 无需重建。

## 2. 扫描店铺新品

前提：Chrome 里装了「AliMonitor 采集助手」扩展（本项目 `extension\` 目录，未打包加载）并保持在线（`alm.py overview` 看 `extensionOnline`；离线时启动扫描会自动拉起 Chrome 等 ~20s，仍离线报 409）。

```powershell
& $py -X utf8 $alm scan-start            # 全量所有启用店铺
& $py -X utf8 $alm scan-start --shops 1,2,5
& $py -X utf8 $alm scan-watch 44         # 轮询进度到结束
& $py -X utf8 $alm scan-retry 44         # 只重跑上次失败的店
& $py -X utf8 $alm scan-history --page 1
```

关键事实（**血的教训，务必记住**）：
- **每店最多抓 40 条**（扩展滚动懒加载的固有上限，Python 端无此常量）。
- **CAPTCHA_REQUIRED**：扫描会等人工过验证码。通常**不点也能自愈**（约 1 分钟自行通过），先观察别急着动手。
- **LOGIN_REQUIRED**（「登录状态已失效」）：多为**瞬时**，直接 `scan-retry` 一般 4/4 就恢复，不需要重新登录。
- 进度 `status`：`running`/`succeeded`/`failed`/`stopped`；`phase` 见 troubleshooting。

## 3. 商品初筛 + 看图复核（分诊）

**这一步是「分类」的核心，不能只用关键词一把过。** 分两段：脚本初筛 → 人/agent 看图定夺。

### 3.1 脚本初筛：`scripts/triage.py`

```powershell
$py  = "D:\GitHub\AliExpressMonitor\.venv\Scripts\python.exe"
$tri = "<本skill目录>\scripts\triage.py"

& $py -X utf8 $tri classify --run 45 --out .\triage-45   # 初筛 + 下主图 + 出对照表 + 报告
& $py -X utf8 $tri classify --run 45 --no-skip           # 不查排除项（跳过第 3.3 步时）
& $py -X utf8 $tri sheet .\thumbs .\sheet-again          # 只把已有缩略图重拼成对照表
```

产物（`--out` 目录下）：

| 文件 | 用途 |
|---|---|
| `report-<runId>-tf.md` | 分层报告：HIGH/MAYBE 表格（店铺/商品/命中/链接）+ SKIP 列表 |
| `thumbs\%02d_<id>.jpg` + `thumbs\index.txt` | 待判主图 + 编号映射（编号 TAB id TAB 等级 TAB 店铺 TAB 标题） |
| `sheet-NN.jpg` | 主对照表，5 列×300px、每表 20 图、编号黑底黄字 |
| `thumbs-skip\` + `sheet-skip-NN.jpg` | 排除项对照表，用来抽查有没有被误排除 |

打分口径：官方线 +3、第三方厂牌 +3、角色名 +2、命中硬排除词 −8；**无硬排除词**且 ≥3=HIGH、≥2=MAYBE，否则 SKIP。
**变形软词（2026-11-16 起）**：`voltron / golion / 百兽王 / 战神金刚 / zord / power rangers / getter / mazinger / 魔神 / 盖塔 / 超机列传 / super robot legend / srl-0x` 这些词**不再直接判 SKIP**，命中即强制进 **MAYBE 主对照表**，由看图复核决定「能不能变形/合体」。
`triage.py` **只读 DB + 下图片，不写库、不改状态**，改状态一律走 `alm.py set-state`。

### 3.2 看图复核（必做）

1. `read_image` 逐张看 `sheet-NN.jpg`，按 `index.txt` 把编号对回商品；
2. 判定口径见 `references/tf-classification.md`（通过清单 / 排除清单 / 实战误判案例）；
3. **核心判据：能不能变形/合体**（2026-11-16 用户定调「属于变形玩具即可」）。能变形合体 → 通过，不管是不是 TF IP（盖塔/魔神 Z/超机列传/Voltron/Megazord 都算）；明确不可变形（兵人/机娘/雕像/不可变形合金成品/道具）→ 排除。
4. 主表每张都要看，**不能只扫标题**——关键词挡不住「标题写 Hasbro、图是 G.I. Joe 蛇兵」；
5. 结论分三类：**通过**（待标 to_process）、**误判要剔除**（保持 pending_review）、**拿不准**（保持 pending_review，汇报单列）。
6. 非 TF 的变形玩具拿不准时，查官方/代理商页面是否写「变形 / 合体 / 可變形合體 / Combining / Transformable」，写了就算。

### 3.3 抽查排除表（容易被跳过，但漏网都在这里）

看 `sheet-skip-NN.jpg`，重点找两类漏网：
- **标题只写代号**的变形玩具：`NA H77`（Newage）、`MMC OX PS-24A`、`BT-08-05`、`DW-E64M`、`BWM-10`、`CS-02`、`RT-07`、`AT-01/02/03`（Apollo Toys）；
- **非 TF 授权但能变形合体**的：Getter/盖塔、Mazinger/魔神 Z、Super Robot Legend SRL、Voltron/百兽王、Power Rangers 合体 Megazord 等（旧口径会误排除，新口径应捞回）。

判为漏网的直接一起标 `to_process`。

### 3.4 改状态（看图之后）

状态值（**只有这四个**，传别的 422）：`pending_review`=待判断、`to_process`=待处理、`ignored`=已忽略、`completed`=已完成。

```powershell
# 列出（默认只 pending_review）
& $py -X utf8 $alm products --state pending_review --from-date today --page-size 100
& $py -X utf8 $alm products --state all --shop 7 --title hulk

# ★ 主用法：把「看过图确认通过」的 id 一次性改状态（scope=page，带乐观锁）
& $py -X utf8 $alm set-state --ids 6722,6723,6724 --to to_process

# 误判回退
& $py -X utf8 $alm set-state --ids 6742 --to pending_review

# 按筛选整体改状态（scope=filter，带一致性快照）——只在「整批都确定」时用
& $py -X utf8 $alm set-state --from-state pending_review --to to_process --from-date today
```

「今天/待处理」这类口语 → 用 `--from-date today`（按 `first_seen_at` 本地日期）或 `--run <runId>`（按某次扫描）精确圈定。改完用 `alm.py overview` 或 `products` 复核数量。
> **语义边界**：改状态是人工分诊动作。`set-state --from-state …` 这种整批操作**只适用于已经看图确认过的批次**；没看过图的绝不能一把梭，宁可一条条 `--ids`。不确定的商品（疑似别的品类）保留 `pending_review`。

## 4. 批量采集并上传到远程玩具库（toy-item-prod）

链路：控制台入队 → 浏览器里的 **Item Picker 扩展**（仓库 `D:\GitHub\toy-item-picker-chrome-extension`）领取任务 → 打开速卖通商品页抓详情 → 上传到 `https://39.107.244.239/api/ingest/products`（靠该 Chrome 档案里 toy 系统的登录 cookie，无 token）→ 回报 → 成功后商品置 `completed`。

前提（缺一不可）：控制台在跑、Picker 扩展在**运行中的 Chrome** 里、toy-item-prod **已登录**、`picker status.paired=true`。

```powershell
& $py -X utf8 $alm picker-status
& $py -X utf8 $alm picker-queue --state to_process --from-date today   # 把今天待处理入队
& $py -X utf8 $alm picker-queue --ids 1201,1202
& $py -X utf8 $alm picker-watch          # 盯进度（建议后台跑）
& $py -X utf8 $alm picker-clear          # 清空未领取的队列（在途不受影响）
```

硬约束：
- 只能入队 `pending_review` / `to_process`；队列只在**控制台内存**，重启控制台即清空。
- 每轮最多 3 件、件间 2–5s；`IN_FLIGHT_LEASE_SECONDS=210` 未回报自动退回队列。
- **采集窗口不能最小化**（最小化→PAGE_HIDDEN，详情图抓不到）。
- 上传失败（toy-auth/未登录）→ 商品状态不变、任务消失，**会白白消耗队列**。所以**先确认已登录再入队**。
- **卡在 `phase=opening-tab` 久久不动**：几乎都是 Picker 的 service worker 休眠/僵死。按顺序处置：
  1. `picker-clear` 清空 → 等 ~30–40s 让 `chrome.alarms`(0.5min) 把 SW 唤醒（`picker-status` 里 `online` 必须为 True、`lastActivitySecondsAgo` 在刷新）；
  2. 把 Chrome 窗口前台化（`Get-Process chrome | ? MainWindowHandle -ne 0` 拿 hwnd，`ShowWindow(9)+SetForegroundWindow`），别让它最小化；
  3. 先**单件试采**（`picker-queue --ids <一个>` + `picker-watch`）确认 12–20s 内 `opening-tab→extracting→uploading→completed`，再批量；
  4. 仍不动 → 让用户在 Chrome 里重载 Picker 扩展 / 重新登录 toy 系统。

详细排障见 `references/troubleshooting.md`。

## 5. 数据核查：别被"假新品"骗了

一天突然多出几百条"新品"几乎都是**同一商品被 AliExpress 换了 item id 形制**重复入库（历史实测：11-11 一天 924 条里 873 条是老商品换 id 重录，真新品仅 51）。

判断口诀：**`remote_product_id` 不可靠**——同一商品会有 `1005…` 和 `3256…` 两套 16 位 id。真正的"同一件"要看 **同店铺 + 同主图（`/kf/<hash>`）+ 同标题**。

```powershell
& $py -X utf8 $alm db-stats      # 各状态计数 + 今日入库/真实新增
& $py -X utf8 $alm db-dups       # 按 (店铺,主图hash) 找重复组，估算真实唯一商品数
```

发现大量重复时：先 `db-dups` 量化 → 备份 DB → 清理重复行（保留最早一条、把 `scan_runs.new_count` 校正为真实新增）→ 长期修复靠 `alimonitor\services\products.py` 里"同图+同标题"兜底去重（该改造已落地并带测试）。完整口径见 `references/data-diagnostics.md`。

## 6. 发布选品情报页（GitHub Pages）

把扫描库里的每日新品渲染成静态页，推到 `D:\GitHub\aliexpress-scan-intel`（站点 https://lyt3905.github.io/aliexpress-scan-intel/ ）。

```powershell
$py  = "D:\GitHub\AliExpressMonitor\.venv\Scripts\python.exe"
$pub = "<本skill目录>\scripts\publish_scan_daily.py"

& $py -X utf8 $pub                      # 全量同步（缺哪期补哪期）+ commit + push
& $py -X utf8 $pub --dry-run            # 只报「要改哪些文件」，不写盘
& $py -X utf8 $pub --no-push            # 写完只本地提交，不推送
& $py -X utf8 $pub --date 2026-11-13    # 只重渲指定日期（可重复/逗号分隔）
& $py -X utf8 $pub --list               # 列出库里有新品的日子 vs 已发布页
```

产物（写入 `--out`，默认 `D:\GitHub\aliexpress-scan-intel`）：

| 文件 | 内容 |
|---|---|
| `<YYYY-MM-DD>.html` | 当天新品卡片（按店铺 chip 归集 + 搜索），缩略图直接引速卖通图床 `_350x350`，带 `referrerpolicy="no-referrer"` |
| `index.html` | 最新一天的日页逐字节副本（入口页） |
| `archive.html` | 全部期号按日期倒序，最新一期带「最新」徽标 |

口径（与历史 24 期完全一致，已回归验证）：日期按 **UTC+8 入库日**（`date(first_seen_at,'+8 hours')`）归档；`扫描 N 次` 用 `scan_runs.finished_at` 归日（**不是 started_at**），`覆盖店铺` 取当日各 run 的 `scan_shop_results`；期号 `第 N / M 期` 中 M = 日页总数，**新增一期会让所有老页的分母变化**，所以一次发布会改动全部老页。幂等：无变化时打印「无变化，跳过提交。」且不产生 commit。`--no-commit` 只写文件不动 git。

由 `run-daily-scan.ps1` 的 `Publish-Digest` 在扫描结束后自动调用（失败只记 WARN，不影响扫描退出码）。

## 7. 命令速查

| 命令 | 作用 |
|---|---|
| `health` | 服务健康 |
| `overview` | 概览（店铺数/今日新增/最近扫描/趋势/每店新增） |
| `scan-start [--shops 1,2]` | 发起扫描 |
| `scan-watch RUNID` / `scan-status RUNID` / `scan-retry RUNID` / `scan-history` | 扫描进度/详情/重试/历史 |
| `triage.py classify --run RUNID [--out DIR]` | **初筛**：分层 + 下主图 + 出主对照表/排除对照表 + 报告 |
| `triage.py sheet <dir> <prefix>` | 把已有缩略图重拼成对照表 |
| `products [--state] [--shop] [--from-date] [--to-date] [--run] [--title] [--all]` | 列商品 |
| `set-state --to STATE (--ids …|--from-state … [--from-date …])` | 批量改状态（看图确认后用 `--ids`） |
| `picker-status` / `picker-queue` / `picker-watch` / `picker-clear` | 采集队列 |
| `db-stats` / `db-dups` | 库内计数 / 重复诊断 |

## 8. 参考

- `references/api-reference.md`：全部 HTTP 接口 + 请求/响应体 + 鉴权细节。
- `references/tf-classification.md`：**变形玩具判定口径**（通过清单/排除清单/实战误判案例/复核步骤）——第 3 节看图复核必读。2026-11-16 起核心标准是「能不能变形/合体」，不限 TF 授权 IP。
- `references/troubleshooting.md`：扫描/picker/扩展/登录 常见故障与处置。
- `references/data-diagnostics.md`：假新品去重诊断 SQL、清理步骤、products.py 去重改造。
- `scripts/alm.py`：控制台 API 封装（扫描/状态/采集/核查）。
- `scripts/triage.py`：新品初筛（分层 + 下主图 + 出对照表 + 报告），只读不写库。
- `scripts/publish_scan_daily.py`：选品情报页生成 + 发布（渲染日页/入口页/归档页，commit + push 到 `aliexpress-scan-intel`），只读 DB。
