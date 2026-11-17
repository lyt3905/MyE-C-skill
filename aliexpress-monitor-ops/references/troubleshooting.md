# 故障排查手册

## 一、服务 / 启动

**症状：`启动控制台.bat` 报 `No Python at '...Python312\python.exe'`**
- 原因：venv 的 `pyvenv.cfg` 指向的解释器被删（重装系统常见）。
- 修：`winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity`，装回 `C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe` 后 venv 无需重建。
- 别拿别的 3.12（wb-proxy / embeddable）当基础解释器：它们缺 `venv`/`multiprocessing`，会在 `uvicorn/_subprocess.py: import multiprocessing` 处炸。

**症状：进程随会话结束被杀 / 起不来**
- 必须用 WMI 分离进程（见 SKILL.md 第 1 节）。`Start-Process -RedirectStandardOutput` 在本机报 `NO_PROXY/no_proxy 字典冲突`；.NET Process 管道启动会随父 shell 退出而死。

## 二、扫描

| 现象 | 处置 |
|---|---|
| extensionOnline=false | 启动扫描会自动拉起 Chrome（`extension_launcher`，`alimonitor\chrome.py:115-143`）等 ~20s；仍离线报 409 EXTENSION_OFFLINE。也可手动 `Start-Process chrome.exe -ArgumentList '--profile-directory=Default','http://127.0.0.1:18765/'`，**等 30–40s** 让扩展 SW 上线。 |
| CAPTCHA_REQUIRED | 扫描进入 `waiting_captcha`，Chrome 被提前台。**通常不点也会在 ~1 分钟自愈**，先观察。 |
| LOGIN_REQUIRED（登录状态已失效） | 多为瞬时。直接 `scan-retry <runId>`，一般 4 家全恢复，不必重新登录。 |
| 某店只抓到 40 条 | 正常上限（扩展滚动懒加载固有）。要更多条需换策略，非 bug。 |
| PFILE_LOCKED | 登录浏览器（采集档案）还开着，先关掉再扫。 |

## 三、批量采集 / Item Picker

**症状：`phase` 长时间停在 `opening-tab`（>60–90s 不动）**
- 根因：Picker 的 service worker 休眠/僵死（Chrome 繁忙、窗口最小化、前台被别的程序占据时高发）。表现为只发过一次 `progress` 就再无声，210s 后被 `sweep_stale` 退回队列→再领取→再卡。
- 处置顺序：
  1. `alm.py picker-clear` 清空队列；等 30–40s 让 `chrome.alarms`(0.5min) 唤醒 SW。`picker-status` 里 `online=true` 且 `lastActivitySecondsAgo` 持续刷新才算活。
  2. 把 Chrome 窗口前台化且**不要最小化**：`Get-Process chrome | ? MainWindowHandle -ne 0` 取 hwnd；`ShowWindow(hwnd,9)` + `SetForegroundWindow`。（最小化 = 页面隐藏 = 详情区不渲染 → PAGE_HIDDEN。）
  3. **先单件试采**：`picker-queue --ids <一个>` + `picker-watch`，确认 12–20s 内 `opening-tab→extracting→uploading→completed`，再批量。
  4. 仍不动：让用户在 Chrome 里「扩展程序」重载 Item Picker，或重新登录 toy 系统。

**症状：上传失败 / 商品状态一直不变**
- `submit_report` 只有 `succeeded && uploaded` 才置 completed；失败（toy-auth 未登录 / 403 / 风控）商品状态**保持不变、任务消失**——等于白白消耗队列。所以**必须先确认 toy-item-prod 已登录再入队**。
- toy 登录态看 `picker-status`/实际试采；无法从 Chrome `Network\Cookies` 读（Chrome 独占锁：`shutil.copy2` → `PermissionError WinError 32`，`[System.IO.File]::Open(...,FileShare.ReadWrite)` 仍被拒，sqlite `immutable=1` → unable to open）。**别在这上面绕太久，直接单件试采最准。**

**症状：队列里一堆但不动**
- 队列只在控制台内存，重启控制台即清空；扩展没在线 / 没配对 / 没登录都会不动。
- 每轮最多 3 件、件间 2–5s；撞风控需人工滑块或换出口 IP，事后 3 分钟冷却（`COOLDOWN_PHASE`）。

## 四、本机环境坑（Windows）

- **前台被 DSH 桌面 / 微信占据**：盲 `SendInput`/`mouse_event`/`SendKeys` 会打到 DSH 或聊天窗口，**严禁盲点击**。要操作 Chrome 用命令行/API。
- `Get-Process chrome | MainWindowHandle` 长期为 0（Chrome 多进程）→ 不能靠它前台化；用 `EnumWindows` + 窗口标题（控制台窗口标题为「数据工作台」）找 hwnd。
- PowerShell 5.1 无 `Join-String`；命令串里 `<` 会被当重定向解析错误。**复杂 Python 逻辑写成临时 `.py` 用 `.venv\Scripts\python.exe -X utf8` 跑**，用完删除（别留在项目根）。
- 嵌套引号的 python `-c` 在 PowerShell 里极易被拆坏 → 一律落到临时 .py 文件。

## 五、Chrome 扩展清单（Default 档案实测）
| 扩展 ID | 说明 | 位置 |
|---|---|---|
| `pleccjjpkgdkaplmffaekhedlohfadlp` | AliMonitor 采集助手 v1.5.0（扫描用） | 未打包，`D:\GitHub\AliExpressMonitor\extension` |
| `fmhebkldbpkddappleogimjkobfndbnn` | Item Picker v0.2.14（采集上传用，含 `aliMonitorToken`/`aliMonitorPickerLoopActive`） | 未打包，`D:\GitHub\toy-item-picker-chrome-extension` |
| `ioadaikpljilagoddljnamloiebcoopb` | 店小秘助手 | 商店装 |
| `ncennffkjdiamlpmcbajkmaiiiddgioo` | 迅雷下载支持 | 商店装 |

远程玩具库：`https://39.107.244.239`（http 301→https，首页「商品管理」SPA）；上传接口 `POST /api/ingest/products`（靠浏览器会话 cookie，`credentials:include`，无 token）；登录页 `/login`（该档案已存账号 `lyt`）。
