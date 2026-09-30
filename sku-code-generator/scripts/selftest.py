#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SKU 生成器冒烟自测 —— 改完 sku_gen.py 跑一遍，确认没改坏。

    python scripts/selftest.py

覆盖：字典解析 / 歧义拦截 / 台账防重 / 复用不回写计数器 / 批量与失败行 / 数字变体 /
缺列默认值 / 台账导出。全部在临时目录里跑，不碰正式台账。
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE / "sku_gen.py"
PY = sys.executable

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (f"  -> {detail}" if detail and not cond else ""))


def run(args, ledger, **kw):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([PY, str(GEN), "--ledger", str(ledger)] + args,
                       capture_output=True, text=True, encoding="utf-8", env=env, **kw)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def load(ledger):
    return json.loads(Path(ledger).read_text(encoding="utf-8"))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sku_selftest_"))
    led = tmp / "led.json"
    print(f"临时目录：{tmp}\n")

    print("1. 单条生成 + 多变体共用一个流水号")
    rc, o = run(["-s", "mts", "-c", "tf", "-e", "s86", "-v", "r,b", "-n", "SS86 擎天柱"], led)
    skus = [r["sku"] for r in load(led)["items"]]
    check("生成 2 条 SKU", rc == 0 and skus == ["MTS-TF-SS86-0001-RD", "MTS-TF-SS86-0001-BL"], str(skus))

    print("\n2. 重跑同名商品：复用流水号、不新增")
    rc, o = run(["-s", "mts", "-c", "tf", "-e", "s86", "-v", "r,b", "-n", "SS86 擎天柱"], led)
    check("台账条数不变", len(load(led)["items"]) == 2)
    check("报告已存在", "已存在" in o and "没有新增" in o, o[-200:])

    print("\n3. 同系列新品：流水号 +1")
    run(["-s", "mts", "-c", "tf", "-e", "s86", "-n", "SS86 大黄蜂"], led)
    skus = [r["sku"] for r in load(led)["items"]]
    check("得到 0002", "MTS-TF-SS86-0002" in skus, str(skus))

    print("\n4. 回归：复用旧流水号后，计数器不能被回写变小")
    run(["-s", "mts", "-c", "tf", "-e", "s86", "-v", "g", "-n", "SS86 擎天柱"], led)
    run(["-s", "mts", "-c", "tf", "-e", "s86", "-n", "SS86 声波"], led)
    skus = [r["sku"] for r in load(led)["items"]]
    check("新商品拿到 0003（不是 0002）", "MTS-TF-SS86-0003" in skus, str(skus))
    check("计数器仍为 3", load(led)["counters"].get("MTS|SS86") == 3, str(load(led)["counters"]))

    print("\n5. 歧义速记符必须被拦下，不能瞎猜")
    rc, o = run(["-s", "mts", "-c", "tf", "-e", "s", "-n", "x"], led)
    check("退出码 1", rc == 1, str(rc))
    check("列出全部候选", all(k in o for k in ("SS86", "SXX", "ST")), o)

    print("\n6. 未知速记符报错")
    rc, o = run(["-s", "mts", "-c", "tf", "-e", "zzz", "-n", "x"], led)
    check("退出码 1", rc == 1, str(rc))

    print("\n7. 纯数字色号透传")
    run(["-s", "pst", "-c", "md", "-e", "msb", "-v", "01,02", "-n", "MSB 合金"], led)
    skus = [r["sku"] for r in load(led)["items"]]
    check("生成 01/02", "PST-MD-MSB-0001-01" in skus and "PST-MD-MSB-0001-02" in skus, str(skus))

    print("\n8. 批量：混合正常行与失败行，缺列走默认值")
    src = tmp / "in.csv"
    src.write_text("名称,速记\n红蜘蛛,mts tf ss86 k\n声波,ss86 k\n坏行,mts tf zzz k\n",
                   encoding="utf-8-sig")
    out = tmp / "out.csv"
    rc, o = run(["-i", str(src), "-o", str(out)], led)
    rows = list(csv.reader(out.open(encoding="utf-8-sig")))
    statuses = [r[9] for r in rows[1:]]
    check("退出码 0", rc == 0)
    check("输出 3 行（含 1 行失败）", len(rows) == 4, str(len(rows)))
    check("失败行被标记", statuses.count("失败") == 1, str(statuses))
    check("缺列默认值生效（MTS/TF）", all(r[1].startswith("MTS-TF-") or r[1] == "" for r in rows[1:]),
          str([r[1] for r in rows[1:]]))

    print("\n9. 台账导出 / 查询")
    exp = tmp / "exp.csv"
    rc, o = run(["--export", str(exp)], led)
    n = len(list(csv.reader(exp.open(encoding="utf-8-sig")))) - 1
    check("导出条数与台账一致", rc == 0 and n == len(load(led)["items"]), f"{n} vs {len(load(led)['items'])}")
    for flag in ("--list", "--stats"):
        rc, _ = run([flag], led)
        check(f"{flag} 正常退出", rc == 0)
    rc, o = run(["--find", "SS86"], led)
    check("--find 命中", rc == 0 and "命中" in o, o[:120])

    print("\n10. dry-run 不写台账")
    before = load(led)["items"]
    run(["-s", "mts", "-c", "af", "-e", "jcs", "--dry-run"], led)
    check("台账未变", len(load(led)["items"]) == len(before))

    print("\n11. 热键：规格解析")
    sys.path.insert(0, str(HERE))
    import sku_hotkey as hk
    cfg0 = __import__("sku_gen").Config(GEN.parent.parent / "config" / "sku_config.json")
    cases = [("mts tf ss86 r,b", "SS86", ["RD", "BL"]),
             ("ss86 r", "SS86", ["RD"]),
             ("62店 md msb 01", "MSB", ["01"]),
             ("jcs w", "JCS", ["WH"])]
    for text, series, variants in cases:
        sp = hk.parse_spec(cfg0, text)
        got_v = sp["variants"] if sp else None
        ok_case = sp is not None and got_v == variants and (series is None or sp["series"] == series)
        check(f"解析 {text!r} → {variants}", ok_case, str(sp))
    sp = hk.parse_spec(cfg0, "ss86 w")
    check("'ss86 w' 的 w 判为变体 WH 而非系列 WFC",
          sp is not None and sp["series"] == "SS86" and sp["variants"] == ["WH"], str(sp))
    bad = [t for t in ("SS86 擎天柱", "随便一段话", "mts tf", "zzz", "s", "w")
           if hk.parse_spec(cfg0, t)]
    check("非规格文本全部被拒（含只有变体没有系列的 'w'）", not bad, str(bad))

    print("\n12. 热键：连按出号与变体轮转")
    hled = tmp / "hk_led.json"
    core = __import__("sku_gen")
    hcfg = core.Config(GEN.parent.parent / "config" / "sku_config.json")
    hledger = core.Ledger(hled)
    st = {"spec": hk.parse_spec(hcfg, "jcs b,bk"), "base": None, "queue_index": 0}
    got = [hk.next_sku(hcfg, hledger, st)[0] for _ in range(3)]
    check("同一流水号先出齐变体再进新号",
          got == ["MTS-TF-JCS-0001-BL", "MTS-TF-JCS-0001-BK", "MTS-TF-JCS-0002-BL"], str(got))
    st2 = {"spec": hk.parse_spec(hcfg, "ss86"), "base": None, "queue_index": 0}
    got2 = [hk.next_sku(hcfg, hledger, st2)[0] for _ in range(2)]
    check("无变体规格每次都是新流水号",
          got2 == ["MTS-TF-SS86-0001", "MTS-TF-SS86-0002"], str(got2))
    st3 = {"base": None, "queue_index": 0}
    sku3, err3 = hk.next_sku(hcfg, hledger, st3)
    check("未设规格时拒绝出号并给提示", sku3 is None and err3 and "--set" in err3, f"{sku3} / {err3}")
    prev = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    hk.next_sku(hcfg, hledger, {"spec": hk.parse_spec(hcfg, "ss86"), "base": None}, commit=False)
    after = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    check("预览（commit=False）不写台账", prev == after, f"{prev} -> {after}")

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for f in FAIL:
            print("  FAILED: " + f)
    print(f"临时目录：{tmp}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
