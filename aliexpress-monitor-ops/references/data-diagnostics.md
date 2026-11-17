# 数据核查：假新品 / 重复入库诊断

## 背景：一天的"新品"暴涨，多半是假象

2026-11-11 一次全量扫描报 `newCount=924`，用户直觉「不可能这么多」。核查后：**924 条里 873 条是老商品换了一套 item id 被重录，真新品只有 51 条**。

根因：**AliExpress 对同一件商品会给出两套数字完全不同的 16 位 item id**（前缀 `1005…` 与 `3256…`）。同一件商品在不同时间、不同店铺页面版本下，锚点 `href` 里的 `/item/<id>.html` 数字会变。而本项目去重键只有 `UNIQUE (shop_id, remote_product_id)`（`alimonitor\schema.py:338` + `alimonitor\services\products.py:126-129`），平台一换 id 形制，同一商品就被当新品 INSERT。

这不是"重装系统把统计搞错了"——DB 从首扫起连续无断；只是重装当天恰好碰上平台切到 `3256…` 形制，时间重合而已。历史上 8-27 首扫（3256）→ 9-14 起（1005）也发生过同类重录（run13 里 655 条同图孪生）。切勿把"重复"归因于重装。

## 判断口诀

- **`remote_product_id` 不可靠**：同一件有 `1005…` / `3256…` 多套 id。
- **真·同一件** = 同店铺 + 同主图（`/kf/<hash>`）+ 同标题。
- 店铺主图 URL 形如 `https://ae-pic-a1.aliexpress-media.com/kf/<hash>.jpg_350x350.jpg`；归一化取 `/kf/([^.?#/]+)` 去掉尺寸后缀。

## 量化（`alm.py db-dups`）

```
总行数 = 6350，唯一(店铺+图)组 = 4806  =>  冗余 1544 行
```
（清理后现为 5477 行 / 4806 组 / 冗余 671 行。）

手工 SQL（SQLite，只读打开）：
```sql
-- 今日入库 vs 同店铺同图的老孪生
SELECT count(*) FROM products WHERE date(first_seen_at,'localtime')=date('now','localtime');
-- 按 (shop_id, 主图hash) 分组找 >1 行的组
```
更稳的做法：`alm.py db-dups --show 20`。

## 清理步骤（务必先备份）

1. **备份**：`Copy-Item data\products.db backups\products-before-dedup-<时间戳>.db`。
2. 用 `(shop_id, /kf/<hash>)` 找今天的重复行；**保留最早一条、删后续**；删除前确认这些行：全是 `pending_review`、只属于本次 run 的 discoveries、无其它 run 引用、无外键违规。
3. 删完把 `scan_runs.new_count` 校正为真实新增（例：924→51），并按实际 `scan_discoveries` 重算 `scan_shop_results.new_count`。
4. 校验：`PRAGMA foreign_key_check` 为空；`alm.py overview` 的 `todayNewCount` 与 `db-stats` 一致。

> 只删"重复的那一份"，不要动真实新品；不确定的一律保留。删数据前一定要用户确认（这是不可逆操作，除非用备份回滚）。

## 长期修复：products.py 去重改造（已落地）

`alimonitor\services\products.py`：
- 主键仍查 `(shop_id, remote_product_id)`；查不到时，用 **同店铺 + 同主图 hash + 同标题（去掉营销前缀后）** 兜底匹配老记录。
- 命中兜底则走 UPDATE（只刷新 `last_seen_at`/title/image），**不新增行**。
- INSERT 成功后把新行同步进本批的 `known_images` 索引，让同批后续商品也能命中。
- helper：`_image_key()`（取 `/kf/<hash>`，正则 `r"/kf/([^.?#/]+)"`）、`_title_key()`（小写、统一引号/dash、压空白、剥 `in stock/new arrival/new/hot/pre-sale/ready to ship/original/official` 等前缀）、`_load_shop_image_index()`、`_match_existing_by_image()`。
- 边界：**同图不同标题**基本不是一件（实测全库仅 2 组，且语义确实不同：如 "Computron" vs "MS-Toy technobots"）；**同标题不同图**有 74 组（不同 SKU/配色），所以不能只按标题去重。安全判据 = 同图 **且** 同标题。
- 测试：`tests/test_discoveries.py` 新增 `test_new_remote_id_same_image_and_title_is_not_new`、`test_same_image_different_title_stays_separate`、`test_image_dedup_is_scoped_to_shop`。跑全套：`.venv\Scripts\python.exe -m pytest -q`（当时 590 passed；`tests/test_launcher.py::test_built_application_export_completes_without_manual_worker_pump` 是历史 flaky，与去重无关）。

改动后用 WMI 方式重启服务生效。改代码一律「只改不提交」，等用户发话再 commit。
