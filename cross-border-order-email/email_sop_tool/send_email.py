"""SMTP sender for cross-border order emails.

Sends HTML email (so <b> tags render as bold) via smtp.qq.com:465 SSL
using the pre-configured toyssuppor@foxmail.com account.

Supports images:
- `images=[...]` each item is either:
    - a local file path  -> embedded inline image, auto-appended to the body
    - a dict: {"path": <file>, "mode": "inline"|"attachment", "cid": <optional id>}
  Inline images get a Content-ID (e.g. "img1") so you can reference them in the
  HTML body via <img src="cid:img1">. If an inline image is not referenced in the
  body, it is auto-appended at the end (max width 480px).
  Attachment images are sent as downloadable files.
"""

import json
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "smtp_config.json")

DEFAULT_CONFIG = {
    "sender_name": "Customer Service",
    "sender_email": "toyssuppor@foxmail.com",
    "smtp_host": "smtp.qq.com",
    "smtp_port": 465,
    "password": "",  # QQ Mail authorization code (not the login password)
}

# Attachment size safety limit (bytes) - QQ Mail limits large attachments.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5MB


def _load_config(config_path=None) -> dict:
    path = config_path or CONFIG_PATH
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # merge defaults so missing keys don't crash
        return {**DEFAULT_CONFIG, **cfg}
    return dict(DEFAULT_CONFIG)


def _mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _normalize_images(images):
    """Yield dicts with keys: path, mode ('inline'|'attachment'), cid."""
    for i, item in enumerate(images or [], start=1):
        if isinstance(item, str):
            yield {"path": item, "mode": "inline", "cid": f"img{i}"}
        elif isinstance(item, dict):
            mode = item.get("mode", "inline")
            cid = item.get("cid") or f"img{i}"
            yield {
                "path": item["path"],
                "mode": mode,
                "cid": cid,
            }
        else:
            raise TypeError(f"Invalid image item: {item!r}")


def _auto_append_inline_refs(body_en: str, inline_cids) -> str:
    """Append <img> tags for inline images not already referenced in the body."""
    missing = []
    for cid in inline_cids:
        if f"cid:{cid}" not in body_en:
            missing.append(cid)
    if not missing:
        return body_en
    tags = "".join(
        f'<br><img src="cid:{cid}" style="max-width:480px;border:1px solid #ddd;border-radius:4px;">'
        for cid in missing
    )
    return body_en + tags


def send_email(to_email: str, subject: str, body_en: str, images=None, config_path=None) -> dict:
    """Send an HTML email with optional images.

    Args:
        to_email: recipient address
        subject: email subject
        body_en: HTML body
        images: optional list of image paths / dicts (see module docstring)
        config_path: optional path to a custom smtp_config JSON (default:
            email_sop_tool/smtp_config.json). Use e.g. smtp_config_126.json
            to send from the 126 account while keeping QQ as the default.

    Returns:
        {'status': 'ok'|'error', ...}
    """
    cfg = _load_config(config_path)
    password = cfg.get("password") or os.environ.get("SMTP_PASSWORD", "")
    if not password:
        return {
            "status": "error",
            "message": (
                f"SMTP password (authorization code) is not configured in {config_path or CONFIG_PATH}. "
                "Set it in the config file or via the SMTP_PASSWORD env var, then retry."
            ),
        }

    normalized = list(_normalize_images(images))
    inline_items = [it for it in normalized if it["mode"] == "inline"]
    attach_items = [it for it in normalized if it["mode"] == "attachment"]

    # Validate files & size
    for it in normalized:
        if not os.path.exists(it["path"]):
            return {"status": "error", "message": f"Image file not found: {it['path']}"}
        size = os.path.getsize(it["path"])
        if size > MAX_ATTACHMENT_BYTES:
            return {
                "status": "error",
                "message": (
                    f"File too large for email ({size//1024} KB > 5MB): {it['path']}"
                ),
            }

    if inline_items:
        body_en = _auto_append_inline_refs(body_en, [it["cid"] for it in inline_items])

    from_addr = f"{cfg['sender_name']} <{cfg['sender_email']}>"

    has_attachments = bool(attach_items)
    if has_attachments:
        # outer mixed: attachments + related(html + inline images)
        outer = MIMEMultipart("mixed")
        related = MIMEMultipart("related")
        related.attach(MIMEText(body_en, "html", "utf-8"))
        for it in inline_items:
            related.attach(_make_image_part(it["path"], it["cid"], inline=True))
        outer.attach(related)
        for it in attach_items:
            outer.attach(_make_image_part(it["path"], it["cid"], inline=False))
        msg = outer
    elif inline_items:
        msg = MIMEMultipart("related")
        msg.attach(MIMEText(body_en, "html", "utf-8"))
        for it in inline_items:
            msg.attach(_make_image_part(it["path"], it["cid"], inline=True))
    else:
        msg = EmailMessage()
        msg.set_content("Please view this email in an HTML-compatible client.")
        msg.add_alternative(body_en, subtype="html")

    msg["From"] = from_addr
    msg["To"] = to_email
    msg["Subject"] = subject

    context = ssl.create_default_context()
    try:
        # timeout: avoid hanging forever on a stuck SMTP connection (learned 2026-08-10)
        with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], context=context,
                              timeout=45) as server:
            server.login(cfg["sender_email"], password)
            server.send_message(msg)
        return {
            "status": "ok",
            "to": to_email,
            "subject": subject,
            "inline_images": len(inline_items),
            "attachments": len(attach_items),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)}


def _make_image_part(path: str, cid: str, inline: bool):
    """Build a MIME part for an image file."""
    mime_type = _mime_type(path)
    if mime_type.startswith("image/") and mime_type in (
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/bmp",
    ):
        with open(path, "rb") as f:
            data = f.read()
        part = MIMEImage(data, _subtype=mime_type.split("/")[1])
    else:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=os.path.basename(path),
        )

    if inline:
        part.add_header("Content-ID", f"<{cid}>")
        part.add_header("Content-Disposition", "inline")
    else:
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=os.path.basename(path),
        )
    return part
