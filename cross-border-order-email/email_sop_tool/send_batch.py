"""Batch sender for cross-border order emails (multi-order paste workflow).

Why this exists (2026-11-09): the user frequently pastes a block of 10+ orders at
once ("这 12 个订单都发延期通知"), not screenshots. Sending them one agent turn
at a time is slow and error-prone, so batch it with one script:

    python send_batch.py orders.json --dry-run     # 先预览全部正文，给用户核对
    python send_batch.py orders.json               # 用户说「发送」后再真发

orders.json — a JSON list, one object per order (same field names as OrderInfo):

    [
      {"order_number": "8213545919253638",
       "buyer_email": "julian.espitia@gmail.com",
       "scenario": "scenario_9_partial_stock_extend",
       "product_name": "CDTOYS Revoltech TMNT 13cm Action Figure",
       "product_name_cn": "CDTOYS 转轮系列 忍者神龟 13cm 可动人偶",
       "extend_days": 90,
       "in_stock_variants": "blue and purple",
       "variant": "A Set"},
      {"order_number": "8215624520137256",
       "buyer_email": "jo2castro65@gmail.com",
       "scenario": "scenario_8_wrong_item",
       "product_name": "BAIWEI TW-1124 Jetfire OP Commander",
       "product_name_cn": "百微 TW-1124 天火 OP 指挥官",
       "product_short": "TW-1124",
       "discount_total": 5, "discount_base": 3, "discount_extra": 2}
    ]

Extra fields: "variant" (any extra descriptor, appended to the CN preview only),
"sender"/"config_path" (per-run SMTP override).

Options:
  --dry-run          build and print everything, send nothing
  --only 1,3,5       send only these 1-based indexes
  --interval 3       seconds between sends (default 3, keeps QQ SMTP happy)
  --config PATH      SMTP config (default smtp_config.json next to this file)
  --start-at 2       resume after a failure without re-sending the first ones

Output: per-mail `OK [i/n] <order> -> <email>` lines, then `sent_ok=N failed=M`.
Any failure is listed with its error at the end and the process exits 1, so a
re-run with --start-at is explicit rather than accidental.
"""

import argparse
import io
import json
import os
import sys
import time

# Chinese in stdout turns into mojibake on a cp936 console; force UTF-8.
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from email_templates import OrderInfo, generate_email  # noqa: E402
from send_email import send_email  # noqa: E402


def build_order(rec: dict) -> OrderInfo:
    """Map one JSON record to OrderInfo, ignoring unknown/aux keys."""
    fields = OrderInfo.__dataclass_fields__
    kwargs = {k: v for k, v in rec.items() if k in fields}
    if "buyer_email" not in kwargs or "order_number" not in kwargs:
        raise ValueError("each record needs buyer_email and order_number")
    kwargs.setdefault("platform", "Aliexpress")
    return OrderInfo(**kwargs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("orders_json", help="path to the JSON list of orders")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="", help="1-based indexes, e.g. 1,3,5")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--config", default=os.path.join(HERE, "smtp_config.json"))
    ap.add_argument("--start-at", type=int, default=1, help="1-based resume index")
    args = ap.parse_args(argv)

    with open(args.orders_json, "r", encoding="utf-8") as fh:
        records = json.load(fh)
    if not isinstance(records, list) or not records:
        print("orders json must be a non-empty list")
        return 2

    only = {int(x) for x in args.only.split(",") if x.strip().isdigit()}
    todo = [
        (i, rec)
        for i, rec in enumerate(records, 1)
        if i >= args.start_at and (not only or i in only)
    ]

    sent_ok, failures = 0, []
    for n, (idx, rec) in enumerate(todo, 1):
        order = build_order(rec)
        scenario = rec.get("scenario", "scenario_9_partial_stock_extend")
        result = generate_email(scenario, order)
        head = f"[{n}/{len(todo)}] #{idx} {order.order_number} -> {order.buyer_email}"
        if args.dry_run:
            print(f"DRY {head}\n  subject: {result['subject']}")
            print("  en: " + result["body_en"].replace("<br>", "\n      ")[:700])
            print("  cn: " + result["body_cn"].replace("<br>", "\n      ")[:700])
            continue
        try:
            r = send_email(
                to_email=order.buyer_email,
                subject=result["subject"],
                body_en=result["body_en"],
                config_path=args.config,
            )
            if r.get("status") == "ok":
                sent_ok += 1
                print(f"OK  {head} | ok")
            else:
                err = r.get("message") or r
                failures.append((order.order_number, err))
                print(f"ERR {head} | {err}")
        except Exception as exc:  # keep going; report at the end
            failures.append((order.order_number, repr(exc)))
            print(f"ERR {head} | {exc!r}")
        if n < len(todo):
            time.sleep(args.interval)

    if args.dry_run:
        print(f"\ndry_run={len(todo)} (nothing sent)")
        return 0
    print(f"\nsent_ok={sent_ok} failed={len(failures)}")
    for order_no, err in failures:
        print(f"  failed: {order_no} | {err}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
