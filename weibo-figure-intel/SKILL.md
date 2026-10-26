---
name: weibo-figure-intel
description: |
  This skill collects Weibo posts from accounts the user follows and extracts intelligence
  about anime figures (手办) and action figures / articulated dolls (可动人偶) — new product
  announcements, pre-orders, release dates, re-releases, delays, exhibitions and photo reviews.
  It fetches posts with the user's Weibo login cookie, pre-filters them against a curated
  keyword lexicon, has the agent structure the surviving posts into intel records, attaches
  each record's product photos, and renders a digest whose DEFAULT view is a flat
  new-product list (新品清单) — one numbered row per product, decoupled from intel-type
  grouping, with same-product reports merged — plus a toggle back to the full
  type-grouped view. Since it runs daily, it also tracks what is NEW: entries whose product
  never appeared in any earlier digest get a 🆕 未读 marker plus a sticky unread counter, and
  the marker flips to ✓ 已读 automatically once the reader has actually viewed the card, so
  the next run only surfaces what hasn't been seen yet. Output comes as both Markdown and an
  HTML file with inline image thumbnails, a click-to-zoom lightbox gallery, search / filter
  controls, and clickable links back to the original Weibo posts.
  Triggered when the user asks for 手办情报 / 可动人偶情报 / figure news, says things like
  "看看今天有什么手办情报", "微博上有没有新开订的手办", "抓一下我关注的手办号",
  "collect figure news from Weibo", or wants to tune the intel keyword lexicon.
agent_created: true
---

# 手办情报雷达（weibo-figure-intel）

## Purpose

从用户关注的微博账号中采集微博，筛出与动漫手办 / 可动人偶相关的情报，抽取成结构化
字段，产出简报。目标是将"刷微博找新品/开订信息"这一动作自动化，服务于店铺选品。

> **用户的核心诉求是「微博里告诉了我有哪些新品」**，不是情报分类学。因此简报的默认
> 形态是**脱离分类的纯新品清单**（连续编号、一行一款），分类分组退居次要视图。
> 调优时优先保证**新品不漏**，其次才是分类准确。

简报默认产出两种格式：

| 格式 | 用途 |
|---|---|
| `output/手办情报-YYYY-MM-DD.html` | **浏览器阅读**。**默认打开「🆕 新品清单」视图**（用户最关心"微博里有哪些新品"）：脱离分类的**纯新品清单**，每条独占一行、带连续编号，与情报类型分组完全解耦。新品判定覆盖：新品公布 / 开订 / 发售 / 再版四类本体，另有两类启发式扩展——「实物测评」类含首次实物曝光语义（首曝 / 大货实测 / 实物首秀等，`FIRST_LOOK_PAT`）且非怀旧向（`NOT_FRESH_PAT` 排除回顾 / 情怀 / 老货）、「展会」类含会场新品语义（特别发售 / 限量 / 限定 / 首展 / 现场售卖等，`EVENT_NEW_PAT`）。可一键切回「全部情报」视图按类型分组浏览全部条目。同一款产品的多条微博**自动合并成一张卡**（`brand|character` 键归一，字段互补、配图并集，其余来源保留为"另有 N 条报道"可点击直达）。每条情报独占一行（左栏正文，右栏缩略图 / 元信息 / 来源按钮），右栏顶部放最多 3 张配图缩略图，多余用 `+N` 角标；**点缩略图弹出放大预览**，同一条情报的全部配图可左右翻页（← → / 触屏滑动 / Esc 关闭）。支持关键词搜索与类型/相关度筛选（类型筛选仅「全部情报」视图生效），分组标题随筛选自动隐藏空组，标题与按钮均可直达微博原帖 |
| `output/手办情报-YYYY-MM-DD.md` | 存档、粘贴进对话、二次加工。首节为「🆕 新品清单」表（脱离分类的纯新品编号清单，含合并报道数与状态说明），其后为全部情报分组表 |
| `output/手办情报-总览.html` | **跨天汇总单页**（`build_index.py` 产出）。顶部一条**日期切换器**，点某天只看那天的情报、点「全部」看累计；另有「新品清单 / 全部情报 / 按天浏览」三视图。解决「每天一个文件、要开好几个页面才能横向对比」的问题。见「总览页」一节 |
| `output/手办情报-总览.md` | 总览的存档版：跨天新品清单表 + 按天索引表（含每日条数、新品数、当日简报链接） |

> ⚠️ **配图必须下载到本地**，不能外链——微博图床会 403，原因见「已知限制」第 8 条。
> **单日简报**的缩略图以 base64 内嵌（保证单文件也有图可看），**总览页例外**——它体量大，
> 缩略图走 `media/` 相对路径（理由见「总览页」一节）。两者的放大预览图都走
> `output/media/view/`。**交付时要连 `media/` 目录一起给**，否则预览会提示图片没加载。

## Trigger

触发场景：

- 用户问"有什么新的手办情报 / 可动人偶情报 / figure 新闻"
- 用户说"抓一下微博""看看我关注的手办号发了什么"
- 用户要调整词库、白名单、黑名单
- 用户反馈某条情报漏了或噪声太多

## 前置条件

1. **微博登录 Cookie**（必需）。存放于 `scripts/wb_cookie.json`，格式：

   ```json
   { "cookie": "SUB=xxxxx" }
   ```

   获取方式：**Edge / Chrome** 登录 `weibo.com` → `F12` → 「应用程序 / Application」→
   存储 → Cookie → `https://weibo.com` → 复制 **Domain 为 `.weibo.com` 的那一行 `SUB`**。

   ⚠️ 两个坑：

   - `SUB` 是 **HttpOnly**，在 Console 里敲 `document.cookie` 取不到，必须在
     「应用程序 / Application」面板里看。
   - Cookie 表里可能有多行 `SUB`（Domain 为 `.sina.com.cn` / `.weibo.com` / `.weibo.cn`），
     **它们的值不一定相同**。只有 `.weibo.com` 那一行的值能通过 `weibo.com` 桌面端接口的
     登录校验——实测中 `.sina.com.cn` 的同名 `SUB` 会返回 `ok:-100`（未登录）。

   更省事的替代路径：`F12` → 「网络」→ `F5` 刷新 → 右键任一请求 → 「以 cURL 格式复制」，
   整段粘给 agent，由 agent 只提取 Cookie 部分。

   该文件已在 `.gitignore` 中排除，不会进入仓库。

   > ⚠️ **Cookie 失效时不要试图从浏览器 cookie 库自动提取**（2026-09-20 实测，排查耗时约 12 次工具调用，结论是死路）：
   >
   > - Edge / Chrome 127+ 用 **App-Bound Encryption** 加密 cookie——DB 里 `encrypted_value` 的
   >   十六进制前缀是 `763230`（即 `v20`，不是旧版 `v10`）；密钥由 ABE 服务校验调用进程身份，
   >   任何第三方进程（含 DPAPI + AES-256-GCM 方案）都解不开。真正的值在 `encrypted_value`
   >   （BLOB）列，`value` 列全为空串，别在 `value` 上白找。
   > - 浏览器运行时会**独占锁定** `User Data/<profile>/Network/Cookies`
   >   （读 `User Data/Default/...` 报 `PermissionError [Errno 13]`，`cp` 报 `Device or resource busy`），
   >   连 profile 复制都做不了，所以「复制 profile 再让浏览器自己解密」也走不通。
   > - 已验证的旁路全部无效：所有**未被锁定**的 profile（Edge Guest / Profile 2–4、Chrome Default）
   >   里都没有任何 `host_key like '%weibo%'` 的 cookie，主人的微博登录只存在于被锁的
   >   Edge `Default` 与 `Profile 1` 中。
   > - 判定是「SUB 过期」还是「Domain 取错」从外部无法区分。**免登录对照端点用
   >   `GET https://weibo.com/ajax/profile/info`（带普通 Chrome UA + `Referer: https://weibo.com/`）**：
   >   返回 **HTTP 200 + `ok:-100`** 说明接口可达、只是没登录 → 定性为**凭据问题而非网络问题**；
   >   若连 200 都拿不到（超时 / 5xx）才是网络问题。
   >   ⚠️ 不要再拿 `ajax/side/hotSearch` 当「站点可达」的判据 —— 2026-10-05 实测它带 UA 也返回
   >   **`HTTP 403`**，会被误读成网络故障，白排查一轮（它以前返回 `ok=1`，属于端点自身策略变化）。
   >
   > **结论：读浏览器 cookie 库是死路，但 CDP 是活路 —— 见下方「自动取 SUB（CDP 方案）」。**

   ### 自动取 SUB（CDP 方案）

   **2026-09-28 实测可行，`scripts/cdp_get_sub.py` 已实现。** 思路：不去解密 cookie 库，
   而是用 CDP（Chrome DevTools Protocol）的 `Network.getAllCookies` 命令
   **让浏览器自己把明文 cookie 交出来**——这是内核级 API，**不受 HttpOnly 限制**
   （HttpOnly 只挡页面 JS 的 `document.cookie`）。正好绕开 ABE 加密与 profile 独占锁。

   | 事实 | 实测结果 |
   |---|---|
   | CDP 能否读到 HttpOnly cookie | ✅ **能**。实测读到 `SUB domain=.weibo.com len=94`、`SRT`、`WBPSESS` 等 9 条 HttpOnly |
   | 是否受 ABE 加密阻碍 | ❌ 不受。CDP 返回的是浏览器解密后的明文值 |
   | 是否需要人类介入 | **首次需要**：得先用**独立 user-data-dir** 开一个 Edge 并在里面登录一次微博 |

   ```bash
   "$PY" scripts/cdp_get_sub.py probe                      # 探测端口是否可用
   "$PY" scripts/cdp_get_sub.py grab  --port 9222          # 抓取 + 登录校验（不写文件）
   "$PY" scripts/cdp_get_sub.py grab  --port 9222 --write  # 抓取 + 写回 wb_cookie.json
   ```

   #### ⚠️ 前提：**必须用独立 user-data-dir，不能复用日常 Edge 的默认 profile**

   > **先做一次引导检查（省时间，别跳过）**：CDP 路径不是开箱即用的，得先有那个独立 profile。
   > ```bash
   > ls -d "C:/Users/shana/EdgeWeibo"   # 不存在 → CDP 必然不可用，不要再 probe 第二遍
   > ```
   > 2026-10-05 实测：该目录**不存在**（主人从未创建过），因此 `probe` 报 `WinError 10061`
   > 拒绝连接是**预期结果**，不是脚本坏了。此时唯一可走的是手工 F12 抄 SUB，
   > 应当**立即收尾报告并明确请主人创建一次该 profile**（无人值守场景尤其不要在此空转）。

   2026-10-05 实测（Edge 154）钉死的两条硬约束，**照下面这条命令做才有效**：

   ```bash
   # ✅ 正确：独立 profile 目录，首次开出来手动登录一次微博，之后长期可用
   "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
     --user-data-dir="C:/Users/shana/EdgeWeibo" --remote-debugging-port=9222
   ```

   | 做法 | 结果 | 原因 |
   |---|---|---|
   | 默认 profile + `--remote-debugging-port` | ❌ **端口根本不开**（`WinError 10061`），进程正常起来但无调试接口 | **Chrome/Edge 136+ 起，出于防 cookie 窃取的考虑，禁止在默认 user-data-dir 上启用远程调试**。看起来像「参数没生效」，实为内核级拒绝——这就是 09-28 记的「默认 profile 不生效」的真实原因 |
   | 复制默认 profile 到临时目录 + 调试端口 | ❌ **返回 0 条 cookie**（或只有零星非加密的） | 默认 profile 的 cookie **888/888 全部是 ABE `v20` 密文**（`hex(encrypted_value)` 前缀 `7632`）。ABE 密钥绑定原始 user-data-dir 路径，换目录后浏览器自己也解不开，**解密失败的 cookie 被内核直接丢弃**（不是报错，是静默消失） |
   | 独立 user-data-dir + 调试端口 | ✅ 可用 | 非默认目录不受上述限制，且该 profile 的 cookie 由它自己加密/解密 |

   > ⚠️ **所以「复制 profile 再让浏览器自己解密」这条旁路是彻底死的**——此前只在
   > 「profile 被独占锁住、复制不出来」这一层失败（09-20），现在即使 Edge 完全没在运行、
   > 复制顺利成功，也会因 ABE 绑定路径而拿不到任何 cookie。别再试第三次。

   > ⚠️ **CDP 不是「关掉 Edge 重启一次」就能用**：必须落在**独立 profile** 上，且该 profile
   > 里要有一次人工登录。好处是**登录一次就长期有效**，此后 `grab --write` 全自动续期，
   > 不用解密、不用 F12 手抄。若该 profile 的登录态也失效了，仍需在里面重新登录微博一次
   > ——**自动取数解决的是「取」，不解决「为什么失效」**。
   >
   > 另外：`--headless=new` 与真实 profile 组合会**以无窗口方式占用默认 profile**，
   > 若此时主人自己打开 Edge，窗口会挂到这个无头实例上（看不见页面）。**用完要立刻
   > 按命令行匹配 `remote-debugging-port=9222` 精确终止该实例**，别留着。

   **三个已踩的坑（都已在脚本内修掉，别再重蹈）：**

   1. **本机代理会吞掉回环请求。** 环境有 `HTTP_PROXY=http://127.0.0.1:54077` 时，
      `urllib` 请求 `127.0.0.1:9222` 返回 **`HTTP Error 502: Bad Gateway`**，
      看起来像「端口没开」，极易误判成实例没启动。
      **必须用 `ProxyHandler({})` 绕开代理**（`curl` 则加 `--noproxy '*'`）。
      裸 `socket` 同样要自建而不走 `create_connection`。
   2. **`webSocketDebuggerUrl` 可能不含端口号。** 实测 Edge 153 返回
      `ws://127.0.0.1/devtools/page/XXX`（没有 `:9222`）；若 fallback 到 80 端口会
      `ConnectionRefused`，**表现和「实例挂了」一模一样，白排查很久**。
      脚本已改为用已知调试端口补全（`default_port` 参数）。
   3. **CDP 的 wsUrl 是短时效的。** 页面导航/回收后旧 URL 立即失效 → 脚本的重试逻辑
      必须**重新取 target**，不能缓存 URL 复用。

   > 结论：**这是当前唯一不依赖人手抄 SUB 的自动化路径**，前提是主人接受
   > 「让 Edge 带调试端口重启」这一步。若不接受，仍走上面的手工 F12 流程。


2. **无需额外 Python 依赖**，脚本仅使用标准库。

## Tool Paths

使用管理版 Python 运行脚本：

```bash
PY="C:/Users/shana/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SKILL="C:/Users/shana/Documents/GitHub/MyE-C-skill/weibo-figure-intel"
# 精抽产物：把日期换成当天，后续所有命令统一用它
INTEL="$SKILL/data/intel-$(date +%F).json"
```

| 文件 | 作用 |
|---|---|
| `scripts/weibo_fetch.py` | 校验登录态、拉取关注列表、按账号抓取微博增量、SQLite 去重；长文微博自动经 `ajax/statuses/longtext` 补抓全文（`--no-fulltext` 关闭） |
| `scripts/prefilter.py` | 用 `scripts/lexicon.json` 打分粗筛，输出候选情报。**空评论转发**（`转发微博`/纯 @）不再整体丢弃：打分本就计入原博文本，总分与 `require_any` 达标即按 `passed_by=keyword-rt` 放行（2026-09-18 起，此前连续两轮出现「原博是开订/预售公告、转发者只 @ 几个人」被误杀、需人工补录） |
| `scripts/assemble_intel.py` | 把精抽草稿组装成规范 intel JSON：**`url`/`blogger`/`posted_at` 按 `post_id` 自动填充**，并拦截未定义字段与非法枚举 |
| `scripts/attach_media.py` | 给情报条回填配图 `images[]`（本地库离线匹配 + 一致性校验），`--download` 抓图到 `output/media/` |
| `scripts/build_digest.py` | 校验结构化情报 JSON，渲染 Markdown + HTML 简报。**新品判定（`is_new`）、同款合并（`dedupe_items`）、新品清单视图**都在这里，见「新品判定规则」一节 |
| `scripts/build_index.py` | **跨天总览页生成器**：把 `data/intel-*.json` 里所有日期合成**一个** HTML，顶部带日期切换器。渲染层直接 `import build_digest`，卡片样式与判定规则永远一致。详见「总览页」一节 |
| `scripts/publish_daily.py` | **发布到 GitHub Pages**（2026-09-30 新增）：当日 HTML/MD + 页面引用到的缩略图 → 独立 public 仓 `lyt3905/figure-intel`，维护固定入口 `index.html`（永远最新）与 `archive.html`，然后 commit + push。**原图 `media/view/` 一律不发布**。详见「第 5.7 步」 |
| `scripts/lexicon.json` | 手办情报词库与权重，**主要调优入口** |
| `scripts/cdp_get_sub.py` | **CDP 自动取 SUB**（2026-09-28 新增）。通过远程调试端口让浏览器交出 HttpOnly 的 `SUB`，绕开 ABE 加密与 profile 锁。子命令 `probe` / `grab`，`--write` 直接写回 `wb_cookie.json`。仅用标准库 |
| `scripts/watchlist.json` | 白名单 / 黑名单账号 UID |
| `references/intel-schema.md` | 精抽输出的字段定义与判定口径 |

## Workflow

### 第 1 步：确认登录态

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" login-check
```

返回 `登录态有效  账号=<昵称>  关注=<N> 人` 则继续。若报未通过登录校验，说明 Cookie 已过期
或取错了 Domain（见前置条件），提示用户重新获取 `SUB` 并写回 `scripts/wb_cookie.json`，
**不要重试超过一次，也不要去翻浏览器的 cookie 库**（原因见前置条件的「Cookie 失效时不要试图
从浏览器 cookie 库自动提取」）。

> 这一步是**全流程的唯一硬前置**：失败则采集、粗筛、精抽、简报全部无从谈起，没有任何降级产物。
> 定时任务场景下，此时应当**立即收尾并明确报告**（Cookie 已失效 + 重取步骤 + 本地已缓存多少条微博），
> 不要反复重试刷接口。历史进度可用 `weibo_fetch.py stats` 查看（已见微博 / 已扫描账号数），
> 重取 Cookie 后增量机制会自动接上，不会丢数据。
>
> 报告时**一并给出「CDP 自动续期通道是否已就绪」**（`ls -d "C:/Users/shana/EdgeWeibo"` 有 / 无），
> 这样主人两条路一次看清：要么临时抄一次 SUB，要么把独立 profile 建起来一劳永逸。

### 第 2 步：采集（首次需先拉关注列表）

首次运行：

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" pull-following
```

产出 `data/following-YYYY-MM-DD.json`，含关注总人数与每个账号的昵称、简介、粉丝数。
**把总人数回报给用户**，据此决定走白名单模式还是全量模式：

| 关注人数 | 单轮耗时（2–4 秒间隔） | 建议 |
|---|---|---|
| 200 以内 | 约 7–13 分钟 | 全量秒扫，无需白名单 |
| 500 左右 | 约 17–33 分钟 | 配合黑名单瘦身 |
| 1000+ | 半小时以上，风控风险高 | 走 `--list whitelist` |

日常增量采集：

```bash
# 全部关注账号（关键词筛）
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --pages 1

# 仅白名单账号（免关键词筛）
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --list whitelist

# 首轮试跑，限制账号数避免触发风控
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --max-accounts 5
```

增量由**客户端**按 `post_id` 单调递增判断（该接口不支持服务端 `since_id`，传了会被忽略）：
脚本对每个账号取第 1 页，丢弃不比 `last_post_id` 新的微博；若整页都是新的则继续翻页，
直到出现旧微博为止。产出 `data/candidates-<时间戳>.json`。

关注人数多时**分批跑**（每次 `--max-accounts 100~150`），跑完再看下一批。
每轮结束用 `stats` 查看本地进度：

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" stats
```

### 第 3 步：粗筛

```bash
"$PY" "$SKILL/scripts/prefilter.py" --max-age-days 14 --preview 10
```

产出 `data/filtered-<时间戳>.json`。常用开关：

- `--max-age-days 14`：丢弃早于 N 天的微博。**首次全量抓取必加**——每个账号的第 1 页
  可能横跨一年以上，不加会把陈年旧博混进简报；日常增量跑时可省略
- `--show-dropped`：列出被丢弃的微博及原因，用于判断词库是否需要补词
- `--no-dedupe`：关闭同源转发去重（默认开启）。同一条原博被多个账号转发时只保留
  评论最长的一条，其余账号名记入 `also_reposted_by`，避免同一则公告重复入简报

### 第 4 步：精抽（由 agent 完成，不调外部 API）

读取 `data/filtered-*.json`，按 `references/intel-schema.md` 的字段定义逐条抽取，
**先写成草稿 spec，再由脚本组装**为 `data/intel-YYYY-MM-DD.json`（见下方）。要点：

- 严格遵循 `intel_type` 枚举，不要自造类型
- 原文没有的价格 / 发售日留空，不要推测
- 一条微博含多个产品就拆成多条
- 只有"敬请期待"这类无实质信息的不要输出
- `relevance` 按 62 店选品视角判定，高相关度的补 `relevance_reason`
- 转发（`is_repost=true`）且原博才是情报主体的：**不要 override `blogger` / `url`**。
  采集数据里 `retweeted` 只有 post_id / author / text / pics，**没有原博链接与时间**，
  手写 blogger 会与 url 对不上、触发 attach_media 的「来源存疑」告警。保留自动填充
  （blogger/url 指向捕获到的转发帖），原博作者写进 summary（如「原博 @XXX 公布…」），
  点开链接即见原博内容。（2026-09-18 约定；若日后 scan 把 `retweeted.url` /
  `retweeted.created_at` 一并落库，可再放开手写归因）
- 若带 `also_reposted_by`，可在 `summary` 末尾补一句"另有 X 家账号转发"

**不要手写 `url` / `blogger` / `posted_at`。** 先把内容字段写成一个「草稿 spec」
（JSON 数组，每条必须有 `post_id`），再交给脚本组装——这三个字段会从原始采集数据里
按 `post_id` 取，从流程上杜绝手抄错误：

```bash
"$PY" "$SKILL/scripts/assemble_intel.py" \
  --source "$SKILL/data/filtered-YYYYMMDD-HHMMSS.json" \
  --spec   "$SKILL/data/_spec_YYYYMMDD.json" \
  --out    "$INTEL"
```

草稿 spec 只写内容字段，例如：

```json
[{ "post_id": "5343320952014745", "intel_type": "实物测评", "brand": "塞伯世界",
   "ip": "变形金刚", "summary": "……", "relevance": "高",
   "relevance_reason": "变形玩具，62 店主类目", "tags": ["变形金刚"] }]
```

脚本会拦下这些错误（直接报错退出，不静默放行）：未定义的字段名（历史上的 `ip` 误打成
`iv` 就是被静默丢弃的）、`post_id` 在源文件里找不到、`intel_type` / `relevance` 不在枚举内、
必填字段缺失。转发类情报要写原博作者时，显式给 `blogger` + `url` 覆盖即可，脚本会提示
哪些被手写覆盖，便于复核。

> ⚠️ `url` 的 uid 段取自博文的 `user.idstr`。**关注列表接口返回的 `uid` 取的是 `user.id`，
> 部分账号两者不同**（2026-09-15 实测：某账号 `id`=5490307047、`idstr`=1538683825 是同一人）。
> 所以看到「url 里的 uid 和候选里的 uid 不一致」**不要改**——经回连核实，URL 用 `idstr`
> 是正确的，改了反而会错。

### 第 4.5 步：回填配图（可选但推荐）

```bash
# 只回填 images[] 字段（离线，秒级）
"$PY" "$SKILL/scripts/attach_media.py" --input "$INTEL" --dry-run

# 回填并抓图到 output/media/{thumb,view}/
"$PY" "$SKILL/scripts/attach_media.py" --input "$INTEL" --download
```

**默认全离线**：scan 阶段已把微博原文（含 `pics` / `retweeted.pics`）落进
`data/candidates-*.json` 与 `data/wb_state.sqlite`，因此回填不打任何网络请求。
只有 `--remote` 打开后，本地找不到的条目才会回连微博 show 接口兜底。

匹配走三级（url → mblogid → blogger+时间），url 命中后还会**核对博主与时间是否一致**——
历史上出现过精抽时手抄 URL 串行、12 条指向别人微博的情况，一旦对不上就改用
`blogger+posted_at` 重新定位并在结尾报告「来源存疑」清单。看到该提示要回写正确 URL 再重跑。

`--download` 会抓两类图（已存在的自动跳过，10 并发约 40 张/秒）：

| 目录 | 尺寸档 | 张数 | 用途 |
|---|---|---|---|
| `output/media/thumb/` | `/orj360/`（约 15KB） | 每条第 1–3 张 | 行内缩略图，被 base64 内嵌进 HTML |
| `output/media/view/` | `/orj960/`（约 70KB） | 全部 | 点缩略图放大预览 |

### 第 5 步：生成简报

先校验再生成：

```bash
"$PY" "$SKILL/scripts/build_digest.py" --input "$INTEL" --validate-only
# 默认同时产出 .md 与 .html
"$PY" "$SKILL/scripts/build_digest.py" --input "$INTEL"
# 只要其中一种
"$PY" "$SKILL/scripts/build_digest.py" --input "$INTEL" --format html
```

生成后会打印本地图片到位情况（`配图：N 条带图，本地 media/view 已有 M 张`），
若 M 明显小于应有张数，补跑一次 `attach_media.py --download`。

> 脚本对每张图**失败会自动重试 3 次并退避**（走代理时图床常见瞬时 502，同一 URL
> 隔一秒重试即成功）。但仍可能有零星缺口，**补跑是安全的**——已下载的会跳过，
> 只补失败的那几张，不会重下一遍。

产出 `output/手办情报-YYYY-MM-DD.html` 与 `.md`。**用 `present_files` 把 HTML 排在
第一项**展示给用户——它在内置浏览器面板里可直接预览，点卡片底部按钮即跳转原博。
若用户明确只要某一种格式，用 `--format md|html|both` 控制。

两个可选开关：

| 开关 | 作用 |
|---|---|
| `--data-dir <目录>` | 指定情报存档目录（默认 `data/`），用于判定「本日新出现」 |
| `--no-first-seen` | 关闭历史比对：不标新出现，页面也不出现未读组件 |

> 💡 首次生成或改动过渲染层（`build_digest.py`）后，**先按下面「本地验证」一节自检**，
> 确认缩略图、放大预览、筛选、未读标记都正常再交付；同时按「单日简报顶部」一节末尾的
> 循环**重刷所有已存在的日页**，别让新旧版式混在一份 archive 里。

#### 日期时间线（顶部「上一期 / 下一期」）

单日简报顶部会渲染一条**日期时间线**（2026-10-05 新增，2026-10-06 定为**日期下拉**）：
`‹ 10-03` · **日期下拉**（`<select class="dn-sel">`，选项 `MM-DD 周X`，当前期后缀「今天」）·
`10-05 ›` · `第 N / M 期` · `全部日期 →`。目标是**读完一天直接翻到相邻一天**，不必回总览页再点一次。

- **为什么是下拉而不是平铺胶囊**：胶囊条要横滑、独占一整行，头部就压不到两排
  （2026-10-06 试过胶囊版，当天即改回下拉）。
- 键盘 `[` / `]` 翻上一期 / 下一期（搜索框、下拉聚焦时不抢键；放大预览开着时让给左右翻图）。
- 到头的一侧渲染成灰掉的 `最早` / `最新`，不可点。
- 窄屏（≤640px）自动收敛：隐藏星期、键盘提示与「第 N / M 期」，只留 `‹ 10-03` / 下拉 / `10-05 ›`。
- 时间线**位于头部第 2 排**，与搜索框、视图切换并列（见下「单日简报顶部：两排 + 下滚收起」）。

| 开关 | 默认 | 作用 |
|---|---|---|
| `--day-link` | `手办情报-{date}.html` | 日页链接模板，`{date}` 占位。**发布站必须传 `{date}.html`** |
| `--day-index` | `手办情报-总览.html` | 时间线右侧的归档 / 总览页链接（传空字符串可隐藏） |
| `--day-index-label` | `全部日期 →` | 上面那个链接的显示文字（发布站用 `全部日期 →` → archive.html） |
| `--day-source` | `data/` | 扫描可用日期的目录。**发布站传发布仓目录**，按实际已发布的 HTML 算 |
| `--no-daynav` | 关 | 完全不渲染时间线（老版式回归用） |

> ⚠️ 日期清单是**扫目录**得到的，不是「今天减一天」推算的：某天断采（如 `2026-10-04` 没出简报）
> 时那天空缺不会被算进去——`10-03` 的下一期直接落到 `10-05`，不会点出一个 404。
> 发布站上还有一层保护：`--day-source` 指向发布仓，只有**真的已发布**的日期才会进时间线。

### 单日简报顶部：两排 + 下滚收起（2026-10-06 主人反馈「顶部占据的部分太长」）

单日页头部曾堆到 **5 排 ≈290px**（时间线 / 大标题 / 统计 chips / 视图切换 / 搜索）才见正文，压成两排：

| 行 | 内容 |
|---|---|
| 行 1 `.toprow` | 标题 `手办情报 · MM-DD 周X`（比原大标题矮一档）+ 来源说明 + 📬 未读胶囊 + `共 N 条 · 新品 N · 高相关 N` |
| 行 2 `.toolbar` | 时间线（`‹` + 下拉 + `›` + `第 N/M 期` + `全部日期 →`）+ 搜索框 + 视图切换 + 计数 |
| `.filterbar`（按需） | 类型 / 相关度筛选条，**只在「全部情报」视图出现**（CSS `.view-new .filterbar{display:none}`），默认视图零占位 |

- 类型分布数字（`类型 N`）也只在「全部情报」视图显示（`data-only-view="all"`），
  「生成于 …」挪到页脚 legend —— 头部只留三个最常看的数字。
- **下滚收起顶栏**：与总览页同一套手势（`.top.hide{translateY(-100%)}`、位移阈值 4px、
  顶部 160px 内不收起），但**顶栏内有焦点时不收起**——主人正在搜索 / 选日期，顶栏滑走会打断输入。
  `check_ui.js` 已加两条断言（下滚收起 / 上滚回来）钉住这个行为。
- 窄屏：≤860px 数字换行 + 视图切换全宽；≤640px 标题再缩一档、下拉限宽 130px。
- 改完**必须重刷所有已存在的日页**（本地 archive 与发布仓各刷一遍），否则新旧版式混在一起：

```bash
for f in data/intel-????-??-??.json; do
  "$PY" "$SKILL/scripts/build_digest.py" --input "$f"
done
"$PY" "$SKILL/scripts/build_index.py"
"$PY" "$SKILL/scripts/publish_daily.py" --rebuild-all   # 发布仓一次性重刷 + push
```

> 重刷是幂等的：实测 21 期重跑后「共 N 条情报」与旧页逐期完全一致（2026-10-06），
> 所以可以放心用它给历史期统一版式。

### 第 5.5 步：刷新总览页（跨天单页）

单日简报是「一天一个文件」，想横向对比几天就得开好几个页面。总览页把 `data/intel-*.json`
里**所有日期合成一个 HTML**：顶部一条日期切换器，点某天只看那天，点「全部」看累计。

```bash
# 全量（推荐，每天跑完单日简报后顺手刷新一次）
"$PY" "$SKILL/scripts/build_index.py"

# 只收最近 7 天，页面更轻
"$PY" "$SKILL/scripts/build_index.py" --days 7
```

产出 `output/手办情报-总览.html` 与 `手办情报-总览.md`。交付时**把总览页排
`present_files` 第一项**（它是横向浏览的主入口），单日简报跟在其后。

三视图（顶部一键切换）：

| 视图 | 内容 |
|---|---|
| **🆕 新品清单**（默认） | 跨天累计的新品，同一款产品在不同天被多次报道的**合并成一张卡**，卡上标注 `📅 首次日期 → 最新日期` |
| 全部情报 | 跨天合并后按类型分组，含实物测评、展会等全部类别 |
| 按天浏览 | **一天一节**、日期倒序；每节标题带「N 条情报 · 其中新品 M 件」，右上角按钮可直达当天的独立简报；切到此视图会出现一条**日期快速导航条**（吸顶） |

日期切换器与视图、类型、相关度、搜索**可以叠加**：例如「新品清单 + 点 09-21」=
只看 9 月 21 日那天出现的新品。计数会实时显示「显示 N / N 条」。

## 总览页（`build_index.py`）

### 顶部区域：紧凑折叠（2026-09-26 主人反馈「顶部太长、遮挡」）

初版把标题 / 统计 / 日期条 / 视图切换 / 搜索 / 类型 / 相关度全摊在顶栏里，实测
**顶栏 318px、视口 803px —— 占了 40%**，正文基本被挤没了。改成两层结构：

| 层 | 内容 | 高度 |
|---|---|---|
| `.topbar` 常驻行 | 标题 + 一行摘要 + **横向滚动的日期条** + 「筛选▾」 | — |
| `.expand` 展开区 | 统计 chips / 视图切换 / 搜索 / 类型 / 相关度 | — |

| 状态 | 顶栏高度 | 占视口 |
|---|---|---|
| 改前（全摊开） | 318px | 40% |
| **收起（默认）** | **44px** | **5.5%** |
| 展开（点「筛选」或按 `/`） | 171px | 21% |

配套两条交互：

- **下滚隐藏 / 上滚出现**：`.top` 加 `translateY(-100%)` 收起，同时 `.mini` 极简条
  （只有日期 + 筛选按钮）贴顶出现。**展开区打开时不收起**——否则会打断正在进行的筛选操作。
  用 `requestAnimationFrame` 节流，位移阈值 4px，顶部 120px 内不隐藏。
  日期条渲染两份（常驻行 + 极简条），点击时靠 `data-day` 双向同步选中态。
- **`/` 先展开再聚焦搜索框**：搜索框默认藏在展开区里，直接 `q.focus()` 会聚焦到不可见元素，
  所以要先 `setExpand(true)` 再 focus。Esc 收起展开区（搜索框自身的 Esc 清空仍归 `build_digest`）。

> ⚠️ 顶栏压扁后要**给正文补间距**：原来靠顶栏自身的大 padding 撑视觉呼吸感，
> 现在由 `main{padding}` 与 `.newhead / .group h2` 的 margin 自己给，
> 否则分组标题会直接贴住第一张卡片。

### 两个关键设计决策（踩坑后钉死，别改回去）

**① 缩略图不内嵌 base64，走 `media/` 相对路径。**

单日简报一天 ≈20 张卡，把缩略图 base64 内嵌换来「单文件也有图」，划算（80KB 图 → 35KB 文本）。
但总览页是**跨天累计**：13 天 1045 张卡、2233 个缩略图槽位，同样的做法直接顶到 **80.3 MB**，
浏览器打开要卡好几秒、滚动掉帧。

实测拆分（2026-09-26）：

| 项 | 数值 |
|---|---|
| 内嵌 base64 总体积 | 78.2 MB / 页面共 80.3 MB |
| 唯一图片数 | 780 张（却内嵌了 2233 次——三视图各渲染一份 DOM） |
| 平均每张 | 35.9 KB |
| **改走相对路径后** | **2.7 MB（↓ 30 倍）** |

总览页本来就必须连 `media/` 目录一起交付（放大预览走 `media/view/`），媒体目录无论如何都要给，
缩略图就没必要内嵌。`attach_media_paths()` 会临时替换 `build_digest.thumb_src`，
**只影响总览页**，单日简报行为不变。

取图顺序：`media/thumb/<name>`（15–30KB）→ 没有就退到 `media/view/<name>`（70KB）→ 都没有才外链。
日更时 `attach_media.py` 只给每条前 3 张下 `thumb/`，所以**绝大多数图只有 `view/`**，
这个 fallback 是必需的（实测 2560 张图里只有 886 张有 thumb）。
缩略图额外加了 `loading="lazy"`，否则一开页面就是 2000+ 个图片请求。

**② 日期筛选挂在 `build_digest` 的 `apply()` 上，不另起一套。**

`build_digest` 的 `apply()` 是闭包，现在通过 `window.__apply = apply` 暴露出来。
总览页的 JS 把 `apply` **包一层**：先跑原逻辑（类型 / 相关度 / 搜索 / 视图），
再叠加日期条件并重写计数。

> ⚠️ 教训：一开始总览页自己写了一套 `applyDay()`，用 `data-dayhidden` 标卡片，
> 结果 `build_digest` 的 `apply()` 根本不看这个标记，两边各算一遍、计数互相覆盖，
> 日期筛选**点了完全没反应**。**筛选链只能有一处入口**，要么包 `apply`，要么把日期并进
> `build_digest.match()`，绝不能各写一套。

### 计数口径（自检时对照）

| 视图 | 正确计数 | 含义 |
|---|---|---|
| 新品清单 | N / N，N = 跨天合并后的新品数 | 如 312 |
| 全部情报 | M / M，M = 跨天合并后的总条数 | 如 358 |
| 按天浏览 | D / D，D = 各天去重后卡片数之和 | 如 375（比 358 大属正常：跨天合并过的条目在每天各出现一次） |

三个视图各渲染一份 DOM，所以**总卡片数 ≈ 新品数 + 总数 + 按天数**（如 312+358+375=1045）。
计数用 `c.closest('.group-days')` / `.group-new'` 区分归属，只数当前视图那份。

### 跨天合并规则

复用 `build_digest` 的 `make_key` / `dedupe_items`：先按天各自去重，再把各天的同键条目并起来，
主卡取信息最全的一条，其余来源进 `also_sources`（卡片底部「另有 N 条报道」），配图取并集，
`_dates` 记录出现过的全部日期。

> ⚠️ 踩坑：`_dates` 必须在**两条分支都赋值**。只在「首次遇到该键」时赋值的话，
> 无法成键的 `solo` 条目（品牌缺失、或品牌有但角色/产品线是泛词）会完全没有日期，
> 实测漏了 **28 条**，表现是卡片上日期标记空白、且按天筛选时整条消失。

实测效果：13 天里 14 款产品跨天被重复报道而合并，如
布鲁可「擎天柱 Ver.EVO」09-15 → 09-21（3 次报道）、NA_NEWAGE「漂移」09-19 → 09-24。

### 第 5.7 步：发布到 GitHub Pages（固定网址）

把当日简报送上一个独立的 **public** 仓库 `lyt3905/figure-intel`（`scripts/publish_daily.py`），
用 GitHub Pages 对外提供固定入口。**发布仓与代码仓 `MyE-C-skill`（private）完全分离**，
互不影响。每天生成完简报后跑一次即可。

```bash
"$PY" "$SKILL/scripts/publish_daily.py"                    # 发布最新一天并推送
"$PY" "$SKILL/scripts/publish_daily.py" --date 2026-09-30  # 指定日期
"$PY" "$SKILL/scripts/publish_daily.py" --dry-run          # 只生成，不 commit/push
"$PY" "$SKILL/scripts/publish_daily.py" --rebuild-all      # 顺带重刷仓里全部历史期（补时间线）
"$PY" "$SKILL/scripts/publish_daily.py" --repo-dir D:/x    # 指定发布仓本地目录
```

发布脚本已接上「日期时间线」：日页链接按发布站命名（`{date}.html`）生成，`--day-source`
指向发布仓，所以线上翻页只会落在**真的已发布**的日期上；`archive.html` 每行也补了
`周X · 第 N 期 · N 条情报`，入口页 `index.html` 取 `max(已发布日期)`，即使 `--date`
指定了旧日期也不会把入口页倒退。

`--rebuild-all` 是给**历史期补版式**用的：重新渲染发布仓里已有的每一期（同一次 commit + push）。
渲染层改了样式 / 加了新组件（比如这次的日期时间线）后，跑一次就能让全部旧页与新版式对齐。
它**只重刷发布仓里已有的日期**，不会把没上线过的日期（例如本地有、线上从没发过的 09-12~09-29）
补上去——扩历史归发布范围，得单独决定（还要掂量缩略图体积）。

| 固定地址 | 内容 |
|---|---|
| `https://lyt3905.github.io/figure-intel/` | **固定入口，永远是最新一期**（收藏这一个） |
| `https://lyt3905.github.io/figure-intel/archive.html` | 历史归档（列出全部日期） |
| `https://lyt3905.github.io/figure-intel/YYYY-MM-DD.html` | 单期存档 |

#### 发布什么、不发布什么

| | 内容 | 理由 |
|---|---|---|
| ✅ 发布 | 当日 HTML/MD + **缩略图**（`media/thumb/`，去重后约 60~90 张） | 页面要能看图 |
| ❌ 不发布 | **原图**（`media/view/`，单日 30~40 MB） | 撑爆仓库；看大图交给原博 |
| ❌ 不发布 | `data/`、`wb_cookie.json` | 凭据与本地缓存 |

发布版由 `build_digest.py --publish` 生成，与本地版有两处差异：

1. **缩略图外链**（`media/thumb/<name>`）而非 base64 内嵌 —— HTML 由 **7.07 MB 降到约 210 KB**。
   顺带消掉一处隐性浪费：单日简报每张卡有「新品清单 / 全部情报」两份 DOM，内嵌时同一张图的
   base64 会被写两遍。
2. **点缩略图直接跳原微博**（`<a target="_blank">`），不再输出 `data-gallery` / 灯箱。
   灯箱模块的 JS 仍在（本地版用），但点击处理已改为「无图集就放行、不 preventDefault」，
   否则会把 `<a>` 的默认跳转吃掉。

> ⚠️ **踩坑（真浏览器才抓得到）**：`main()` 原本会把 `MEDIA_REL` 按「HTML 落地位置 → 本地
> media 目录」反推，正好覆盖掉 `--media-rel`，发布版图片被写成
> `../MyE-C-skill/weibo-figure-intel/output/media/thumb/...`，线上必然 404。
> 注意 grep 统计 `media/thumb/` 出现次数**完全看不出这个错**，因为错误路径里也含该子串。
> 已修：显式传 `--media-rel` 时不做反推。

体积参考（实测 2026-09-30）：HTML 211 KB + 缩略图 74 张 2.6 MB ≈ **2.8 MB/天**，
对比原方案的 40 MB/天；缩略图跨天去重，实际增速低于线性。

> ⚠️ **发布仓是 public**，拿到网址的人都能看。之所以和代码仓分开，就是为了让
> 「公开简报」与「私有 skill 代码」互不牵连。想下线：仓库 Settings → 删除仓库，
> 或在 Pages 设置里关掉站点。

### 第 6 步：回报与调优

汇报时包含：抓取账号数 / 新增微博数 / 通过粗筛数 / **新品件数** / 情报总条数 / 高相关条数 /
带配图条数 / 简报路径（HTML 与 MD 各一份）+ **总览页路径**。
展示结果时把**总览页 HTML 放 `present_files` 第一项**，单日简报跟其后。

`build_digest.py` 收尾会打印 `共 N 条情报`（合并后的条数），结合标题区
`其中新品清单 N 条` 即可取到这两个数。

若 HTML 与 `media/` 不在同一目录，预览会找不到图。同步到别处时用目录联接而不是复制
（省掉 ~68MB 重复占用）：

```powershell
New-Item -ItemType Junction -Path "<目标目录>\media" -Target "$SKILL\output\media"
```

根据用户反馈调优：

| 用户反馈 | 排查路径 |
|---|---|
| **漏了情报 / 漏了新品**（最高频） | 三级定位：①`prefilter.py --show-dropped` 查是否被粗筛丢 → 补 `lexicon.json` 词；②粗筛过了但不在 intel → 补精抽 spec 重跑 `assemble_intel.py`；③在 intel 但不在新品清单 → 扩 `build_digest.py` 的 `is_new()` 正则，详见「新品判定规则」 |
| **噪声多** | 把噪声账号 UID 加进 `watchlist.json` 的 `blacklist`，或提高 `threshold` |
| **某账号总被关键词漏掉** | 把其 UID 加进 `whitelist`，该账号免筛直通 |
| **同一款产品重复出现多次** | 检查 `dedupe_items()` 的成键规则，泛词是否该进 `_STOP_LINE`（见「同款合并」） |

> 效率提示：**只有第 ① 级需要重跑采集**。②③ 都是本地重算（`assemble_intel.py` /
> `build_digest.py` 秒级完成），不要为了补一条漏报去重抓一遍微博。

## 新品判定规则（`build_digest.py`）

新品清单的收录范围由 `is_new()` 决定，这是**调优的第一优先级**——用户投诉最多的是
「有新品被漏了」。判定分三档：

| 档位 | 判据 | 备注 |
|---|---|---|
| 主档（一定算） | `intel_type ∈ {新品公布, 开订, 发售, 再版}` | `NEW_TYPES` |
| 扩展：实物测评 | 命中 `FIRST_LOOK_PAT`（首度 / 首曝 / 大货实测 / 实物曝光 …）或 `FRESH_ACTION_PAT`（开箱 / 实测 / 实物 / 大货），**且未命中** `NOT_FRESH_PAT`（回顾 / 重温 / 情怀 / 老货 / 剧情） | 首度实拍本质就是新品露面 |
| 扩展：展会 | 命中 `EVENT_NEW_PAT`（特别发售 / 限量 / 限定 / 首展 / 现场售卖 / 推出 …） | 会场限定本身就是新面市产品 |

判定用的文本是 `summary + line + character + scale + channel` 的拼接（`blob`）。
`new_reason()` 会给扩展档的卡片打上「首次实物曝光」/「会场限定」角标。

**调优入口**：以上 `*_PAT` 正则与 `NEW_TYPES` 都集中在 `build_digest.py` 顶部
`# ---- 新品清单` 区块。改完**必须重跑**（纯渲染层，秒级出结果，不用重抓微博）：

```bash
"$PY" "$SKILL/scripts/build_digest.py" --input "$INTEL"
```

> ⚠️ 历史教训：扩宽 `is_new()` 时**宁可多收**。用户对"多收了无关内容"的容忍度远高于
> "漏了新品"——2026-09-17 那次漏报（FT-63 / NA 漂移 / TRANSBOTS 拦路虎等 7 条）就是
> 因为「实物测评」被整类排除在新品之外。

## 同款合并（`dedupe_items()`）

同一款产品被多个博主转发报道时，简报里会出现多张几乎一样的卡。合并规则：

- 归一键 `make_key(brand, character, line)` → `brand|character`，`character` 为空时
  退化为 `brand|line`；`_STOP_LINE` / `_STOP_SUBJECT` 里的泛词（"限定""特别版"等）不参与成键
- 保留信息最全的一条为主卡，缺失字段（价格 / 发售日 / 渠道 / 比例 / 角色）从其余条目补齐
- 配图取并集，其余来源在卡片底部渲染成「另有 N 条报道」可点击直达
- 键为空（品牌缺失、或角色/产品线都是泛词）的条目不参与合并，原样展示

实测效果：布鲁可擎天柱 Ver.EVO 由 4 条微博合成 1 张卡（「另有 3 条报道」），
千值练大师级攻略王由 2 条合成 1 张。

## 新增 / 未读（`mark_first_seen()`）

⚠️ **别把「新品」和「新增」搞混，这是两个独立口径：**

| 概念 | 字段 | 含义 | 用途 |
|---|---|---|---|
| 新品 | `is_new()` | 这条情报属于新品 / 开订 / 发售 / 再版（**与日期无关**） | 默认视图「🆕 新品清单」 |
| 本日新出现 | `_first` | 这款产品**在此前所有简报存档里都没出现过**（**与历史有关**） | 卡片上的「🆕 未读」+ 顶部未读条 |
| 已读 | localStorage | 用户在浏览器里实际看过了 | 读到即自动标记，未读数往下掉 |

一款老产品今天开订 → 算新品清单，但**不算**新出现；一条全新的展会限定 → 两者都算。

### 「本日新出现」怎么判：四条路，命中任意一条就算旧闻

历史索引来自 `data/intel-????-??-??.json`（严格只吃这个命名，跳过 `.bak` / `_spec`），
只取**早于当天**的存档。判定逐条走：

| # | 判据 | 举例 |
|---|---|---|
| ① | 合并键完全一致（`brand\|character`） | 「MegaHouse\|阿斯拉达01 赛道模式」 |
| ② | 同一条微博（`post_id`） | 同帖被不同账号转发 |
| ③ | 共享**有区分度**的型号编号 | `MPG-27` ≡ `MPG27` → 都是 `MPG27` |
| ④ | 同品牌 + 角色名互相包含（≥3 字） | 「传奇版 甲斗王 骑士形态」⊃「传奇版甲斗王」 |

**③ 是主力，也是踩过坑的地方**，三个必须保留的设计：

- **去连字符归一化**：`MPG-27` / `MPG27` / `DK-88W` / `DW-E58B` 每天写法都在变，
  不减掉连字符就成了两个身份，同一款产品天天被当成新品（实测：不减 → 38 条里标 36 条新；
  减掉 → 29 条，逐条核对全部正确）
- **文档频次过滤** `TOKEN_MAX_DF = 4`：`SS86`（产品线名）、`WF2026`（展会名）这类
  token 几百条里都有，拿来判「同一款」会把所有新品都误判成旧闻，超频次直接丢掉
- **必须含数字**：光靠连字符会误收 `PRE-ORDER` 这类英文词

**调优入口**：`_SPEC_TOKEN_PAT` / `TOKEN_MAX_DF` / `_text_axis()`，都在 `build_digest.py`
的 `# ---- 新增 / 未读` 区块。改完重跑单日简报即可（纯渲染层，秒级），无需重抓微博。

### 页面行为（`build_digest.py` 前端）

- 有「本日新出现」条目时才渲染未读组件；一条都没有 → 整个组件不渲染，JS 模块自动停用
- 卡片头部最前加 `🆕 未读`；读到后原地换成绿色 `✓ 已读`，卡片左侧出现淡绿内阴影
- 顶栏统计区最前是 **📬 未读 N** 胶囊（吸顶常驻，滚到哪儿都看得见未读数往下掉）
- 顶栏整体**下滚收起 / 上滚回来**（阈值同总览页：4px 位移、顶部 160px 内不收起；
  顶栏内有焦点时不收起），读正文时零遮挡
- 操作条三个按钮：`只看未读`（「只看未读」期间**暂停自动标记**，否则卡片一标已读就消失、
  下面的顶上来又被标读，会把整个列表连锁清空）、`全部标为已读`、`导出已读回执`
- **自动已读靠每秒一次的几何扫描**（`sweep()`）：卡片在视口安全区内稳定停留
  `DWELL = 2000ms` 后写入 localStorage（`wfir:read:v1`），最多保留 3000 条键。
  点标题 / 点「打开原博」立即标记，不必等停留
- ⚠️ **同一张卡在页面上有两份 DOM**（新品清单一份、全部情报一份），共用同一个 `ukey`。
  扫描必须**按去重键**判可见性（任一副本可见即可），不能按元素逐个判——
  隐藏副本 `getBoundingClientRect()` 全为 0，会把可见副本刚设好的停留计时器清零，
  导致自动已读**永不触发**（2026-09-30 踩过，结构上看完全正常）
- ⚠️ **「只看未读」的过滤条件必须判两项**：`c.dataset.first !== '1' || 有 .read`。
  只判 `.read` 会漏掉 `data-first="0"` 的旧闻卡 —— 它们既不算未读、也不会被标上 `.read`，
  筛完仍赖在列表里（实测 36 张里剩 9 张），**而 `#count` 照样在变，弱断言抓不到**。
  `check_ui.js` 已改为直接数可见卡，并断言「残留旧闻卡 = 0」「筛出数 ≤ 未读数」。
  （2026-09-30 修复：此前只断言「计数变了」，上线后才被真实浏览器发现）

### 跨天续接

`data/read-log.json`（可选，不入库）存在时会被烘焙进页面（`window.__READ_BAKED`）。
换浏览器 / 换打开方式后已读状态不通用，点「导出已读回执」拿到该文件放进 `data/` 即可续上。

## 调整词库

`lexicon.json` 结构：

- `weights`：各类别权重。`core` 4 / `brand` 3 / `line` 3 / `line_weak` 1 / `event` 2 /
  `scale` 1 / `ip` 1 / `negative` -6
- `threshold`：默认 3，总分达标才进入精抽
- `require_any`：除总分外还必须命中这些类别之一。作用是避免"今天买了个手办"这类
  只有泛词、没有实质信息的微博蒙混过关
- `terms.core`：手办 / 可动人偶等泛词
- `terms.line_weak`：`HG`/`MG`/`RG`/`PG`/`MP` 这类 2 字母代号。歧义大（`HG` 可能指
  高达，也可能是路由器型号），因此只给 1 分，单独命中不放行，需要配合其他类别才生效
- `terms.negative`：抽奖、招聘、带货等营销词，命中扣分。**负分只计一次，不随命中词数叠加**
  （2026-09-16 修正：此前按命中数翻倍，导致「开订公告 + 抽奖福利」被 抽奖+开奖 的双重负分压死，
  DLX 钢铁侠 Mark 1 开订因此漏报）

新增厂商或产品线时，优先加到 `brand` / `line`（权重高、判定准），不要加到 `core`。

## 本地验证（交付前自检）

简报是给人看的，**生成完必须亲眼看过再交付**。HTML 里字段名写错、图片没出来、筛选失效
这类问题脚本一律不报错（未知字段是静默忽略的），只有看图才发现得了。

### 1. 不需要起服务（默认走 `file://`）

⚠️ **本 skill 的常规运行不需要任何服务。** 交付环节用 `present_files` 展示即可——
WorkBuddy 会自己起内置预览面板，关掉即自动释放，不需要手动做任何事。

自检截图也**默认用 `file://` 直接打开**，本地图能正常加载（含放大预览，已实测）：

```bash
cp "手办情报-YYYY-MM-DD.html" _preview.html   # 先复制成 ASCII 名，中文名在 file:// URL 里要编码，容易出岔
```

> ⚠️ **截图副本一定要在 `$SKILL/output/` 里做**（该目录已被 `.gitignore` 忽略）。
> 2026-10-05 踩过一次：为了看发布版的排版，把副本放进了**发布仓**目录，随后
> `publish_daily.py` 的 `git add -A` 把它一起提交推到了 public 仓（临时文件进公开仓，
> 无敏感信息但很难看）。现在发布脚本每次都会重写发布仓的 `.gitignore`（忽略
> `_preview*.html` / `_*.png` / `_*.tmp`）兜底，但仍应在 `output/` 里截图。

只有当需要复现真实 HTTP 环境（调试跨域、Service Worker 之类）时，才临时起服务，
且**必须换一个高位端口**——8765 这类常见端口可能被 WorkBuddy 自身占用
（会返回 `404 application/json`），起了也白起：

```bash
cd "$SKILL/output" && "$PY" -m http.server 8912 --bind 127.0.0.1
```

起过服务的话，用完务必按第 4 节的方式停掉。

### 2. Edge 无头截图看排版

`agent-browser` 在本机会被 SIGTERM 打断，**改用 Edge 命令行截图最稳**：

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --headless=new --disable-gpu --no-first-run --hide-scrollbars \
  --window-size=1400,1500 --virtual-time-budget=20000 \
  --user-data-dir="<临时目录>" --screenshot="<输出.png>" \
  "file:///C:/<HTML 所在目录>/_preview.html"
```

（若已起了 HTTP 服务，把最后一行换成 `"http://127.0.0.1:8912/_preview.html"` 亦可。）

- `--virtual-time-budget=20000` 要给足，太小会截到图片还没加载完的空白
- 换 `--window-size=560,1100` 复检窄屏（缩略图折行、右栏转横排）
- 截完用 Read 工具看图，肉眼确认缩略图、标题链接、筛选条是否正常

### 3. 验证交互组件（缩略图放大预览 / 视图切换）

静态截图看不到点击后的状态。**往 HTML 注入一段自动点击脚本**再截即可：

```bash
"$PY" -c "
s = open('xxx.html', encoding='utf-8').read()
s = s.replace('</body>',
  '<script>setTimeout(function(){document.querySelector(\".thumb\").click();},600);</script>\n</body>', 1)
open('_lb.html', 'w', encoding='utf-8').write(s)"
```

对 `_lb.html` 截图，就能看到弹层、`1 / 18` 计数、左右导航是否正常。

**两个视图都要验**（默认是新品清单视图，注入点击切到全部情报视图）：

```bash
"$PY" -c "
s = open('_preview.html', encoding='utf-8').read()
inj = '<script>window.addEventListener(\"load\",function(){var b=document.querySelector(\"[data-view=all]\");if(b)b.click();});</script></body>'
open('_all.html', 'w', encoding='utf-8').write(s.replace('</body>', inj, 1))"
```

重点核对右下角计数：**新品视图应为「显示 N / N 条」（N = 新品件数），全部情报视图应为
「显示 M / M 条」（M = 情报总条数）**。两个视图各渲染一份 DOM（共 2N 张卡），
若计数出现「显示 N / 2N」说明卡片归属判定错了——归属靠 `c.closest('.group-new')`。

> ⚠️ **多行 Python 一律写成临时 `.py` 文件再执行，不要用 stdin heredoc。** 2026-09-17
> 踩坑：`"$PY" - << 'EOF'` 少写一个变量导致 fallback 分支启动**交互式 REPL**，
> 在无 tty 的无头环境里疯狂刷 `_pyrepl` 的 `OSError: [WinError 123]`，
> 2 分钟产出约 295MB stderr。用 `TaskStop` 才停掉。

**交互状态用 `--dump-dom` + `document.title` 回读，比截图靠谱。** 截图只能看个大概，
计数错了、点了没反应这类问题肉眼容易漏（也可能是我截图时机不对）。把结果写进 `title`，
再用 `grep -o` 捞出来，一次能验一整串状态：

```bash
# 注入：连点各视图 / 日期，把每步计数串成一行塞进 title
"$PY" -c "
s=open('_idx.html',encoding='utf-8').read()
js='''var out=[];
function snap(t){out.push(t+'='+document.getElementById('count').textContent.trim());}
snap('新品');document.querySelector('[data-view=\"all\"]').click();snap('全部');
document.querySelector('[data-view=\"days\"]').click();snap('按天');
document.querySelector('[data-view=\"new\"]').click();
document.querySelector('[data-day=\"2026-09-21\"]').click();snap('新品@09-21');
document.title='R::'+out.join(' | ');'''
open('_dbg.html','w',encoding='utf-8').write(s.replace('</body>','<script>window.addEventListener(\"load\",function(){setTimeout(function(){'+js+'},500);});</script></body>',1))"

"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu \
  --no-first-run --window-size=1200,800 --virtual-time-budget=20000 \
  --user-data-dir="<临时目录>" --dump-dom "file:///.../_dbg.html" 2>/dev/null | grep -o "R::[^<]*"
```

输出形如 `R::新品=显示 312 / 312 条 | 全部=显示 358 / 358 条 | ...`，一眼看出哪一步错了。

> ⚠️ 注入脚本**必须包 `setTimeout` 延时**（500ms 起）再点。2026-09-26 踩坑：
> 直接在 `load` 里立刻点，点击发生在页面自身初始化之前，结果截图里日期筛选
> 「看起来没生效」，实际是**测试脚本的时序问题**，白排查了两轮。

验证完删掉 `_lb.html` / `_all.html` / `_preview.html` / `_dbg*.html`。

### 3.5 交互功能自检：必须用真浏览器（`scripts/check_ui.js`）

⚠️ **无头 Edge 验不了交互。** 2026-09-30 实测：`--headless=new` 下
`IntersectionObserver` **一次回调都不派发**、`getBoundingClientRect()` **全为 0**（不做 layout）、
连 `window.scrollTo()` 都不触发 scroll 事件。所以第 2、3 节那些 `--dump-dom` 手段
**只能验结构与计数，验不了「读到即已读」这类交互**——当天就是它把「自动已读永不触发」
的 bug 放了过去，改用真浏览器才暴露。

用 Playwright 驱动本地已缓存的 Chromium 真跑一遍：

```bash
NODE_PATH="<node 工作区>/node_modules" node "$SKILL/scripts/check_ui.js"
# 也可指定文件：node scripts/check_ui.js --html output/手办情报-YYYY-MM-DD.html
```

它会依次断言：未读探针可读 → 首屏停留即自动已读 → 未读计数下降 → 两份 DOM 同步变已读 →
「只看未读」筛选生效 → 刷新后已读保留 → 「全部标为已读」清零 → 徽章文案只有两态 →
页面无 JS 异常；再确认总览页不出现未读组件、计数正常。
**退出码 0 = 全过，1 = 有项没过**，可直接串进流程。

- 找不到 `playwright-core` 时以退出码 **2 跳过**（不算失败），此时只能退回收第 2、3 节。
- playwright-core 只认自己那一版浏览器，版本号差一位就报 `Executable doesn't exist`；
  脚本会自动去 `ms-playwright` 缓存目录里挑一个可用的完整版 Chromium。
- 任何时候都能看页面状态：URL 加 `?probe=1`（如 `demo.html?probe=1`），
  页面会把 `R::未读=N/首现=M 已读键=K` 写进隐藏的 `#probe`，供 `--dump-dom` 或脚本读取；
  正常打开时不输出任何东西。

### 4. 收尾

- **若起过 HTTP 服务**：用 `TaskStop` 停，不要用外部 `Stop-Process` kill。外部 kill 会让
  面板留下「僵尸条目」，一直显示"已运行 XXmXXs"，而 `TaskStop` 事后又清不掉（报 `not found`），
  只能重启应用。⚠️ 面板上那个计时**不代表进程还在**——查 `tasklist` 和端口才是准的。
  **不起服务就没有这一节的烦恼，这也是默认走 `file://` 的原因之一。**
- 临时文件**用完即删**：截图目录 `_shots/`，以及复制出来的 `_preview.html` / `_lb.html` / `_all.html`。
  无头浏览器的 `--user-data-dir` 很占地方，实测跑一轮截图能到 99MB。
  省事写法：`rm -rf output/_shots output/_preview.html output/_all.html output/_lb.html`
- 这些临时文件不会污染 git——根 `.gitignore` 第 9–10 行把整个 `weibo-figure-intel/data/`
  与 `weibo-figure-intel/output/` 都排除了（**简报产物、抓取数据、媒体文件均不入库**，
  只有 `scripts/` / `references/` / `SKILL.md` 进版本控制）。但仍要删干净，别把乱糟糟的
  中间文件留在输出目录里影响主人翻看。

## 已知限制

1. **必须带登录 Cookie，且必须是 `.weibo.com` 域的那一行 `SUB`。** 实测（2026-09）：

   | 通道 | 无 Cookie | 带访客 Cookie | 带 `.sina.com.cn` 的 SUB | 带 `.weibo.com` 的 SUB |
   |---|---|---|---|---|
   | `m.weibo.cn` 时间线接口 | 432 | 432 | 未登录 | **未登录** |
   | `weibo.com` 桌面端 Ajax | 403 | — | `ok:-100` | **正常** ✅ |

   结论：**移动端接口对 `.weibo.com` 签发的 SUB 一律返回未登录**，因此脚本全部走
   `weibo.com` 桌面端 Ajax 接口，不要改回 `m.weibo.cn`。微博开放平台的
   `friends_timeline` 需要高级权限，个人开发者无法申请。

2. **`SUB` 有效期通常数月到一年**，失效表现为接口返回 `ok:-100` / `ok:0` / 401 / 403。
   脚本会明确报错而不静默失败。

3. **风控是主要风险。** 请求已内置 2–4 秒随机间隔与 10–20 秒退避重试。仍被限流时应缩小
   抓取范围、稍后重跑（增量机制会让脚本自动接着抓），不要连续硬刷。

4. **微博没有"关注流增量"接口**，只能逐个账号抓，单轮耗时 ≈ 关注人数 × 3 秒。
   且该接口的正序 `since_id` 参数无效，增量只能客户端比较 `post_id`。

5. **首次抓取会带回历史微博。** 每个账号第 1 页最多 22 条，可能横跨一年以上，
   必须用 `prefilter.py --max-age-days` 收敛时间窗口。

6. **接口不返回登录者自己的 uid。** `friendships/friends` 不带 uid 时即代表本人，
   这是身份识别的唯一依据；脚本因此不需要用户提供自己的 uid。

7. **长文微博**（`isLongText`）：列表接口（`mymblog`）和 `show` 接口都只给约 140 字截断摘要；
   全文要走 `GET https://weibo.com/ajax/statuses/longtext?id=<mblogid>`
   （响应 `data.longTextContent`）。**2026-09-16 起 `weibo_fetch.py` 已内置**：
   scan 时对新增长文自动补抓全文并回写 SQLite，每条多耗 2–4 秒，`--no-fulltext` 可关闭。
   补抓失败的条目保留摘要，精抽时若发现关键信息（价格/发售日）被 `…` 截断，可单独重跑
   `scan`（增量机制不会重抓旧微博，需用临时脚本按 mblogid 补抓）。转发的**原博**长文不补。

8. **微博图床防盗链会挡住本地 HTML 外链**（2026-09 实测）。`wx*.sinaimg.cn` 的判定逻辑是：
   只要请求带浏览器特征头（真实 Chrome/Edge UA + `Sec-Fetch-*`），Referer 不是 `weibo.com`
   域就直接 **403**；而空 UA 或带 `Referer: https://weibo.com/` 才放行。

   | 请求特征 | 结果 |
   |---|---|
   | 真实 Chrome UA + `Sec-Fetch-*` + 无 Referer | **403** |
   | 真实 Chrome UA + `Sec-Fetch-*` + `Referer: http://127.0.0.1:8912/` | **403** |
   | 真实 Chrome UA + `Sec-Fetch-*` + `Referer: file:///...` | **403** |
   | 空 UA（curl 默认） | 200 |
   | 带 `Referer: https://weibo.com/` | 200 |
   | 无头浏览器直接打开图片 URL | **403** |

   所以 `referrerpolicy="no-referrer"` 也救不了——浏览器一定会带 `Sec-Fetch-*`。
   **结论：必须下载到本地再引用**，这就是 `attach_media.py --download` 存在的原因。
   下载时脚本固定带 `Referer: https://weibo.com/`。

9. **尺寸档**：`/orj360/`≈15KB、`/orj960/`≈70KB、`thumbnail`≈3.4KB，均返回 `image/jpeg`；
   部分图 `/large/` 与 `/orj960/` 等价（原图本身不够大）。转档只需替换 URL 中的路径段。

10. **同一个账号可能有两个数值 uid**（2026-09-15 实测）。`friendships/friends`（关注列表）返回的
    `id` 与博文 `user` 对象里的 `idstr` 在部分账号上不同（实测一例：`id`=5490307047、
    `idstr`=1538683825，经 `ajax/statuses/show` 回连确认为同一人）。因此：
    `weibo_fetch.py` 存进候选的 `uid` 取 `id`，而 `url` 的 uid 段取 `idstr`，**两者不一致是正常的**，
    不必"修正"。回连核实的办法：`GET https://weibo.com/ajax/statuses/show?id=<mblogid>`，
    响应里的 `idstr` / `mblogid` / `user.screen_name` 三者对齐即可确认 URL 无误。

11. **未读状态存在浏览器 localStorage，换「打开方式」会失忆**（2026-09-30 实测）。
    已读记录键 `wfir:read:v1` 存在浏览器 Profile 里：`file://` 直开的本地文件**之间、
    跨进程共享且持久**（实测写入后两个全新进程都能读到），但以下情况不通用：

    | 打开方式 | origin | 已读状态 |
    |---|---|---|
    | 双击 HTML（`file://`） | `file://` | ✅ 持久，跨天跨文件共享 |
    | 内置预览面板（`http://127.0.0.1:<随机端口>`） | 每次端口都不同 | ❌ 视为新 origin，读不到 |
    | 换浏览器 / 换机器 | 不同 Profile | ❌ |

    兜底：页面「导出已读回执」→ 拿到 `read-log.json` → 放进 `data/` →
    构建时烘焙进页面（`window.__READ_BAKED`），任何打开方式都能续上。
    **自动化里不要去读浏览器的 localStorage**（Edge 运行中独占锁 Profile，且 127+ 用
    App-Bound Encryption，读不出来）——这也正是回执走「页面导出 + 落文件」的原因。

12. 仅供个人自用，不要把采集结果对外分发。

## 安全与凭据

- `scripts/wb_cookie.json` 含登录凭据，**不得提交到 git**，已在 `.gitignore` 排除
- 仓库内只保留 `wb_cookie.json.example` 作为格式示例
- 任何输出中不得回显完整 `SUB` 值，汇报时最多显示前 6 位
