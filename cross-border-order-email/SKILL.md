---
name: 跨境订单邮件
description: |
  This skill handles the full workflow of cross-border e-commerce abnormal order email communication.
  Triggered when the user sends an order screenshot and asks to notify the buyer about issues
  (pre-order delay, out of stock, defective items, logistics problems).
  Provides bilingual email generation with preview confirmation before sending via SMTP.
  This skill should be used when the user shares an order screenshot/image with an issue description.
agent_created: true
---

# Cross-Border E-Commerce Order Email Skill

## Purpose

Handle the end-to-end workflow: screenshot → information extraction → bilingual email generation → user confirmation → SMTP sending.

## Trigger

This skill triggers when the user:
- Sends a screenshot/image of an order (from AliExpress, eBay, etc.)
- Mentions an order issue (pre-order can't ship, out of stock, defect, logistics)
- Asks to notify a buyer / send an email about an order problem

## Tool Paths

The tool files ship with this skill under `email_sop_tool/`. Before running the workflow in a project, copy this folder into the project root (so `<project_root>/email_sop_tool/` exists):

```
cp -r <skill_dir>/email_sop_tool <project_root>/email_sop_tool
```

| File | Purpose |
|------|---------|
| `email_sop_tool/email_templates.py` | Template generation (3 scenarios: scenario_1 out-of-stock/pre-order, scenario_2 defect, scenario_3 logistics) |
| `email_sop_tool/send_email.py` | SMTP sending (smtp.126.com:465 SSL, HTML body) |
| `email_sop_tool/smtp_config.json` | SMTP config (sender hezhen226102@126.com); `password` holds the SMTP authorization code (or leave empty and supply it via the `SMTP_PASSWORD` env var at send time) |

> **Security (optional)**: the QQ Mail authorization code may be stored directly in `smtp_config.json` (`password` field) for convenience, or passed per-send via the `SMTP_PASSWORD` environment variable to avoid persisting the secret. Choose per your own risk tolerance.

## Workflow

### Step 1: Extract Order Information from Screenshot

Read the image using the Read tool. Extract:
- **Buyer email** (required — the recipient address)
- **Order number** (required)
- **Platform** (required — AliExpress, eBay, Shopee, etc.)
- **Product name** (if visible)
- **Order amount** (if visible)

If any required field cannot be read from the screenshot, ask the user.

### Step 1b: VERIFY the email address (MANDATORY — do not skip)

> **Lesson learned 2026-08-08**: On one batch of 18 screenshots, 6/18 email
> addresses were misread (e.g. `carefejimbob` vs `carefreejimbob`, `october666ruff`
> vs `october666rust`, `auqian2023` vs `ausjan2023`, `us2398160208zabee` vs
> `...zabae`, `voiceactorrdreamer` vs `voiceactordreamer`, `allanstanton` vs
> `alanstanton`). Dense lowercase runs (rr/ll/ee/st/ae/fre/ffe/ua/an) are the
> most error-prone. DO NOT trust a first-pass read; always verify.

**Verification procedure for every email address:**

1. **Crop + upscale the email field** from the screenshot before reading it
   (screenshots are usually 1080px wide; text is too small to read reliably):

   ```python
   from PIL import Image
   img = Image.open('<screenshot_path>')
   w, h = img.size
   # Email field is usually on the right side, y ≈ 32-50% of image height
   crop = img.crop((int(w * 0.50), int(h * 0.32), w, int(h * 0.50)))
   crop = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
   crop.save('<output_path>')   # then Read this file and read the address out loud
   ```

   If the crop misses the field, adjust the y range and re-crop (the field sits
   right under "联系邮箱" / "Contact email").

2. **Read it twice** (two separate Read calls, at least one from an upscaled
   crop). Compare both readings; they must agree character-by-character.

3. **Sanity-check the result**: `@` appears exactly once, domain is a known
   provider (gmail/yahoo/hotmail/outlook/qq/163/naver/aliyun/aliexpress/...),
   and the local part has no spaces or obvious double letters in odd places.
   If anything looks off, crop again and re-read, or ask the user.

4. **Optional belt-and-braces**: for batch workflows, export the list of
   extracted addresses to a txt file (one per line) and present it to the user
   for a final eyeball check BEFORE sending.

### Step 2: Determine the Scenario

Ask the user or infer from context. Four scenarios exist:

1. **scenario_1** — Pre-order delay / Out of stock → Request cancellation
2. **scenario_2** — Partial defect / No box → Request to keep (fast ship + cash compensation)
3. **scenario_3** — Logistics issue / Delivery failed → Urge buyer to contact local post
4. **scenario_4_po_box** — Address not deliverable (PO Box / 备注「地址不可达」) → Ask buyer for a physical street address, otherwise cancel for a full refund

### Step 3: Generate the Email

Run this Python code to generate the email:

```python
import sys
sys.path.insert(0, '<project_root>/email_sop_tool')
from email_templates import OrderInfo, generate_email

order = OrderInfo(
    buyer_email='<extracted_email>',
    order_number='<extracted_order_number>',
    platform='<extracted_platform>',
    product_name='<extracted_product_name>',
)
result = generate_email('<scenario_key>', order)
print(result['subject'])
print(result['body_en'])  # English body — this is what gets sent
print(result['body_cn'])  # Chinese body — reference only, NEVER sent
```

### Step 4: Present Preview for Confirmation

Display the email to the user in this exact format:

```
收件人：<buyer_email>
主题：<subject>

英文（发送）
---
<body_en>
---

中文（仅参考，不发送）
---
<body_cn>
---

确认发送？回复"发送"。
```

CRITICAL: Always show the full Chinese version (body_cn), never abbreviate or omit it. The user needs to see the complete Chinese reference.

### Step 5: Send on Confirmation

When the user replies "发送" / "Y" / "yes" / "发" / "OK":

```python
import sys
sys.path.insert(0, '<project_root>/email_sop_tool')
from email_templates import OrderInfo, generate_email
from send_email import send_email

# ... generate as above ...
r = send_email(
    to_email=order.buyer_email,
    subject=result['subject'],
    body_en=result['body_en'],
)
# r['status'] == 'ok' means success
```

**Optional — send with images** (upgraded 2026-08-07):

```python
# Inline image: displayed in the body (auto-appended at the end if not referenced).
# Reference it manually in body_en via <img src="cid:img1"> for placement control.
r = send_email(to, subject, body_en, images=[r"C:\path\product.jpg"])

# Attachment image: downloadable file.
r = send_email(to, subject, body_en, images=[{"path": r"C:\path\doc.pdf", "mode": "attachment"}])

# Mixed.
r = send_email(to, subject, body_en, images=[
    {"path": r"C:\path\photo.png", "mode": "inline", "cid": "img1"},
    {"path": r"C:\path\manual.pdf", "mode": "attachment"},
])
```

Image rules:
- Supported inline types: png / jpeg / gif / webp / bmp (sent as `image/*` with a `Content-ID`)
- Other files are sent as `application/octet-stream` attachments
- Files larger than **5MB** are rejected (QQ Mail limit)
- Keep images small (prefer compressed jpg/webp); large emails are more likely flagged as spam

Report back: "已发送成功！✅" with recipient, status, and subject.

## Email Style Rules (MANDATORY)

These rules were established through user feedback and must be followed exactly.

> **Out-of-stock (scenario_1) template — UPDATED 2026-08-06 (user-specified).**
> The user overrode the original "My dear friend" template with this cleaner version.
> This is now the DEFAULT for scenario_1. Keep the other scenarios as-is.
>
> Subject: `Aliexpress Order Update: [Order#] About [Product]`
> Body (EN):
> ```
> Dear Valued Customer,
>
> Hope you are doing well.
>
> We are writing to inform you that your item [Product] (Order No. [Order#]) cannot be shipped right now, as it is currently out of stock. Please select one of the following options:
>
> Cancel the order: You may submit a cancellation request directly on AliExpress.
>
> Please feel free to contact us if you have any questions.
>
> Best regards,
> Customer Service Team
> ```
> Notes: no `<b>` tags, no apology-discount line, no step-by-step cancel instructions.
> `email_sop_tool/email_templates.py` scenario_1 already implements this.

1. **Opening (scenario_1)**: "Dear Valued Customer," then "Hope you are doing well." (other scenarios keep "My dear friend,")
2. **Apology (scenario_1)**: "We are writing to inform you that ... cannot be shipped right now, as it is currently out of stock." (no "We sincerely apologize")
3. **First sentence**: Include product name and order number. E.g., "your item [Product] (Order No. [Order#])"
4. **Cancel order (scenario_1)**: Option-style — "Cancel the order: You may submit a cancellation request directly on AliExpress." (no `<b>`, no compensation offer)
5. **No step-by-step instructions** (other scenarios): Do NOT tell the buyer specific steps to cancel. Instead: "please **cancel this order** on your AliExpress account. If you need assistance, please contact AliExpress customer service."
6. **Compensation** (other scenarios): "As an apology, we will offer you an exclusive discount on any future purchase from our store." — standard wording, do not vary
7. **Signature**: "Best regards,\nCustomer Service Team"
8. **Conciseness**: Keep to ~6 sentences maximum. No filler.
9. **Pre-order vs out of stock** (other scenarios): Distinguish correctly:
   - Pre-order: "is a pre-order item and unfortunately cannot be shipped at this time"
   - Out of stock: "is currently out of stock and unavailable for the foreseeable future"
10. **Subject formula (scenario_1)**: `Aliexpress Order Update: [Order#] About [Product]`
    **Subject formula (other scenarios)**: `[Platform] Order [Order#]: [Issue EN] / [Issue CN]`

### Subject Templates by Scenario

| Scenario | EN Subject | CN Subject |
|----------|-----------|------------|
| scenario_1 (pre-order) | Pre-order Delay & Cancellation Notice | 预售商品无法发货通知 |
| scenario_1 (out of stock) | `Aliexpress Order Update: [Order#] About [Product]` | 缺货通知（客户模板） |
| scenario_2 | Item Condition Notice & Special Offer | 商品瑕疵说明及补偿方案 |
| scenario_3 | Urgent: Delivery Issue - Action Required | 紧急物流问题通知 |
| scenario_4_po_box | `[Platform] Order [Order#]: Address Issue - PO Box Not Deliverable` | 收货地址问题：邮政信箱无法投递 |

**scenario_4_po_box style (added 2026-09-12)**: same clean style as scenario_1 —
"Dear Valued Customer," + "Hope you are doing well.", no `<b>` tags, **no discount/
compensation line** (the address problem is on the buyer's side). Ask for a physical
street address first, offer local-post-office pickup as an alternative, and only then
fall back to "please cancel this order directly on AliExpress, and you will be fully
refunded." Trigger keywords in the order note: `pos地址不可达` / `地址不可达` /
address is a `PO Box`.

## SMTP Configuration

Pre-configured, do NOT ask user to re-enter unless sending fails:
- **Default sender (user preference 2026-08-10)**: Customer Service <toyssuppor@foxmail.com> via QQ
  SMTP: smtp.qq.com:465 (SSL), config path `email_sop_tool/smtp_config.json`
- **Fallback (126 account)**: <hezhen226102@126.com>, SMTP smtp.126.com:465 (SSL),
  config path `email_sop_tool/smtp_config_126.json` — pass `config_path='email_sop_tool/smtp_config_126.json'`
  to `send_email()` only if the user explicitly asks for the 126 account.
- The project copy of `smtp_config.json` must hold the QQ account; do not overwrite it with the 126 config.

## Important Reminders

- The Chinese version (body_cn) is for USER REFERENCE ONLY — it is NEVER appended to the outgoing email
- HTML `<b>` tags in body_en are intentional for bold rendering in the email
- After sending, briefly confirm success and remind the user they can send more orders
- Do NOT skip the confirmation step — always show preview and wait for explicit "发送" before sending
