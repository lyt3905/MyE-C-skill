---
name: feishu-todo-registration
description: 把用户的每一句诉求/需求/发现当成一条待办事项，追加进飞书「刘宇彤-测试」待办清单（含截图上传到「截图」列、完成情况活公式、生图模板列）。当用户说「记一条待办」「这个记下来」「我给你说的每一句话都是一条待办事项」，或用户随口提需求/发现问题/发截图要你登记时使用。
---

# 飞书待办清单登记

## Overview

用户的口头约定（2026-10-29）：**「我给你说的每一句话都是一条待办事项」**。
所以用户每说一条诉求，就要在飞书待办清单里**追加一行**，不是只在聊天里答复。

本 skill 固化：目标文档位置 → 行结构与默认值 → 写整行的正确方式（B 列必须活公式）→ 截图上传到 I 列 → 三层校验。

底层 API 调用**复用 `feishu-sheet-writer` skill 的脚本**（同一仓库：`../feishu-sheet-writer/scripts/feishu.js`），
凭据在 `%USERPROFILE%\.dsh\feishu-app.json`。本 skill 不重复实现鉴权。

## 目标文档

| 项 | 值 |
| --- | --- |
| 文档标题 | 「刘宇彤-测试」（知识库 wiki 节点） |
| wiki node_token | `L2etwfkrkiVc40kURYhcy9kunMd` |
| obj_type / spreadsheet_token | `sheet` / `HUo3sTcWShlZxMtVIkvc7hJ6nrg` |
| 子表 | 「待办事项清单」 sheet_id `bfe2ca`（另一页「待办事项-优先级」`Rczbgo` 是表内嵌 bitable，token 反查不到，别碰） |
| 知识库 space_id | `7648451020569185515` |
| 打开链接 | `https://<租户域名>.feishu.cn/wiki/L2etwfkrkiVc40kURYhcy9kunMd?sheet=bfe2ca`（租户域名需问用户，API 拿不到） |

## 行结构

- **第 1 行**：合并标题「待办清单」
- **第 2 行**：一句引言（康德）
- **第 3 行**：**表头**（A–J），不要动
- **第 4 行起**：数据行。找空行看 **C 列**（`待办事项`）是否为空

| 列 | 字段 | 写什么 |
| --- | --- | --- |
| A | 已完成 | `0`（未完成）/ `1`（完成），复选框语义 |
| B | 完成情况 | ⚠️ **公式，不能写字符串**：`=IF(C{r}="","",IF(A{r}=0,"未完成","已完成"))` |
| C | 待办事项 | 一句话说清做什么（祈使句，≤30 字左右） |
| D | 优先级 | 默认 `P1`；用户说急/影响卖货/侵权类 → `P0` |
| E | 工作/生活 | 默认 `工作` |
| F | 进度 | 默认 `0` |
| G | 截止日期 | 默认留空 |
| H | 备注 | **必写**：用户原话诉求 + 已经做了什么 + 还差什么（判断依据写这里） |
| I | 截图 | 内嵌图片（embed-image）；用户发图就传到同一行的 I 列 |
| J | 生图模板 | 2026-10-29 新增列。生图类待办记录本次用的模板名；未知留空 |

现有数据：第 4–8 行 5 条老待办（标题关键词 / SKU 标题不生效 / 主图补位 / 违禁词 Optimus Prime / 4406 蝙蝠侠换风格），
2026-10-29 追加到第 9–10 行。

## 工作流

### 1. 判断该不该入表

| 用户说的话 | 处理 |
| --- | --- |
| 提需求、发现问题、定规则、指出要改的地方 | **追加一行**，同时口头答复 |
| 纯提问（「你写到哪里了」「发我具体地址」） | 先回答；默认不入表（用户若要求字面逐句都记，再补） |
| 同一诉求的后续补充 | 优先**改已有行的 H 备注**，别另开一行刷屏 |

追加后回报：第几行 + 关键列内容 + revision，不要只说「已记录」。

### 2. 追加一行（推荐用脚本）

```powershell
node scripts\append_todo.js --item "AI 合图记录显示所用模板，支持自动选/手动改" `
  --priority P1 --note "诉求原文…；已加 J 列表头；还需定义模板清单" `
  --template "" --image .\shot_rgb.png
```

脚本会：读表找空行 → 写 A{r}:J{r}（B 列自动生成公式）→ 有图则转 RGB 后插 I{r} → 读回校验 → 输出 `{ok,row}`。
`--dry-run` 只打印将写入的行；`--clear-row N` 清空该行（自测后收尾用）。

手工方式（等价，便于排查）：

```powershell
# 1) 找空行
node $FS read $SS 'bfe2ca!A3:J40' --render ToString
# 2) 写整行（B 列用带类型的对象！）
[IO.File]::WriteAllText("$PWD\row.json", $json, (New-Object Text.UTF8Encoding $false))
node $FS write $SS 'bfe2ca!A9:J9' --data-file "$PWD\row.json"
```

### 3. 截图上传（I 列）

```powershell
# 必须先去 alpha，否则 90204 Image format is unknown
& $PY -c "from PIL import Image; Image.open(r'in.png').convert('RGB').save(r'out.png')"
node $FS img $SS 'bfe2ca!I9:I9' out.png out.png
```

- 一张图 → 该行 I 列；多张图 → 目前一行只放一张，多余的另起行或问用户
- `name` 参数必须带 `.png`/`.jpg` 扩展名
- 插完**一定要提醒用户**：单元格图片显示尺寸被行高列宽卡死，而**行高列宽没有公开 API**，要看清得在飞书里手动拉行高/列宽

### 4. 三层校验

1. `read 'bfe2ca!A{r}:J{r}' --render FormattedValue`：C/H 内容对，**B 显示「未完成」**（证明公式活了）
2. 有图时：读回 I 列必须是 `[{"id":N,"type":"embed-image"}]`
3. 要更稳就 `export` 成 xlsx 后查 `xl/media/` 数量是否 = 历史图数 + 新增图数（飞书会把 png 转 jpeg，属正常）

## 关键技术坑

1. **PowerShell 吞内联 JSON 的双引号** → 一律先落 `--data-file`，用 `[IO.File]::WriteAllText(path, text, (New-Object Text.UTF8Encoding $false))`；别用 `Set-Content -Encoding UTF8`（PS 5.1 加 BOM）。
2. **B 列写裸字符串 `"=IF(...)"` 会被当文本存**，读回来还是 `=IF(...)` 不算公式；必须写 `{"type":"formula","text":"=IF(C9=\"\",\"\",IF(A9=0,\"未完成\",\"已完成\"))"}`。`{"type":3}` / `{"formula":...}` 都报 `90204`。
3. **图片不能带 alpha**（RGBA/palette PNG 报 `90204 Image format is unknown`），先 `convert("RGB")`。
4. **每行公式要按行号重新生成**，不能整列复制粘贴同一串（否则引用错行）；空行公式用 `=IF(C{r}="","",…)` 自隐藏，别把空行写成「未完成」。
5. **样式（字体/删除线/填充）读写接口都没有**：新行若继承到怪格式，只能人在飞书里「清除格式」；整表要重做样式就本地 openpyxl 生成再 `import`。
6. **权限错误码**：`91403` = 应用没被加成可编辑协作者；`99991672` = 缺 scope（开通后没发版）；`131006` = 知识库节点级权限。
7. 写入 `revision` 会递增（写一格 +1 左右），不是冲突信号，无需处理。

## 与其他 skill 的关系

- `feishu-sheet-writer`：底层飞书 API 工具（`scripts/feishu.js` 的 read/write/img/export），本 skill 的依赖
- `profit-ledger-registration` / `purchase-ledger-registration`：Excel 台账登记，与本 skill 无关

## 变更记录

- 2026-10-29 首版：从「用户说每句话都是待办 + 加生图模板列 J + 截图上传 I 列」一次实战中沉淀。
