---
name: 手办情报
description: |
  This skill collects Weibo posts from accounts the user follows and extracts intelligence
  about anime figures (手办) and action figures / articulated dolls (可动人偶) — new product
  announcements, pre-orders, release dates, re-releases, delays, exhibitions and photo reviews.
  It fetches posts with the user's Weibo login cookie, pre-filters them against a curated
  keyword lexicon, has the agent structure the surviving posts into intel records, and renders
  a digest grouped by intel type — both Markdown and a self-contained HTML file with
  clickable links back to the original Weibo posts.
  Triggered when the user asks for 手办情报 / 可动人偶情报 / figure news, says things like
  "看看今天有什么手办情报", "微博上有没有新开订的手办", "抓一下我关注的手办号",
  "collect figure news from Weibo", or wants to tune the intel keyword lexicon.
agent_created: true
---

# 手办情报雷达（weibo-figure-intel）

## Purpose

从用户关注的微博账号中采集微博，筛出与动漫手办 / 可动人偶相关的情报，抽取成结构化
字段，产出按情报类型分组的简报。目标是将"刷微博找新品/开订信息"这一动作自动化，
服务于店铺选品。

简报默认产出两种格式：

| 格式 | 用途 |
|---|---|
| `output/手办情报-YYYY-MM-DD.html` | **浏览器阅读**。单文件、无外部依赖，按情报类型分节，**每条情报独占一行**（左栏正文、右栏元信息与来源按钮）。支持关键词搜索与类型/相关度筛选，分组标题随筛选自动隐藏空组，每条带「打开原博」按钮直达微博原帖 |
| `output/手办情报-YYYY-MM-DD.md` | 存档、粘贴进对话、二次加工 |

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

2. **无需额外 Python 依赖**，脚本仅使用标准库。

## Tool Paths

使用管理版 Python 运行脚本：

```
PY="C:/Users/shana/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SKILL="C:/Users/shana/Documents/GitHub/MyE-C-skill/weibo-figure-intel"
```

| 文件 | 作用 |
|---|---|
| `scripts/weibo_fetch.py` | 校验登录态、拉取关注列表、按账号抓取微博增量、SQLite 去重 |
| `scripts/prefilter.py` | 用 `scripts/lexicon.json` 打分粗筛，输出候选情报 |
| `scripts/build_digest.py` | 校验结构化情报 JSON，渲染 Markdown + HTML 简报（HTML 自带搜索/筛选与原博链接） |
| `scripts/lexicon.json` | 手办情报词库与权重，**主要调优入口** |
| `scripts/watchlist.json` | 白名单 / 黑名单账号 UID |
| `references/intel-schema.md` | 精抽输出的字段定义与判定口径 |

## Workflow

### 第 1 步：确认登录态

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" login-check
```

返回 `登录态有效  账号=<昵称>  关注=<N> 人` 则继续。若报未通过登录校验，说明 Cookie 已过期
或取错了 Domain（见前置条件），提示用户重新获取 `SUB` 并写回 `scripts/wb_cookie.json`，
不要重试超过一次。

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
写入 `data/intel-YYYY-MM-DD.json`。要点：

- 严格遵循 `intel_type` 枚举，不要自造类型
- 原文没有的价格 / 发售日留空，不要推测
- 一条微博含多个产品就拆成多条
- 只有"敬请期待"这类无实质信息的不要输出
- `relevance` 按 62 店选品视角判定，高相关度的补 `relevance_reason`
- 转发（`is_repost=true`）且原博才是情报主体的：`blogger` 写**原博作者**
  （`retweeted.author`），`url` 用原博链接，`summary` 里可注明经谁转发
- 若带 `also_reposted_by`，可在 `summary` 末尾补一句"另有 X 家账号转发"

先校验再生成：

```bash
"$PY" "$SKILL/scripts/build_digest.py" --input "$SKILL/data/intel-2026-09-12.json" --validate-only
# 默认同时产出 .md 与 .html
"$PY" "$SKILL/scripts/build_digest.py" --input "$SKILL/data/intel-2026-09-12.json"
# 只要其中一种
"$PY" "$SKILL/scripts/build_digest.py" --input xxx.json --format html
```

产出 `output/手办情报-YYYY-MM-DD.html` 与 `.md`。**用 `present_files` 把 HTML 排在
第一项**展示给用户——它在内置浏览器面板里可直接预览，点卡片底部按钮即跳转原博。
若用户明确只要某一种格式，用 `--format md|html|both` 控制。

### 第 5 步：回报与调优

汇报时包含：抓取账号数 / 新增微博数 / 通过粗筛数 / 情报条数 / 高相关条数 / 简报路径
（HTML 与 MD 各一份）。展示结果时把 HTML 放在 `present_files` 的第一项。

根据用户反馈调优：

- **漏了情报** → 往 `lexicon.json` 的对应类别补词，重跑 `prefilter.py`（无需重新抓取）
- **噪声多** → 把噪声账号 UID 加进 `watchlist.json` 的 `blacklist`，或提高 `threshold`
- **某账号总被关键词漏掉** → 把其 UID 加进 `whitelist`，该账号免筛直通

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
- `terms.negative`：抽奖、招聘、带货等营销词，命中扣分

新增厂商或产品线时，优先加到 `brand` / `line`（权重高、判定准），不要加到 `core`。

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

7. **长文微博**（`isLongText`）只拿到摘要文本，完整版需要额外请求，当前不取。

8. 仅供个人自用，不要把采集结果对外分发。

## 安全与凭据

- `scripts/wb_cookie.json` 含登录凭据，**不得提交到 git**，已在 `.gitignore` 排除
- 仓库内只保留 `wb_cookie.json.example` 作为格式示例
- 任何输出中不得回显完整 `SUB` 值，汇报时最多显示前 6 位
