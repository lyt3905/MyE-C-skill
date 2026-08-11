---
name: purchase-ledger-registration
description: 跨境电商（62店）采购台账登记。当用户发送微信支付/订单/闲鱼采购截图，要求按「62店8月-采购登记表.xlsx」结构登记采购记录（填自发货采购登记表、运营利润统计表或纠纷订单统计表）时使用。This skill should be used when the user sends payment/order/dispute screenshots and asks to register them into the 62-store August purchase ledger Excel file, extracting fields from images and appending rows per the workbook's schema.
agent_created: true
---

# 跨境电商采购台账登记

## Overview

将用户发来的截图（微信支付账单、订单详情页、闲鱼采购页）识别为字段，按 62 店台账的结构追加写入 Excel，并把原图以浮动图（oneCellAnchor）插入对应格子。适用于 62店8月-采购登记表.xlsx 的日常采购登记。

## 台账文件与结构

- **主台账**：`C:\Users\shana\Desktop\62店8月-采购登记表.xlsx`（8月专用，跨月如 9 月才新建）
- **参考模板**（勿改）：`C:\Users\shana\Desktop\62店8月.xlsx`
- ⚠️ **模板用途约定（用户强调）**：只参考模板的**格式和填写内容**（表头、列宽、样式、下拉框、每列填什么），**不要参考它的具体信息**（模板里的 7 月示例数据、图片等一律不要带入新表）
- 3 个工作表：运营利润统计表（12列）/ 自发货采购登记表（20列）/ 纠纷订单统计表（19列）
- ⚠️ **表头结构差异（重建/读取时务必注意）**：
  - 运营利润统计表 / 纠纷订单统计表：**row 1 是合并标题**（"产品销售采购管理" / "纠纷订单台账"），**row 2 才是列名**
  - 自发货采购登记表：**row 1 就是列名**
  - 清空数据时：运营利润/纠纷删 row 3+，自发货删 row 2+

### 自发货采购登记表 20 列（row 1 表头）
序号, 采购日期, 企业微信审批编号, 采购类别, 系列, 名字（商品规格）, 单位, 采购数量, 单价(元), 合计金额(元), 进货人, 付款方式, 付款金额, 付款日期, 预计到货日期, 产品图片, 自行垫付支付截图, 财务付款截图, 实际入库日期, 收货人

### 运营利润统计表 12 列（row 2 列名，row 1 标题 A1:L1 合并）
序号, 下单日期, 订单编号, 名字（商品规格）, 进货价格, 平台预计可得（CNY）, 运费, 平台其他扣费, 利润, 利润率, 进货人, 备注
- 利润 = ROUND(F-E-G-H, 2)，利润率 = ROUND(I/(G+E), 2)（公式列）
- 订单页截图无进货价格 → 需用户补充

### 纠纷订单统计表 19 列（row 2 列名，row 1 标题 B1:S1 合并）
序号, 纠纷时间, 店铺, 运营, 订单号, 下单时间, 名字（商品规格）, 数量, 纠纷订单状态, 纠纷理由, 协商方案, 退款退货类别, 退款金额, 退货运单号, 退货入库时间, 验收人, 验收结果, 处理结果, 二次销售时间

### 下拉框（数据验证，保留勿删）
- 自发货表 D 列（采购类别）：list 下拉
- 纠纷表 L 列（退款退货类别）：list 下拉

## 工作流

### 1. 识别图片
- 微信支付账单详情：提取 支付时间、金额、付款方式（亲情卡/零钱等）、商品说明、商家订单号
- 闲鱼订单详情页：提取 商品名、成交价、订单编号、下单/付款时间
- 付款人姓名后缀带 `[进货]` 标记的是采购付款（如"亲情卡（李辉[进货]）"）

### 1.5 图片列分类规则（用户约定）
| 列 | 字段名 | 填什么 |
|---|---|---|
| **P** | 产品图片 | 商品图/闲鱼订单详情页截图（展示商品规格） |
| **Q** | 自行垫付支付截图 | **一般为空**（除非有垫付凭证） |
| **R** | 财务付款截图 | **微信支付账单详情类截图**（含支付时间/金额/付款方式/订单号） |

- 脚本调用：`--img-prod` → P 列（产品图），`--img-self-pay` → Q 列（垫付），`--img-pay` → R 列（财务付款）
- 闲鱼 T200P 订单号、拼多多订单详情这类"商品+订单信息"的截图 → P 列
- 微信支付账单详情（含"账单详情/支付成功/支付时间/付款方式/订单号"字样）→ **R 列**

### 2. 默认字段规则（用户约定，无需询问）
| 字段 | 规则 |
|---|---|
| 采购日期 | = 付款日期（图片支付时间）|
| 采购类别 | 备货进货 |
| 系列 | 从商品名判断（变形金刚/万代等）|
| 单位 | 闲鱼（商家订单号 **T200P** 开头）或图片显示的渠道 |
| 采购数量 | 1 |
| 单价 | = 付款金额 |
| 合计金额 | = 付款金额 |
| 进货人 | 刘宇彤 |
| 收货人 | 刘宇彤（进货人为刘宇彤时）|
| 预计到货日期 | 付款日期 +3天 |
| 实际入库日期 | = 预计到货日期 |
| 企业微信审批编号 | 不填 |
| 序号 | 自动递增（各表独立）|

### 2.5 ⚠️ 每次写入前必须备份（用户强制约定）
**任何修改台账文件的操作（追加行/改图/改列宽/重建）开始前，必须先备份**：
```python
import shutil, os, datetime
fp = r"C:\Users\shana\Desktop\62店8月-采购登记表.xlsx"
bak_dir = r"C:\Users\shana\Desktop\62店台账备份\进货表备份\Excel备份"  # Excel 备份专门子文件夹
os.makedirs(bak_dir, exist_ok=True)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = os.path.join(bak_dir, f"62店8月-采购登记表_{ts}.xlsx")
shutil.copy2(fp, bak)
```
- **备份统一放 `C:\Users\shana\Desktop\62店台账备份\` 文件夹**（用户约定，不放桌面根目录）
- **⚠️ 备份分类存放（用户约定 2026-08-11）**：Excel 备份、截图、利润表分别放独立子文件夹，不要混在根目录：
  - `62店台账备份\进货表备份\Excel备份\` ← 台账 .xlsx 备份（`62店8月-采购登记表_YYYYMMDD_HHMMSS.xlsx`）
  - `62店台账备份\进货表备份\截图备份\{YYYYMMDD}-{产品}-{分类}\` ← 订单截图
  - `62店台账备份\利润表备份\` ← 利润表备份（与进货表备份同级）
- 备份命名带时间戳：`62店8月-采购登记表_20260803_1112.xlsx`
- 此规则对 append 脚本、zipfile 手动编辑、列宽调整、重建都适用

### 2.6 ⚠️ 收到图片先备份 + 分组存文件夹（用户强制约定）
**用户发来截图时，先备份图片再登记**：
- 备份目录：`C:\Users\shana\Desktop\62店台账备份\进货表备份\截图备份\`
- **每组（每单）图片单独一个子文件夹**，文件夹命名：`{YYYYMMDD}-{产品名称}-{分类}`（日期前缀方便排序，如 `20260802-魔方MS-B65计算王钢鞭-变形金刚`）
- 步骤：1) 识别图片属于哪个订单（付款日期作为 YYYYMMDD）→ 2) 创建子文件夹 → 3) 复制所有该订单的图进去 → 4) 再登记到台账
- 订单详情图 + 账单图放同一组文件夹

### 2.7 ⚠️ 追加前检查浮动图/嵌入图状态（用户约定）
**追加新行前，检查之前行的图片状态**：
- 读 drawing1.xml（浮动图锚点）+ cellimages.xml（嵌入图 ID）+ sheet2.xml DISPIMG 公式
- 如果之前行的浮动图**被嵌入**（转为 cellimages 嵌入图）：检查 cellimages.xml.rels 每个 Target 文件是否存在、大小是否与嵌入图原内容一致
- **没问题 → 不做修改**，继续追加
- **发现问题（引用缺失/内容被覆盖）→ 先通知用户**，等确认后再操作，不擅自改动已有行

### 2.8 ⚠️ 图片 P/R 列分配 + 写入后必查方向（用户约定）
**给新行加图片时，务必按用途分配，不要按图片顺序想当然**：
- **P 列（产品图）← 订单详情截图**（pinduoduo/闲鱼订单详情，展示商品规格）
- **R 列（账单）← 微信/支付宝支付账单截图**（AlipayGphone/微信账单）
- 常见错误：把账单放 P 列、订单详情放 R 列（2026-08-05 row 11 实际发生过）
- **写入后必须验证方向**：找该行 DISPIMG 公式的 ID → cellimages.xml 的 rId → cellimages.xml.rels 的 Target → 对比文件大小与源图（订单详情 vs 账单），确认 P/R 各就各位
- 修正方法：交换两个 media 文件的二进制内容即可（不动 cellimages/公式）

### 3. 追加写入
用脚本 `scripts/append_purchase_row.py` 一键追加（含浮动图插入）：
```bash
python scripts/append_purchase_row.py \
  --file "C:\Users\shana\Desktop\62店8月-采购登记表.xlsx" \
  --data '[...20个值JSON...]' \
  [--img-prod "产品图.jpg"] [--img-self-pay "垫付截图.jpg"] [--img-pay "财务图.jpg"]
```
- 日期值用 ISO 字符串 `"2026-08-01T10:49:36"` 传入
- 图片列（16 产品图片 / 17 自行垫付支付截图 / 18 财务付款截图）不写值，由 `--img-prod` → P 列、`--img-self-pay` → Q 列、`--img-pay` → R 列 插入浮动图（200×445px）
- **⚠️ 用户约定：永远不指定 `--row`**，让脚本自动追加到最后一个数据行的下一行（脚本逻辑：从 max_row+1 往回找最后一个非空行再 +1，正好落在末尾）。只有明确要覆盖/改写某一行时才用 `--row`，且需先跟用户确认
- **⚠️ 写入前先按 2.5 节备份**
- ⚠️ **当文件含用户嵌入图（cellimages.xml 存在）时，不要用本脚本**（openpyxl 重打包会错乱嵌入图 media 引用）。改用 zipfile 直接编辑方案（见下方"zipfile 直编方案"）

### 4. 用户手动嵌入图片
⚠️ **DISPIMG 嵌入无法自动化**：DISPIMG ID 由 WPS 运行时生成，无法伪造（图片 MD5≠ID，手动构造 cellimages.xml 实测无效）。**图片嵌入由用户手动在 WPS 做**：插入图片→右键→嵌入到单元格。我只负责浮动图占位。

### 4.5 ⚠️ 浮动图 vs 嵌入图共存风险（核心经验）
**根源问题**：我添加浮动图（drawing1.xml + oneCellAnchor）后，文件里同时存在用户之前的手动嵌入图。WPS 保存时会：
- 重写 drawing1.xml（命名空间从 `xmlns=""` 变成 `xdr:` 前缀，`</wsDr>` → `</xdr:wsDr>`）
- 重命名嵌入图引用的 media 文件（image1.jpeg → image15.jpeg 等）
- 清理孤儿文件

**导致**：我拼的浮动图 rels 引用失效（Target 指向被重命名的文件），表现就是图片显示错误或缺失。

**解决方案 / 安全流程（已与用户确认）**：
1. 我加浮动图（数据 + 占位图）
2. 用户**不保存**，在 WPS 打开验证数据
3. 用户手动嵌入所有浮动图，保存 WPS
4. 此时文件变成**纯嵌入图**（16 个全部由 WPS 管理）
5. **纯嵌入图文件上 WPS 保存不会再打乱任何东西** ← 关键结论
6. 我仅做验证（cellimages.xml.rels 引用全部 OK 即通过），不动文件

**技术要点**：
- WPS 保存后的 drawing1.xml 使用 `xdr:` 前缀命名空间，用 zipfile 直接编辑时要注意匹配 `</xdr:wsDr>` 而非 `</wsDr>`
- WPS 保存后 rels 格式为 `Id="rIdN" Type="..." Target="..."`（Id 在 Target 前）
- 修复浮动图 rels 时，重建整个 `<Relationships>` 比逐个替换更可靠

### 5. 台账重建 / 清空旧数据（用户约定：只保留格式）
用户要求"新建为空的，从今天开始登记，去除旧信息"时：
```python
from openpyxl import load_workbook
wb = load_workbook(r"C:\Users\shana\Desktop\62店8月.xlsx")  # 模板
keep = {"运营利润统计表": 2, "自发货采购登记表": 1, "纠纷订单统计表": 2}  # 各表保留的表头行数
for sn in wb.sheetnames:
    ws = wb[sn]
    if ws.max_row > keep[sn]:
        ws.delete_rows(keep[sn] + 1, ws.max_row - keep[sn])
    ws.row_dimensions.clear()
    ws._images = []  # 删浮动图；openpyxl 保存自动丢弃 cellimages.xml/media（正好清掉旧嵌入图）
wb.save(r"C:\Users\shana\Desktop\62店8月-采购登记表.xlsx")
```
- 重建后字符串存为 inlineStr（无 sharedStrings.xml，合法），列宽/冻结窗格/合并单元格/下拉框自动保留
- **重建前**：备份旧文件为 `.bak`；提取今天已登记行的截图（先看 drawing1.xml 的锚点 → rels 映射 media 文件名）供重新登记用
- 重建后序号从 1 重新计，登记脚本自动追加到 row 2 起

## 关键技术坑（必须遵守）

1. **⚠️ openpyxl 重存会丢弃 cellimages.xml 和 sharedStrings.xml**（用户手动嵌入的图 + 共享字符串）！含嵌入图的文件：
   - 追加数据/插入浮动图用 `append_purchase_row.py`（脚本 backup_wps_parts 自动备份 cellimages/cellimages.xml.rels/customStorage/sharedStrings 并恢复）
   - 只改列宽/行高/纯文本时用 **zipfile 直接改 XML**，不要过 openpyxl
   - ⚠️ **用户嵌入图（DISPIMG 公式）和脚本浮动图（oneCellAnchor）共存**：嵌入图存在 cellimages.xml，openpyxl ws._images 看不到；脚本只追加浮动图，互不干扰。识别信号：`ws.cell(r,16).value` 是 `=_xlfn.DISPIMG("ID_xxx",1)`
   - ⚠️ **⚠️⚠️ openpyxl 重打包时会重命名嵌入图引用的 media 文件**（image1.jpeg → image3.jpeg 等），导致 cellimages.xml.rels 的 Target 指向错位的图。**append 后必须验证**：cellimages.xml.rels 每个 Target 对应的文件大小是否还是嵌入图原本的内容；不一致就从 WPS 备份 `%AppData%\Roaming\Kingsoft\office6\backup\` 找原图恢复，并手动改回 rels Target。**以后追加含嵌入图的文件后必须做这步校验**
2. **文件锁**：预览面板/WPS 打开文件时 Python 写入报 PermissionError → 先请用户关闭预览再写入
3. cellimages.xml 注册信息（WPS 私有命名空间）：
   - Content_Types: `application/vnd.wps-officedocument.cellimage+xml`
   - workbook rels: `http://www.wps.cn/officeDocument/2020/cellImage`
   - ⚠️ **不要手动添加/修改这些声明**（2026-08-11 实测）：WPS 有自己的识别机制，我手动往 Content_Types 和 workbook.xml.rels 里加 cellimages 声明，反而把图片显示弄坏（显示 ref）。**保持文件原样**，只改数据/锚点
   - **判断文件是否带正确 cellimage 结构**：读 workbook.xml.rels，看是否有 `Type="http://www.wps.cn/officeDocument/2020/cellImage" Target="cellimages.xml"` 的 Relationship + Content_Types 里有 `cellimages.xml` Override。**两个都有 = 图片能正常显示**；缺 = 图片数据在但显示不出来（显示 ref / 空白）
4. 环境：系统 Python `C:\Users\shana\AppData\Local\Programs\Python\Python312\python.exe` + openpyxl + pillow
5. 本地 editor_sdk / sheetagent 通道不可用，不要尝试
6. **脚本入参编码**：JSON 数据带中文时不要在 PowerShell/bash 直接传参（易乱码），用 Python 子进程 `json.dumps(data, ensure_ascii=False)` 传参最稳；bash 传 Windows 路径用正斜杠。
7. **⚠️ 沙箱陷阱 - 绝对不要手动删 .tmp 文件**：
   - 脚本用 `<file>.tmp` 做中间写入，shutil.copy2 完成后 `os.remove(tmp)` 会被 safe-delete 拒绝（沙箱无回收站）
   - 残留的 `.tmp` 文件**可能正好是当前最新的好状态**（如果上次 save 写完 .tmp 但没 copy2 到主文件就中断了）
   - 如果发现 `.tmp` 和主文件大小相同，**别动 .tmp**，先把 .tmp 复制成 .xlsx 验证再决定
   - 例外：如果主文件已损坏（[Content_Types].xml 丢失等），且 `.tmp` 大小正常（>30MB），那就是救命稻草
8. **⚠️ 主文件损坏急救 - WPS 自动备份**：
   - 路径：`C:\Users\shana\AppData\Roaming\Kingsoft\office6\backup\`
   - 文件名格式：`<原名>.<16位hash>.<YYYYMMDDhhmmssmmm>.et`
   - WPS 每 30 分钟一次完整快照，文件大小通常 40-50MB
   - 损坏症状：`[Content_Types].xml` 丢失、sharedStrings 丢失、openpyxl 读报 `KeyError`、文件大小骤降
   - 恢复方法：找最近一份大于 30MB 的 .et，复制为 .xlsx 即可
   - 兜底目录：同层 `62店8月.xlsx` 是参考模板（勿改），只用来对照结构不包含当前月数据
9. **⚠️ 文件被覆盖成"空壳"急救（2026-08-11 实测）**：
   - 症状：主文件从 22.7MB 骤降到 21KB，media 0 个，cellimages 丢失，但表格结构还在（打开能看到数据没图）
   - 现场：桌面出现 `..._YYYYMMDD_HHMMSS_fixdup.xlsx` 之类副本（可能是某个去重/另存操作生成的）
   - **关键：桌面多个副本可能是"正常版"和"残缺版"混着**：
     - 正常版：23848KB，workbook.xml.rels 有 `wps.cn/officeDocument/2020/cellImage` 引用 → 图片能显示
     - 残缺版：22753KB，缺该引用 → 图片数据在但显示 ref/空白
   - **恢复方法**：MD5 对比 + 检查 workbook.xml.rels 是否有 cellimage 引用 → 选正常版 `shutil.copy2` 覆盖主文件
   - 验证：恢复后 MD5 应与源一致，openpyxl 读取 56 张嵌入图，WPS 能显示图片
10. **⚠️ 序号重排（删除行后序号错位）**：
   - 场景：删除了重复行（如盲盒买 2 误登记 2 条删 1），但 A 列序号没重排 → 出现 8 后直接 10 的断号，最后序号比实际行数多 1
   - 修复：zipfile 直接改 sheet2.xml，对断号之后每行 A 列序号减 1（`<c r="A10"...><v>10</v>` → `<v>9</v>`），直到恢复 1-N 连续
   - 用户约定：序号必须连续（1,2,3...N），删除行后要主动检查并重排

## 其他表

- **运营利润统计表**：订单页截图 → 需用户补充进货价格（图片无）；利润/利润率是公式列。列名在 row 2
- **纠纷订单统计表**：纠纷截图 → 填写 店铺/运营/订单号/状态/理由/退款金额 等。列名在 row 2
- 这两张表的登记脚本未内置，需要时用 openpyxl 直接写（注意 row 2 列名，从 row 3 开始追加）
