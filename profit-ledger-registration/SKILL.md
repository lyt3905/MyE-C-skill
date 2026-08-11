# 跨境电商运营利润登记

## Overview

将用户提供的订单文字信息解析为字段，按「运营利润统计表」结构追加到 `62店8月利润表.xlsx`。**核心原则：只写文字值，不动格式和公式**。

## 台账文件

- **利润表**：`C:\Users\shana\Desktop\62店8月利润表.xlsx`（独立文件，跨月新建）
- **目标 sheet**：运营利润统计表（仅这一个 sheet）
- **预填结构**：row 1 合并标题，row 2 列名，A/I/J 列公式已预填到约 500 行
- ⚠️ **交替行背景色**：奇数行(row 3,5,7...)B-E 列白底 `FFFFFFFF`，偶数行无填充；row 1 绿底 `FFE2EFD9`；不动颜色

### 运营利润统计表 12 列

| 列 | 字段 | 来源 | 说明 |
|---|---|---|---|
| A | 序号 | 公式已有 | `=ROW()-2`，不动 |
| B | 下单日期 | 用户提供 | 付款时间 |
| C | 订单编号 | 用户提供 | 平台订单号 |
| D | 名字（商品规格） | 用户提供 | 商品名称 |
| E | 进货价格 | 用户提供 | 从备注提取（如 "yu516.66" → 516.66） |
| F | 平台预计可得（CNY） | 用户提供 | 「预计可得（到手）」；有 duty/ICMS 则减去 |
| G | 运费 | 默认为空 | 留空不填 |
| H | 平台其他扣费 | 默认为空 | 留空不填 |
| I | 利润 | 公式已有 | `=ROUND(F-G-E-H,2)`，不动 |
| J | 利润率 | 公式已有 | `=ROUND(I/(G+E),2)`，不动 |
| K | 进货人 | 默认 刘宇彤 | |
| L | 备注 | 默认为空 | 留空不填 |

## 工作流

### 1. 解析用户输入

用户发来一段订单详情文字。**只提取页面直接可见的数值**：

- 下单日期（「付款时间」）
- 订单编号（「订单号」）
- 商品名/规格（「商品信息」）
- 进货价格（备注里提取数字，如 "yu516.66" → 516.66；缺了就问）
- 平台预计可得（「预计可得（到手）」；有 duty/ICMS 项则减去）
- ⚠️ **同单多商品不拆分**：一个订单的多件商品合并为一条记录，商品名用 `/` 连接（如 "MSB64/MSB63/MSB65"），预计可得填整单金额，不平均拆分
- 运费（留空）
- 平台其他扣费（留空）
- 进货人（默认 刘宇彤）
- 备注（⚠️ 留空不填）

### 2. ⚠️ 每次写入前必须备份

```python
import shutil, os, datetime
fp = r"C:\Users\shana\Desktop\62店8月利润表.xlsx"
bak_dir = r"C:\Users\shana\Desktop\62店台账备份\利润表备份"
os.makedirs(bak_dir, exist_ok=True)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy2(fp, os.path.join(bak_dir, f"62店8月利润表_{ts}.xlsx"))
```

### 2.5 登记顺序约定（用户约定）

**用户一般按下单时间顺序提供订单，默认追加到末尾即可**。
- 若发现新订单的下单日期早于已登记的最后一条（乱序），**先提醒用户确认**，不要自动插入排序

### 3. 追加写入（只写值，不动格式）

找到第一个 C 列为空的行 → 只对 B/C/D/E/F/K/L 列设值，不设 font/border/alignment：

```python
import openpyxl, zipfile, shutil, os
from datetime import datetime

FILE = r"C:\Users\shana\Desktop\62店8月利润表.xlsx"

# 备份 + 提取 WPS 部件
parts = {}
z = zipfile.ZipFile(FILE)
for n in z.namelist():
    if n in ('xl/cellimages.xml','xl/_rels/cellimages.xml.rels',
             'xl/customStorage/customStorage.xml',
             'xl/customStorage/_rels/customStorage.xml.rels',
             '[Content_Types].xml','xl/_rels/workbook.xml.rels',
             'xl/sharedStrings.xml','xl/_rels/sharedStrings.xml.rels') \
       or n.startswith('xl/media/'):
        parts[n] = z.read(n)
z.close()

wb = openpyxl.load_workbook(FILE)
ws = wb['运营利润统计表']

# 找第一个空行（C列无值）
row = 3
while row <= ws.max_row:
    if ws.cell(row, 3).value is None or str(ws.cell(row, 3).value).strip() == '':
        break
    row += 1

# 只设值，不设格式
ws.cell(row, 2).value = datetime(2026,8,7)       # B: 下单日期
ws.cell(row, 3).value = '订单编号'                 # C: 订单编号
ws.cell(row, 4).value = '商品名'                   # D: 商品
ws.cell(row, 5).value = 进货价格                   # E: 进货价
ws.cell(row, 6).value = 平台预计可得                # F: 预计可得
ws.cell(row, 11).value = '刘宇彤'                  # K: 进货人
# L: 备注留空，不写值
# A/G/H/I/J 不动（公式已存在或留空）

wb.save(FILE)

# 恢复 WPS 部件
items = {}
z = zipfile.ZipFile(FILE)
for n in z.namelist(): items[n] = z.read(n)
z.close()
for n,d in parts.items():
    if n not in items: items[n] = d
tmp = FILE + '.tmp'
zout = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
for n,d in items.items(): zout.writestr(n, d)
zout.close()
shutil.copy2(tmp, FILE)
try: os.remove(tmp)
except: pass
```

### 4. ⚠️ 写入后必须与备份对比验证（用户强制约定）

**每次添加后，都必须与写入前的备份文件对比，确保没有影响之前的内容**：

```bash
python scripts/verify_unchanged.py \
  --backup "备份目录/62店8月利润表_写入前时间戳.xlsx" \
  --file "C:\Users\shana\Desktop\62店8月利润表.xlsx" \
  --row 19
```

- 对比范围：新增行之前的所有行（值+公式+格式）、表头、列宽、行高、冻结窗格、筛选、合并单元格、下拉框
- **通过**：输出 `✅ OK` → 可以继续
- **有差异**：输出差异明细并以退出码 1 结束 → **立即停止，先排查差异原因**（常见：WPS 打开导致文件被旧版本覆盖），不要继续追加
- 对比差异不通过时，从备份恢复主文件再重新操作

### 5. 写入后验证

读回新写入的行，确认 B/C/D/E/F/K 值与用户提供的一致，A/I/J 公式不受影响。

## 关键技术坑

1. **不动格式**：只 `ws.cell(row, col).value = xxx`，不设 font/border/alignment/fill/row_height，保持文件原有背景色、样式和行高（sheet 默认 25.0）。
2. **A/I/J 公式已预填**：不需要写入公式，文件里已有。
3. **找空行用 C 列**：C 列是订单编号，有值 = 有数据。
4. **WPS 部件保留**：openpyxl 保存会丢 cellimages/customStorage/sharedStrings，必须备份恢复。
5. **文件锁**：WPS 打开时 PermissionError → 先关闭。
6. **环境**：系统 Python `C:\Users\shana\AppData\Local\Programs\Python\Python312\python.exe` + openpyxl。
7. **跨月**：月初提醒新建当月利润表。

## 与采购登记 skill 的关系

- `purchase-ledger-registration`：采购端 → 提供进货价参考
- 本 skill：销售端 → 登记平台销售利润
