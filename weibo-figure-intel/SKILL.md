---
name: 手办情报
description: |
  This skill collects Weibo posts from accounts the user follows and extracts intelligence
  about anime figures (手办) and action figures / articulated dolls (可动人偶) — new product
  announcements, pre-orders, release dates, re-releases, delays, exhibitions and photo reviews.
  It fetches posts with the user's Weibo login cookie, pre-filters them against a curated
  keyword lexicon, has the agent structure the surviving posts into intel records, and renders
  a Markdown digest grouped by intel type.
  Triggered when the user asks for 手办情报 / 可动人偶情报 / figure news, says things like
  "看看今天有什么手办情报", "微博上有没有新开订的手办", "抓一下我关注的手办号",
  "collect figure news from Weibo", or wants to tune the intel keyword lexicon.
agent_created: true
---

# 手办情报雷达（weibo-figure-intel）

## Purpose

从用户关注的微博账号中采集微博，筛出与动漫手办 / 可动人偶相关的情报，抽取成结构化
字段，产出按情报类型分组的 Markdown 简报。目标是将"刷微博找新品/开订信息"这一动作
自动化，服务于店铺选品。

## Trigger

触发场景：

- 用户问"有什么新的手办情报 / 可动人偶情报 / figure 新闻"
- 用户说"抓一下微博""看看我关注的手办号发了什么"
- 用户要调整词库、白名单、黑名单
- 用户反馈某条情报漏了或噪声太多

## 前置条件

1. **微博登录 Cookie**（必需）。存放于 `scripts/wb_cookie.json`，格式：

   ```json
   { "cookie": "SUB=xxxxx; SUBP=xxxxx" }
   ```

   获取方式：浏览器登录 weibo.com → F12 → Application/存储 → Cookies → `https://weibo.com`
   → 复制 `SUB` 的值。该文件已在 `.gitignore` 中排除，不会进入仓库。

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
| `scripts/build_digest.py` | 校验结构化情报 JSON 并渲染 Markdown 简报 |
| `scripts/lexicon.json` | 手办情报词库与权重，**主要调优入口** |
| `scripts/watchlist.json` | 白名单 / 黑名单账号 UID |
| `references/intel-schema.md` | 精抽输出的字段定义与判定口径 |

## Workflow

### 第 1 步：确认登录态

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" login-check
```

返回 `登录态有效` 则继续。若报 `Cookie 未通过登录校验` 或接口返回 432，说明 Cookie 已过期，
提示用户重新获取 `SUB` 并写回 `scripts/wb_cookie.json`，不要重试超过一次。

### 第 2 步：采集（首次需先拉关注列表）

首次运行：

```bash
"$PY" "$SKILL/scripts/weibo_fetch.py" pull-following
```

产出 `data/following-YYYY-MM-DD.json`，含关注总人数与每个账号的昵称、简介、粉丝数。
**把总人数回报给用户**，并按其判断决定走白名单模式还是全量模式。

日常增量采集：

```bash
# 全量关注流（关键词筛）
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --pages 1

# 仅白名单账号（免关键词筛）
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --list whitelist

# 首轮试跑，限制账号数避免触发风控
"$PY" "$SKILL/scripts/weibo_fetch.py" scan --max-accounts 30
```

脚本自动带 `since_id` 只取新增，产出 `data/candidates-<时间戳>.json`。
关注人数多时**分批跑**（每次 `--max-accounts 100~150`），跑完再看下一批，不要一次跑完上千人。

### 第 3 步：粗筛

```bash
"$PY" "$SKILL/scripts/prefilter.py" --preview 10 --show-dropped
```

产出 `data/filtered-<时间戳>.json`。`--show-dropped` 会列出被丢弃的微博及原因，
用于判断词库是否需要补词。

### 第 4 步：精抽（由 agent 完成，不调外部 API）

读取 `data/filtered-*.json`，按 `references/intel-schema.md` 的字段定义逐条抽取，
写入 `data/intel-YYYY-MM-DD.json`。要点：

- 严格遵循 `intel_type` 枚举，不要自造类型
- 原文没有的价格 / 发售日留空，不要推测
- 一条微博含多个产品就拆成多条
- 只有"敬请期待"这类无实质信息的不要输出
- `relevance` 按 62 店选品视角判定，高相关度的补 `relevance_reason`

先校验再生成：

```bash
"$PY" "$SKILL/scripts/build_digest.py" --input "$SKILL/data/intel-2026-09-12.json" --validate-only
"$PY" "$SKILL/scripts/build_digest.py" --input "$SKILL/data/intel-2026-09-12.json"
```

产出 `output/手办情报-YYYY-MM-DD.md`，用 `present_files` 展示给用户。

### 第 5 步：回报与调优

汇报时包含：抓取账号数 / 新增微博数 / 通过粗筛数 / 情报条数 / 高相关条数 / 简报路径。

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

1. **必须带登录 Cookie。** 访客 Cookie 方案已被微博封堵，`m.weibo.cn` 的
   `containerid=107603<uid>` 接口在无有效 `SUB` 时返回 432。
   微博开放平台的 `friends_timeline` 需要高级权限，个人开发者无法申请。
2. **`SUB` 有效期通常数月到一年**，失效表现为接口返回 432 / 403。脚本会明确报错而不静默失败。
3. **风控是主要风险。** 请求已内置 2–4 秒随机间隔与 10–20 秒退避重试。仍被限流时应缩小
   抓取范围、稍后重跑（增量机制会让脚本自动接着抓），不要连续硬刷。
4. **微博没有"关注流增量"接口**，只能逐个账号带 `since_id` 抓，因此单轮耗时 ≈ 关注人数 × 3 秒。
5. 仅供个人自用，不要把采集结果对外分发。

## 安全与凭据

- `scripts/wb_cookie.json` 含登录凭据，**不得提交到 git**，已在 `.gitignore` 排除
- 仓库内只保留 `wb_cookie.json.example` 作为格式示例
- 任何输出中不得回显完整 `SUB` 值，汇报时最多显示前 6 位
