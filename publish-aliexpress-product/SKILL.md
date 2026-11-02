---
name: publish-aliexpress-product
description: |
  在速卖通（AliExpress）卖家后台发布 / 重发商品：定位到卖家**真实已登录**的 Edge 窗口 →
  全屏截图看清当前页 → 核对商品信息与主图 → 主图交给图片编辑器 → **用真实鼠标键盘（SendInput）
  像人一样点提交** → 回到页面确认发布成功页。适用于"把这个商品挂上去 / 重新发布这个 listing /
  改完主图后提交 / 确认商品到底发布成功没有"这类请求，也用于只读排查"商品为什么没上架"。
  Use when the user asks to publish or republish an AliExpress seller listing, submit a listing
  after fixing its main image, or verify whether a product actually reached the publish-success page.
  Never uses CDP / DevTools / browser automation — only simulated human mouse + keyboard.
---

# 速卖通商品发布（真实鼠标键盘 · 模拟人手）

> **一句话：截图当眼睛，SendInput 当手，每一步都能在屏幕上看见。**
> 绝不开调试端口、绝不注入 JS、绝不调 DOM —— 平台侧看到的就是一个正常人在点。

## 零、硬约束（违反任何一条都停手）

1. **禁止浏览器自动化**：不碰 CDP / DevTools / `browser_prepare` / `browser_*` 任何工具；不注入 JS；不读 DOM。
   调试端口附着本身就是平台风控的强信号。
2. **所有输入必须是「人手级」的真实输入**：鼠标用 `click {scope:"desktop"}`（走 SendInput，真实光标真的会动），
   键盘用 `type_text` / `press_key` / `hotkey`。实测返回 `route:"global_input"`。
3. **不用无障碍接口代替人手**：`set_value`（UIA ValuePattern）、`background` 模式的 UIA Invoke / PostMessage 全部不用 ——
   它们是"程序在改控件"，不是"人在点"。而且 Chromium 页面往往根本不认这些投递。
4. **坐标只有唯一来源**：`get_desktop_state` 的全屏截图。见第二节。
5. **提交类动作（提交 / 发布 / 确认发布 / 删除）必须先截图 + 得到用户明确同意**，一次只走一步。

## 一、工具清单（全部带 `cua_driver_native__` 前缀）

**允许：**

| 用途 | 调用 | 说明 |
| --- | --- | --- |
| 眼睛（唯一坐标源） | `get_desktop_state {screenshot_out_file}` | 全屏 1920×1080，和卖家看到的版式一致 |
| 真鼠标点击 | `click {scope:"desktop", x, y}` | SendInput；真实光标移动 + 真实按下 |
| 拟人预备动作 | `move_cursor {scope:"desktop", x, y}` | 先把真实指针挪过去，停一下再点 |
| 键盘 | `type_text` / `press_key {scope:"desktop"}` / `hotkey {scope:"desktop"}` | 打到**当前前台**应用 |
| 粘贴长文本 | `clipboard_write` + `hotkey {scope:"desktop", keys:["ctrl","v"]}` | 标题/描述/属性用这条最稳 |
| 滚动 | `scroll {scope:"desktop", x, y, direction, amount}` | 真实滚轮事件 |
| 找窗口/认店 | `list_apps` / `list_windows` / `get_window_state`（只读） | 拿 pid、窗口标题、页面 URL |
| 校准 | `get_cursor_position` / `get_screen_size` | 确认坐标空间没跑偏 |

**禁用（写在这里是为了手滑前能想起来）：**

`browser_prepare`、`get_browser_state`、`browser_navigate`、`browser_click`、`browser_type`、
`browser_dialog`、`browser_set_input_files`、`browser_download`、`browser_pointer`、`page`、
`set_value`、`click {scope:"window"}`、`click {delivery_mode:"background"}`、
`type_text {delivery_mode:"background"}`、`verify_state`（它靠 UIA 树断言，只读可以，但别拿它当动作）、
`kill_app` / `launch_app`（对 Edge 一律不动）、`bring_to_front`（用真实点击激活，别程序化抢前台）。

## 二、坐标：只有一个空间，不做任何换算

实测（2026-10，Windows，Cua Driver 0.28.0，本机 1920×1080）：

| 来源 | 空间 | 能不能用来点 |
| --- | --- | --- |
| `get_desktop_state` 截图 | **1920×1080**，与 `click{scope:"desktop"}` 同一空间 | ✅ **唯一可用** |
| `get_cursor_position` | 同一空间 | ✅ 校准用 |
| `list_windows` / `window_bounds` | 3840×2065（DPI 虚拟化出来的 2× 假象） | ❌ 别用 |
| `get_window_state` 截图 | 1567×848（压过 `max_image_dimension`） | ❌ 别用来点 |
| `elements[].frame` | 逻辑 px，相对窗口 | ❌ 别用来点 |

`click {scope:"desktop", x, y}` 的实测返回：

```
{"content":[{"text":"✅ Sent click via SendInput at screen (900,215) on HWND 0x3d0356 (desktop scope)."}],
 "structuredContent":{"delivery":{"mode":"not_applicable"},"effect":"unverifiable","route":"global_input"}}
```

- `route:"global_input"` = 系统级真实输入，正是要的效果；
- `effect:"unverifiable"` = **它不保证结果**，永远自己再截一次图确认。

## 三、拟人节奏（不只是为了好看）

机器可以 0ms 连点，人不会。放慢节奏能降低风控观感，也让每一步可回滚：

- 点击前：`move_cursor` 到目标 → 停 **200–500ms** → `click`；
- 打字：`type_text` 的 `delay_ms` 设 **60–120**；长文本改用"写剪贴板 + Ctrl+V"；
- 两动作之间停 **400–900ms**；
- 滚动：`amount: 3–5`、`by: "line"`，分几次滚，不要一次滚到底；
- 同一个坐标不要连点两次；连续操作之间让鼠标动一动，不要每次都精确落同一个像素。

## 四、选窗口 + 认店

```
cua_driver_native__list_apps                     # 找 msedge.exe 的 pid
cua_driver_native__list_windows { pid }          # 看窗口标题
cua_driver_native__get_window_state { pid, window_id, query: "https://", include_screenshot: false,
                                     max_elements: 400, max_depth: 12 }   # 读 Document.value 拿 URL
```

**同一个 pid 下可能挂着多个 Edge 窗口 = 多个用户配置文件，`channelId` 才是店铺的硬标识。**

| 窗口标题里的配置 | channelId | 店铺 |
| --- | --- | --- |
| `… - 个人 - Microsoft Edge` | **2465459** | **PureSun Toys Store** |
| `… - 个人 2 - Microsoft Edge` | **2348249** | （另一个店） |

认店顺序：**URL 里的 channelId ≥ 标题里的配置昵称 ≥ 问用户**。
认错了就是在别人店铺里发布 —— 比没发更糟。**认不准就停下来问。**

> `list_windows` 的 `app` 字段时有时无，别拿它当唯一过滤器；用 `pid:` 过滤或看 `title`。

## 五、一次操作的标准流程（每步都走完）

```
① 截图      get_desktop_state { screenshot_out_file: "...\\ae-<step>.png" }
② 看图      用 read 工具看那张 PNG（别让 base64 进上下文），确认版式和坐标
③ 描述      告诉用户"我要点哪里、为什么"（提交类必须等他点头）
④ 动作      move_cursor → 停 → click / type_text / hotkey { scope:"desktop" }
⑤ 再截图    重新 get_desktop_state，确认页面真的变了
⑥ 断言      只有截图证明成功才算数
```

**`effect:"unverifiable"` + "动作已送达" ≠ 事情成了。** 没有新截图证据，不许说"已完成"。

## 六、工作流

### 0. 绑定窗口、确认店铺
见第四节。确认后把 pid / window_id / channelId / 店铺名记在对话里，后面每步复核。

### 1. 摸清现状 + 核对商品
截图看完当前页（列表页/编辑页/成功页），读出**标题、商品 ID、类目、主图、必填红标**，和用户对一遍。

⚠️ **别猜 URL**：`.../item_product/product_list?channelId=...` 这类拼出来的地址会 404。
入口要么让用户从导航点到位，要么让用户把链接给到地址栏。

### 2. 主图处理
交给 `aliexpress-image-editor`（`C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\SKILL.md`）：
回填 800×800 合成主图 → 拖成主图 → 补海关监管属性。

**两个技能共用同一套「眼睛/手」口径**（10-29 统一）：`get_desktop_state` 全屏截图当坐标源、
`click {scope:"desktop"}` 走 SendInput 真实点击、键盘走 `type_text`/`hotkey`。
所以这里量的坐标在那个技能里可以直接用，反之亦然 —— 不要一边用全屏像素、一边用旧的
"窗口截图 − 窗口偏移 × 2.4" 物理坐标。切换技能时不换坐标系，只换流程。

### 3. 填字段
对每个输入框：**真实点击输入框 → `ctrl+a` 全选 → 粘贴/输入**。别指望 Tab 顺序，别盲敲。

```
click { scope:"desktop", x: <输入框中心>, y: <输入框中心> }
hotkey { scope:"desktop", keys:["ctrl","a"], x: <同一点>, y: <同一点> }
clipboard_write { text: "..." }
hotkey { scope:"desktop", keys:["ctrl","v"], x: 同一点, y: 同一点 }
```

填完立刻截图，确认值真的落进去了（中文/emoji/长度截断都要看一眼）。

### 4. 提交（要过闸）
1. 截图，把「提交」按钮圈出来给用户看（描述位置：哪个区块、旁边是什么）；
2. **等用户明确说"点"**；
3. `move_cursor` 到按钮 → 停 400ms → `click {scope:"desktop"}`；
4. 立刻截图，看有没有参数校验红字 / 二次确认弹窗。

按钮文案在变（提交 / 发布 / 确认发布 / 保存并发布）—— **按语义找，按截图确认**，别记死一个坐标。

### 5. 验收
**URL 必须落到 `itemPublish/publish_success`**（读 `Document.value`，或直接看截图地址栏）。
看到成功页才算发布完成；停在报错页就把那一页的红字原文 + 截图交给用户。

## 七、安全闸门（不可跳过）

1. 不开调试端口、不注入脚本、不调 DOM —— 用户没批准也不行。
2. 出现验证码 / 短信校验 / 滑块 / 异地登录提示 → **立刻停手**，截图给用户，让他自己处理。
3. 商品 ID、店铺、类目进流程前先对一遍；靠 `channelId` 认店。
4. 截图和回复里不要出现密码、token、后台密钥。
5. 提交 / 删除 / 改价这类动作：**一次一步**，截图 + 用户明确同意后才动。
6. 卖家说"点了"不等于成了 —— 自己截图断言。
7. 真实点击会移动卖家鼠标。开始前一句话告知："接下来我会动一下你的鼠标"；动作之间别乱点。
8. 慢就是快：宁可多截一张图，也不要盲点第二下。

## 八、失败处理

- 打开是登录页 → 让用户在**真实 Edge** 里手动登录，再从第 0 步重来。不要自己起新 profile。
- 点下去没反应 → **第一件事查 DPI**（`get_screen_size` 若返回 `@ 2x`，任何 1920 口径的坐标都点不中）；其次看是不是弹窗/遮罩挡住；再考虑是否需要先滚动到可视区（截图里没看到就别点）。
- 光标会动、悬停有反应、但点不进去 → 大概率是坐标空间错（DPI/缩放），不是权限、不是锁屏、不是风控。别在权限/前台窗口上纠缠。
- 打字没进框 → 检查输入框是否真的拿到焦点（截图里有没有光标/占位符消失）；改用"点一下 + ctrl+a + 粘贴"。
- 滚动没动 → 用 `scroll {scope:"desktop", x: 页面中央, y: 页面中央}` 明确指定滚动区域。
- 提交后停在参数校验页 → 把红字原文 + 截图给用户，不要催着重试。
- 页面白屏/转圈 → 停 2–3 秒再截一张，别连点。

## 九、已验证 / 待验证

已验证：
- `get_desktop_state` → 1920×1080，`scale_factor: 1`，与 `click{scope:"desktop"}` 同空间。
- `click {scope:"desktop"}` → `"Sent click via SendInput at screen (x,y)"`，`route:"global_input"`，真实光标移动。
- `move_cursor {scope:"desktop"}` → `route:"global_input"`，`get_cursor_position` 读回同坐标。
- `move_cursor {scope:"window"}` → `route:"synthetic_events"`，真实光标不动（只动叠加层）→ 所以别用 window 作用域。
- `get_window_state` 能读到网页内容（`total_element_count` 330–1833），`role:"Document"` 的 `value` = 当前 URL，
  元素无障碍名在 **`label`** 字段（不是 `name`）。→ 适合**只读确认**，不适合当坐标源。
- **200% 缩放的机器上**：`get_screen_size` 返回 **`3840x2160 pixels @ 2x`**，`get_desktop_state` 的 PNG 预览标注 2730×1536
  但**实际要 ×≈2.16 才是物理像素**（用 1:1 裁剪核对过：竖排标签预览 y=187 ↔ 物理 y=405）。
  → 有 2x 时，坐标一律从自建 1:1 裁剪截图量，官方预览图只用来判断"现在是什么页面/在前台吗"。

待验证（第一次真跑时补进来）：
- `type_text {scope:"desktop"}` 在中文输入场景下是否稳定（不稳就一律走剪贴板 + Ctrl+V）。
- 速卖通发布页「提交」按钮的实际文案与位置。
- 成功页 `itemPublish/publish_success` 的稳定特征文案。

## 九之二、2026-10-29 实战踩坑（channelId 2465459，7 个商品，全部"只改不提交"）

**1. "鼠标点击完全没反应"的 90% 是 DPI，不是权限**

屏幕 3840×2160 @ 200%，而自建 PowerShell 工具是 DPI-unaware：
- `CopyFromScreen` 只截到屏幕**左上角 1920×1080**（窗口右半边根本没进图）；
- `SetCursorPos/点击` 坐标被系统按 DIP 处理 → 点 A 命中 B。
- 表现极具误导性：光标会动、悬停态会出现、`SendInput` 返回成功、进程不是锁屏也不是安全桌面 → 很像"被风控拦了"。
- 修法：进程先 `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`，之后 `GetSystemMetrics=3840×2160`，截图与点击同空间。
- 判据：`get_screen_size` 说 `@ 2x` 就别再用 1920 口径的坐标。

**2. 同一 pid 下两个 Edge 配置窗口完全重叠**

`list_windows {pid:<msedge>}` 会返回两个同尺寸最大化窗口：
- `… - 个人 - Microsoft Edge` → 本次目标店（例：PureSun Toys Store / 2465459）
- `… - 个人 2 - Microsoft Edge` → **另一家店**（例：Morph Toys Store / 2348249）
两层完全重叠，点到上层就跑到别人店里去了。→ 每次点击前先看 `fg` 标题里有几个"个人"；
必要时 `SetForegroundWindow` 精确拉回（返回 True 即成功），或点任务栏 Edge 按钮再核对。

**3. 键盘兜底路径（鼠标彻底不可信时）**

`F6` → 焦点进 Edge 竖排标签栏；`↑/↓` 换标签（会弹预览气泡，气泡里能读到域名）；`Enter` 激活；`F11` 全屏切换；`ctrl+0` 重置缩放。
**`ctrl+l` 实测不可靠**（地址栏不高亮）。真正稳的导航是：`ctrl+t` 新标签 → `clipboard_write` 写 URL → `ctrl+v` → `Enter`。

**4. 未提交的改动只活在标签页内存里**

7 个商品逐个改主图 + 补海关，全程不提交 → 一旦刷新/重开该页，所有改动回到平台已保存状态。
所以：① 每个商品改完立刻裁剪核对并留图；② 别开一堆页到最后才回头验；③ 交付时明确告诉用户"改动未保存，刷新即丢"。

**5. 商品页关键坐标（3840×2160 口径，仅供第一次缩小搜索范围，每次仍要现量）**

| 元素 | 物理坐标 |
|---|---|
| 扩展图标「AliExpress 图片编辑器」 | (2910, 40) |
| 回填到商品页 | (3707–3711, 256–262) |
| 回填弹窗右上 ✕ | (3135, 432)；弹窗高时 (3135, 462) |
| 图片行第 1 格中心 / 拖拽落点 | (653, 1855) / **(630, 1855) 左半边** |
| 「去设置」（滚到海关区后） | (638, 590) |
| 海关抽屉「确认」 | (3720, 1987) |
| 商品页「提交」（**绝不点**） | (2634–2816, 1926–2013) |
| 任务栏 Edge 按钮（切店用） | (600, 2100) |

## 十、退役说明（legacy，留档）

| 实现 | 状态 | 原因 |
| --- | --- | --- |
| `scripts/ae_browser.py`（CDP + 专用 profile） | 退役 | 调试端口附着 = 风控强信号；且那条 profile 属于另一个店铺 |
| `browser_*` 工具族 | 禁用 | 同属浏览器自动化（CDP） |
| `set_value` / `background` 投递 | 禁用 | 无障碍通道改控件，不是人手输入；Chromium 常直接拒收 |
| `click {scope:"window"}` 像素模式 | 不用 | 坐标落在压缩后的窗口图里（3840→1567），容易点错 |
| `screen.py` 的 Win32 `osclick` | 被替代 | 新方案的 `click{scope:"desktop"}` 就是同一件事，且带截图/校准 |

顺带记 `ae_browser.py` 的已知 bug：`cmd_click` 的 dry-run 分支用 `document.querySelectorAll(sel)`，
遇到 `text=提交` 会抛 `SyntaxError: Failed to execute 'querySelectorAll' on 'Document'`；
只有 `--yes` 分支的 `page.click` 认 `text=` 选择器；`connect()` 固定取 `ctx.pages[0]`。
