---
name: feishu-sheet-writer
description: 用飞书自建应用 API 读写电子表格 / 多维表格：定位 wiki 链接、清空重写、写活公式、插入截图、把本地 xlsx 传成飞书原生表格。当用户给出 feishu.cn 的 wiki / sheets / base 链接并要求往里写内容、改成新结构、补图片，或要求把本地 Excel 上传替换线上文档时使用。This skill should be used when the user wants to read or write a Feishu/Lark spreadsheet or bitable via the Open Platform API — writing rows and live formulas, embedding screenshots, or importing a local workbook as a native Feishu sheet.
agent_created: true
---

# 飞书电子表格 / 多维表格写入

## Overview

用户给一条飞书链接（`/wiki/…`、`/sheets/…`、`/base/…`），要用程序把内容写进去。
飞书没有给第三方留「浏览器式」入口，唯一正规路径是**企业自建应用 + 开放平台 API**。
本 skill 固化这条链路上所有实测过的命令、坑和校验手法，脚本见 `scripts/feishu.js`（零依赖，只需 Node ≥ 18）。

**先认清对象类型**，后面全按类型走不同接口：

| 链接形态 | obj_type | obj_token 是什么 | 用什么接口 |
| --- | --- | --- | --- |
| `/wiki/<node>?sheet=xx` | `sheet` | spreadsheet_token | `sheets/v2` `sheets/v3` |
| `/wiki/<node>` 或多维表 | `bitable` | base app_token | `bitable/v1` |
| `/wiki/<node>?table=tblxxx` 且 obj_type=`sheet` | 表内**嵌**的多维表格 | 电子表格 token**反查不到** | 拿不到 base token，只能按单元格写外层 sheet |
| `/sheets/<token>` | — | 直接用 | `sheets/v2` |
| `/base/<token>?table=tblxxx` | — | 直接用 | `bitable/v1` |

> 血泪点：URL 里带 `table=tblXxx&view=vewXxx` 不等于它是多维表格。先跑 `wiki <nodeToken>` 看 `obj_type`，
> 曾遇到 `obj_type=sheet` 而 `table=` 属于第二个工作表里嵌的 bitable，用外层 token 调 bitable 接口只会得到 `91402 NOTEXIST`。

## 前置条件（一次性，约 5 分钟）

1. <https://open.feishu.cn/app> 建「企业自建应用」，抄下 `app_id` / `app_secret`。
2. **权限管理** 开通（开通后必须「创建版本 → 发布」才生效，这是最常见的「改了没反应」原因）：
   - `sheets:spreadsheet` —— 电子表格读写（只读版 `:readonly` 不够）
   - `bitable:app` —— 多维表格读写
   - `wiki:wiki:readonly` —— 反查 wiki 节点
   - `drive:drive` —— 上传 / 导出 / 授权
3. **把应用加成文档协作者**：表格右上「分享 / ···」→「添加文档应用」→ 选应用 → **可编辑**。
   知识库里的节点要让应用能建节点，还得在「知识库 → 设置 → 成员管理」给**可编辑/可管理**。
4. 凭据落地（任选，优先级从高到低）：
   - 环境变量 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
   - `FEISHU_CRED_FILE` 指向的 json
   - `%USERPROFILE%\.dsh\feishu-app.json` ← **推荐**，本机全局可用
   - `./feishu/app.json`（当前工作目录）

   ```json
   { "app_id": "cli_xxxxxxxx", "app_secret": "xxxxxxxx" }
   ```

凭据只写本机，`.token.json` 缓存 2 小时；泄露就去开放平台重置 secret。

## 命令速查

```powershell
$FS = "<skill>\scripts\feishu.js"

node $FS whoami                                          # 验证凭据 + 显示读的是哪个 cred 文件
node $FS wiki   <wikiNodeToken>                          # wiki 链接 -> obj_token / obj_type
node $FS sheets <spreadsheetToken>                       # 子表 sheet_id / 标题 / resource_type
node $FS read   <ssToken> 'bfe2ca!A1:H20' --render FormattedValue
node $FS write  <ssToken> 'bfe2ca!A4:H6' --data-file rows.json
node $FS append <ssToken> 'bfe2ca!A4:H4' --data-file row.json
node $FS img    <ssToken> 'bfe2ca!I4:I4' shot.png shot.png
node $FS export <ssToken> --out cur.xlsx                 # 导出成 xlsx（校验样式/图片用）
python scripts\verify_xlsx_style.py cur.xlsx <工作表名> --rows 3-8   # 导出后查字体/CF/DV/图片/值
node $FS upload <本地文件> [--name xx] [--parent <folder>]
node $FS import <本地xlsx> [--name 名字]                  # 上传 + 转成飞书原生电子表格
node $FS share  <token> <openId> [--type sheet|file]     # 给用户开权限（否则只有应用能看）
node $FS tables|fields|list|add|addmany|update ...        # 多维表格（记录级）
node $FS raw    <METHOD> <path> --body-file body.json     # 兜底：任意接口
```

`read` 的 `--render`：`ToString`（默认，看公式文本）、`FormattedValue`（看计算结果）、`Formula`（看公式原文）、`UnformattedValue`（看原始值，日期是序列号）。

## 硬坑清单（全部实测踩过）

1. **裸字符串公式会被当文本存**。`"=IF(A4=0,\"未完成\",\"已完成\")"` 写进去，读回来还是那串 `=…`，不算公式。
   必须用带类型的单元格对象：`[{"type":"formula","text":"=IF(A4=0,\"未完成\",\"已完成\")"}]`。
   试过的错法：`{"type":3}` / `{"type":2}` → `90204 invalid cell type`；`{"formula":"=1+1"}` → 同样 90204。
2. **插图**（`values_image`）三个坑：
   - `name` 字段**必须带扩展名**（`.png` / `.jpg`）——接口靠它猜格式，传中文名或 `probe` 会报 `90204 Image format is unknown`；
   - 图片**不能带 alpha 通道**（RGBA / palette PNG 同样报 format unknown），先 `PIL Image.convert("RGB")` 再存；
   - 插进去是**单元格内图片**（读回来 `[[{"type":"embed-image","id":N}]]`），显示大小被行列尺寸框死，而**行高/列宽没有公开 API 可改**——只能在飞书里手动拖。写 `""` 覆盖该格即可删除图片。
3. **样式（字体/删除线/颜色/填充）既不能读也不能写**。想改必须人手动「清除格式」。
   典型事故：原模板对「已完成」行留了静态删除线格式，写新内容后新文字继承了删除线，而接口无能为力。
   稳妥做法：**另建干净文件**（openpyxl 写 xlsx，删除线改成条件格式 `$B4="已完成"`），再用 `import` 传上来。
4. **三类权限错误码要分清**（脚本已内置中文提示）：
   - `91403 Forbidden` → 文档级：应用没被加成「可编辑」协作者（读得到写不了就是这个）
   - `99991672` → 应用缺 scope（开通后没发版也会这样）
   - `131006 tenant needs edit permission` → 知识库空间/节点级：要在知识库成员管理里给应用可编辑
5. **PowerShell 会吞掉内联 JSON 里的双引号** → 一律 `--data-file` / `--body-file`：
   ```powershell
   [IO.File]::WriteAllText("$PWD\rows.json", '[["a",1]]', (New-Object Text.UTF8Encoding $false))
   ```
   同理别用 `Set-Content -Encoding UTF8`（PS 5.1 会加 BOM，能直接毁掉 `#!/usr/bin/env node` 和中文）。
6. **导出任务轮询必须带 `?token=<源文档token>`**，否则 `99992402 field validation failed: token is required`。导入任务轮询则不用。
7. **清空单元格用空字符串 `""`**（`null` 不保证生效）；清空一片区域就写同形状的 `""` 矩阵。
8. **上传/导入产生的文件属于应用**，用户默认看不到 → 用 `share` 把 `openid` 加成 `full_access`（openid 可从 wiki 节点的 `creator`/`owner` 字段拿到）。
9. **写数据只动数据区**：保留表头行、合并单元格、公式列、统计行；覆盖前先 `read` 一遍并落盘备份。
10. **xlsx → 飞书原生表格的保真度很好**（实测）：活公式、条件格式、数据验证下拉、冻结窗格、内嵌图片全部保留。所以复杂格式优先走这条路，不要硬用单元格 API 拼。

## 标准流程

### 0. 定位对象
`wiki <node>` 拿 `obj_token` + `obj_type`；`sheets <token>` 拿子表 id；**先确认 resource_type**（`sheet` / `bitable`）。

### 1. 读结构 + 备份
```powershell
node $FS read <ss> '<sheetId>!A1:M25' --render Formula > backup.json
node $FS read <ss> '<sheetId>!A1:M6'  --render FormattedValue   # 看渲染结果
```
看清：表头在第几行、哪些列是公式、统计行在哪、有没有数据验证。

### 2. 写入
- 只写目标区域，别整表覆盖；
- 公式列用 `{"type":"formula","text":…}`；
- 空行让公式自己隐藏（`=IF(C4="","",…）`），别把空行写成「未完成」刷屏。

### 3. 三层校验（必做，缺一层都可能翻车）
1. **读回**：`read --render FormattedValue` 确认值/计算结果对；
2. **公式活性**：把勾选列改 `1` 再改回 `0`，确认派生列跟着变（证明是活公式不是静态值）；
3. **样式与图片**：`export` 成 xlsx → 跑 `scripts/verify_xlsx_style.py`（查 `font.strike`、条件格式、数据验证、内嵌图片数量与锚点、值是否为活公式）；需要看观感时再用 LibreOffice Kit 渲染成 PNG。
   这一步就是抓出「行 6 残留删除线」和「插图被行高夹扁」的尺子——**飞书 API 读不到样式，只能导出后看**。

### 4. 插图
先 `convert("RGB")` → `img <ss> '<sheetId>!I4:I4' a.png a.png` → 读回确认 `embed-image`。
插完提醒用户：缩略图受行高限制，要看得清就手动拉行高/列宽。

### 5. 整本替换线上文档
`import 本地.xlsx` → 得到原生 sheet token + url → `share` 给用户 → （若要挂进知识库）需要知识库编辑权限，否则只能用户自己拖进去。

## 已知文档登记

| 文档 | 关键 token |
| --- | --- |
| 「刘宇彤-测试」待办清单（wiki） | wiki node `L2etwfkrkiVc40kURYhcy9kunMd`；obj_type `sheet`；spreadsheet `HUo3sTcWShlZxMtVIkvc7hJ6nrg`；子表「待办事项清单」`bfe2ca`；表内嵌 bitable 工作页 `Rczbgo`（token 不可反查）；知识库 `7648451020569185515` |
| 该表列结构 | `已完成 / 完成情况 / 待办事项 / 优先级 / 工作·生活 / 进度 / 截止日期 / 备注 / 截图`，表头在第 3 行，数据从第 4 行起 |

## 变更记录

- 2026-10-26 首版：从「往飞书表里写待办 + 插图 + 整本导入」一次实战中沉淀。
