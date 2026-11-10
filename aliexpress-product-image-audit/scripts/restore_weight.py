# -*- coding: utf-8 -*-
"""站点重量复原小工具（skill 副本，依赖同目录 site_client.py）

背景（2026-11-07 实测）：`PUT /api/admin/products/{id}?autoSave=true` 是「缺字段填默认值」的
全量覆盖 —— body 里不带 `weight` 时服务端把重量重置成默认 0.3，并连带按新重量重算
`skus[].shippingFee`（0.2→0.3 时 7.43→8.8）。`Site.save()` 现在会自动回传当前重量，
所以新写的脚本不会再踩；但**旧脚本 / 旧写入留下的历史漂移**需要按快照复原。

用法：
  python restore_weight.py 4571 0.5          # 单件：把 4571 的重量设回 0.5
  python restore_weight.py --list rows.json  # 批量：rows = [[pid, weight], ...]
  python restore_weight.py --from-snap _wsnap.json 4571 4868
                                            # 从快照文件（{pid: [updatedAt, weight, fees]}）取原值

只改 weight（运费由站点自动重算），不动标题/图片/状态。写完立即回读校验。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_client import Site  # noqa: E402


def fees_of(p):
    return sorted({sk.get("shippingFee") for sk in (p.get("skus") or [])
                   if sk.get("shippingFee") is not None})


def restore(s, pid, weight, dry=False):
    before = s.product(pid)
    w0, f0 = before.get("weight"), fees_of(before)
    if dry:
        print("  [dry] %s  weight %s -> %s  fees=%s  (不写入)" % (pid, w0, weight, f0))
        return None
    s.save(pid, extra={"weight": weight})
    after = s.product(pid)
    w1, f1 = after.get("weight"), fees_of(after)
    ok = abs(float(w1 or 0) - float(weight)) < 1e-9
    print("  %s  weight %s -> %s (目标 %s) %s | fees %s -> %s | status=%s"
          % (pid, w0, w1, weight, "OK" if ok else "FAIL", f0, f1, after.get("status")))
    return {"pid": pid, "before": w0, "after": w1, "target": weight,
            "fees_before": f0, "fees_after": f1, "ok": ok}


def main(argv):
    dry = "--dry" in argv
    argv = [a for a in argv if a != "--dry"]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    jobs = []
    if argv[0] == "--list":
        jobs = [(int(p), float(w)) for p, w in json.load(open(argv[1], encoding="utf-8"))]
    elif argv[0] == "--from-snap":
        snap = json.load(open(argv[1], encoding="utf-8"))
        for pid in argv[2:]:
            entry = snap.get(str(pid))
            if not entry:
                print("  %s 快照里没有，跳过" % pid)
                continue
            jobs.append((int(pid), float(entry[1])))
    else:
        if len(argv) < 2:
            print(__doc__)
            return 2
        jobs = [(int(argv[0]), float(argv[1]))]

    s = Site()
    res = [restore(s, pid, w, dry) for pid, w in jobs]
    bad = [r for r in res if r and not r["ok"]]
    print("\n完成 %d 件，失败 %d 件" % (len(jobs), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
