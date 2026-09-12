"""Email templates for cross-border e-commerce order issue notifications.

Scenarios:
- scenario_1 (out of stock): Out of Stock Notice & Solutions / 缺货通知及解决方案
- scenario_1_preorder: Pre-order Delay & Cancellation Notice / 预售商品无法发货通知
- scenario_2: Item Condition Notice & Special Offer / 商品瑕疵说明及补偿方案
- scenario_3: Urgent: Delivery Issue - Action Required / 紧急物流问题通知
- scenario_4_po_box: Address Issue - PO Box Not Deliverable / 收货地址问题（邮政信箱无法投递）
- scenario_5_repack_delay: Shipping Delay Notice (repacking) / 发货延期通知（重新备货）
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderInfo:
    buyer_email: str
    order_number: str
    platform: str
    product_name: Optional[str] = None


def _subject(platform: str, order_number: str, issue_en: str, issue_cn: str) -> str:
    return f"{platform} Order {order_number}: {issue_en} / {issue_cn}"


def generate_email(scenario_key: str, order: OrderInfo) -> dict:
    """Return dict with keys: subject, body_en, body_cn.

    body_en is the HTML email that gets sent (contains <b> tags for bold).
    body_cn is for the seller's reference only and is NEVER sent.
    """
    platform = order.platform
    order_number = order.order_number
    product_line = f' (product: {order.product_name})' if order.product_name else ''

    if scenario_key in ("scenario_1", "scenario_1_out_of_stock"):
        # Preferred style (user-specified 2026-08-06): "Dear Valued Customer" +
        # "Hope you are doing well" + option-style cancellation.
        product_about = order.product_name or "your item"
        subject = f"Aliexpress Order Update: {order_number} About {product_about}"
        product_ref = order.product_name or "your item"
        body_en = (
            "Dear Valued Customer,<br><br>"
            "Hope you are doing well.<br><br>"
            f"We are writing to inform you that your item {product_ref} "
            f"(Order No. {order_number}) cannot be shipped right now, as it is currently out of stock. "
            "Please select one of the following options:<br><br>"
            "Cancel the order: You may submit a cancellation request directly on AliExpress.<br><br>"
            "Please feel free to contact us if you have any questions.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "尊敬的客户：<br><br>"
            "希望您一切安好。<br><br>"
            f"我们写信告知您，您的商品 {product_ref}（订单号 {order_number}）"
            "目前缺货，暂时无法发货。请您选择以下任一处理方式：<br><br>"
            "取消订单：您可直接在 AliExpress 上提交取消申请。<br><br>"
            "如有任何问题，欢迎随时联系我们。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    elif scenario_key == "scenario_1_preorder":
        subject = _subject(platform, order_number,
                           "Pre-order Delay & Cancellation Notice",
                           "预售商品无法发货通知")
        body_en = (
            "My dear friend,<br><br>"
            f"We sincerely apologize that your {platform} order {order_number}{product_line} "
            "is a pre-order item and unfortunately cannot be shipped at this time.<br><br>"
            "Since we are unable to ship this item, we kindly ask you to "
            "<b>cancel this order</b> on your AliExpress account. "
            "If you need assistance, please contact AliExpress customer service.<br><br>"
            "As an apology, we will offer you an exclusive discount on any future purchase from our store.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "亲爱的朋友：<br><br>"
            f"我们非常抱歉地通知您，您在 {platform} 的订单 {order_number}{product_line} "
            "为预售商品，目前暂时无法发货。<br><br>"
            "由于我们无法发货，恳请您在您的 AliExpress 账户上<b>取消此订单</b>。"
            "如需帮助，请联系 AliExpress 客服。<br><br>"
            "作为歉意，我们将在您日后在本店的任何购买中为您提供专属折扣。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    elif scenario_key == "scenario_2":
        subject = _subject(platform, order_number,
                           "Item Condition Notice & Special Offer",
                           "商品瑕疵说明及补偿方案")
        body_en = (
            "My dear friend,<br><br>"
            f"We sincerely apologize regarding your {platform} order {order_number}{product_line}. "
            "Upon inspection, the item has a minor defect / the original box was damaged in transit. "
            "The product itself remains fully functional.<br><br>"
            "We can ship a replacement immediately, and as an apology we will also offer you a cash compensation. "
            "If you prefer, you may keep the item and accept the compensation.<br><br>"
            "As an apology, we will offer you an exclusive discount on any future purchase from our store.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "亲爱的朋友：<br><br>"
            f"就您在 {platform} 的订单 {order_number}{product_line}，我们非常抱歉。"
            "经检查，商品存在轻微瑕疵 / 原包装在运输途中受损，但商品本身功能完好。<br><br>"
            "我们可以立即补发，并作为歉意提供现金补偿。如您愿意，也可保留商品并接受补偿。<br><br>"
            "作为歉意，我们将在您日后在本店的任何购买中为您提供专属折扣。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    elif scenario_key == "scenario_3":
        subject = _subject(platform, order_number,
                           "Urgent: Delivery Issue - Action Required",
                           "紧急物流问题通知")
        body_en = (
            "My dear friend,<br><br>"
            f"We sincerely apologize for the delivery issue with your {platform} order {order_number}{product_line}. "
            "The parcel appears to be pending or undelivered at your local post office.<br><br>"
            "Please contact your local post office as soon as possible to arrange collection or redelivery. "
            "If you need assistance, please contact AliExpress customer service.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "亲爱的朋友：<br><br>"
            f"就您在 {platform} 的订单 {order_number}{product_line} 出现的物流问题，我们非常抱歉。"
            "包裹似乎停留在您当地邮局，待领取或未能成功投递。<br><br>"
            "请尽快联系您当地邮局安排领取或重新投递。如需帮助，请联系 AliExpress 客服。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    elif scenario_key in ("scenario_4_po_box", "scenario_4"):
        # PO Box / 地址不可达（新增 2026-09-12）：买家下单地址为 PO Box 或物流渠道
        # 无法投递，请买家提供实体街道地址；若无法更改则取消订单全额退款。
        # 风格与 scenario_1 保持一致：Dear Valued Customer + Hope you are doing well，
        # 无 <b> 标签，无折扣补偿承诺。
        product_ref = order.product_name or "your item"
        subject = (
            f"{platform} Order {order_number}: "
            "Address Issue - PO Box Not Deliverable / 收货地址问题：邮政信箱无法投递"
        )
        body_en = (
            "Dear Valued Customer,<br><br>"
            "Hope you are doing well.<br><br>"
            f"We are writing regarding your item {product_ref} (Order No. {order_number}). "
            "Our shipping channel cannot deliver to a PO Box address, so we are unable to "
            "ship your parcel to the address shown on the order.<br><br>"
            "Could you please provide a physical street address for delivery? If you prefer, "
            "you may also confirm that you can collect the parcel from your local post office.<br><br>"
            "If the address cannot be changed, please cancel this order directly on AliExpress, "
            "and you will be fully refunded.<br><br>"
            "Please feel free to contact us if you have any questions.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "尊敬的客户：<br><br>"
            "希望您一切安好。<br><br>"
            f"我们写信是关于您的商品 {product_ref}（订单号 {order_number}）。"
            "我们的物流渠道无法投递至邮政信箱（PO Box）地址，因此无法按订单上的地址为您发货。<br><br>"
            "能否请您提供一个实体的街道收货地址？如果您更方便，也可以确认您能到当地邮局自行领取包裹。<br><br>"
            "如果地址无法更改，请直接在 AliExpress 上取消此订单，款项将全额退回。<br><br>"
            "如有任何问题，欢迎随时联系我们。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    elif scenario_key in ("scenario_5_repack_delay", "scenario_5"):
        # 打包发现损坏 → 重新备货 → 发货延期 + 请买家延长收货时间
        # （新增 2026-09-12，源于主人手写草稿的口语化版本，此处润色为规范邮件）
        # 风格：Dear Valued Customer + Hope you are doing well，无 <b>、无折扣补偿承诺。
        product_ref = order.product_name or "your item"
        subject = (
            f"{platform} Order {order_number}: "
            "Shipping Delay Notice - Please Extend Delivery Time / 发货延期通知：请延长收货时间"
        )
        body_en = (
            "Dear Valued Customer,<br><br>"
            "Hope you are doing well.<br><br>"
            f"We are writing regarding your item {product_ref} (Order No. {order_number}). "
            "Your product was originally ready, but some damage was found during packing. "
            "Out of responsibility to our customers, we will prepare a new item for you.<br><br>"
            "Therefore the shipping time may be slightly delayed. We sincerely apologize for the "
            "inconvenience.<br><br>"
            "Could you please extend the delivery time on your order, so that it will not be closed "
            "by the system? We would really appreciate your help.<br><br>"
            "Please feel free to contact us if you have any questions.<br><br>"
            "Best regards,<br>"
            "Customer Service Team"
        )
        body_cn = (
            "尊敬的客户：<br><br>"
            "希望您一切安好。<br><br>"
            f"我们写信是关于您的商品 {product_ref}（订单号 {order_number}）。"
            "您的商品原本已经备好，但在打包时发现有损坏。出于对客户负责，我们将为您重新准备一件新商品。<br><br>"
            "因此发货时间可能会有所延迟，对此我们深表歉意。<br><br>"
            "能否请您为订单延长收货时间，以免订单被系统自动关闭？非常感谢您的帮助。<br><br>"
            "如有任何问题，欢迎随时联系我们。<br><br>"
            "此致，<br>"
            "客服团队"
        )

    else:
        raise ValueError(f"Unknown scenario_key: {scenario_key}")

    return {
        "subject": subject,
        "body_en": body_en,
        "body_cn": body_cn,
    }
