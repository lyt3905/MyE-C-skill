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
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
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
    day1 = datetime(2026, 9, 30, 10, 0, 0)
    st3 = {}
    got3 = [hk.next_code(hcfg, hledger, st3)[0] for _ in range(3)]
    check("默认模式出「日期时间-序号」（前缀随当天日期+时分秒）",
          all(re.fullmatch(r"\d{14}-\d{5}", c) for c in got3)
          and got3[0] == hk.compose(hk.render_prefix({}), "-", 1, 5)
          and [c.rsplit("-", 1)[1] for c in got3] == ["00001", "00002", "00003"], str(got3))

    # 12.4 日期前缀：隔天换日期、序号重新从 1 开始（用固定时间避免跨零点假失败）
    std = {}
    d1 = [hk.next_plain(hcfg, std, now=day1) for _ in range(3)]
    d2 = [hk.next_plain(hcfg, std, now=day1 + timedelta(days=1)) for _ in range(2)]
    check("隔天自动换日期、序号归 1",
          d1 == ["20260930100000-00001", "20260930100000-00002", "20260930100000-00003"]
          and d2 == ["20261001100000-00001", "20261001100000-00002"], f"{d1} / {d2}")

    # 12.4b 编号精确到秒，但跨秒后序号必须继续递增（计数器按天分组，不能每秒归 1）
    ss = {}
    ds = [hk.next_plain(hcfg, ss, now=day1 + timedelta(seconds=3 * i)) for i in range(3)]
    check("跨秒后序号不重置（计数器按天分组）",
          ds == ["20260930100000-00001", "20260930100003-00002", "20260930100006-00003"], str(ds))

    # 12.5 固定前缀连续递增；连接词与位数可改；空前缀只出流水号
    stf = {"prefix": "MTS", "sep": "_", "width": 4}
    gf = [hk.next_plain(hcfg, stf, now=day1) for _ in range(2)]
    check("自定义前缀/连接词/位数", gf == ["MTS_0001", "MTS_0002"], str(gf))
    snp = {"prefix": "", "width": 3}
    gnp = [hk.next_plain(hcfg, snp, now=day1) for _ in range(2)]
    check("前缀留空时只出流水号", gnp == ["001", "002"], str(gnp))
    stp = {"prefix": "MTS-{yy}{mm}{dd}"}
    check("前缀占位符 {yy}{mm}{dd}",
          hk.next_plain(hcfg, stp, now=day1) == "MTS-260930-00001",
          hk.next_plain(hcfg, {"prefix": "MTS-{yy}{mm}{dd}"}, now=day1))
    check("--from 把下一个编号设为 N（不改已出的历史）",
          hk.compose("", "", 1200, 5) == "01200", "compose 基本拼接")

    st4 = {"mode": "sku", "base": None, "queue_index": 0}
    sku4, err4 = hk.next_code(hcfg, hledger, st4)
    check("SKU 模式但缺规格时报错", sku4 is None and bool(err4) and "--set" in err4, f"{sku4} / {err4}")

    n_before = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    hk.next_code(hcfg, hledger, {})
    n_after = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    check("纯流水号模式不写台账", n_before == n_after, f"{n_before} -> {n_after}")

    prev = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    hk.next_code(hcfg, hledger, {"mode": "sku", "spec": hk.parse_spec(hcfg, "ss86"), "base": None},
                 commit=False)
    after = len(json.loads(hled.read_text(encoding="utf-8"))["items"])
    check("预览（commit=False）不写台账", prev == after, f"{prev} -> {after}")

    print("\n13. 守护进程重读磁盘（外部改动即时生效，不撞号）")
    # 13.1 Ledger.reload：另一个「进程」写入的新记录必须能被看见
    rled = tmp / "reload_led.json"
    writer = core.Ledger(rled)
    writer.add({"sku": "A-0001", "base": "A-0001"})
    writer.save(backup=False)
    holder = core.Ledger(rled)                     # 模拟常驻进程持有的旧副本
    writer.add({"sku": "A-0002", "base": "A-0002"})
    writer.save(backup=False)
    holder.reload()
    check("reload 后能看见外部写入的新记录", len(holder.items) == 2, str(len(holder.items)))

    # 13.2 daemon.refresh：外部 --set 换规格后，再按 Ctrl+B 必须出「新」规格的号
    stfile = tmp / "hk_state.json"
    saved_state_file = hk.STATE_FILE
    try:
        hk.STATE_FILE = stfile
        hk.save_state({"mode": "sku", "spec": hk.parse_spec(hcfg, "ss86 r"),
                       "base": None, "queue_index": 0})

        class _Args:
            quiet = True
            copy_only = True
            settle_ms = 180

        daemon = hk.HotkeyDaemon(hcfg, core.Ledger(tmp / "hk_daemon_led.json"), _Args())
        daemon.refresh()
        before, _ = hk.next_code(hcfg, daemon.ledger, daemon.state)

        hk.save_state({"mode": "sku", "spec": hk.parse_spec(hcfg, "cmt af dw g"),
                       "base": None, "queue_index": 0})
        daemon.refresh()
        after, _ = hk.next_code(hcfg, daemon.ledger, daemon.state)
        check("外部 --set 后守护进程立即换到新规格",
              before.startswith("MTS-TF-SS86") and after.startswith("CMT-AF-DW"),
              f"{before} -> {after}")

        hk.save_state(daemon.state)                # 模拟 do_press 落盘
        disk_series = json.loads(stfile.read_text(encoding="utf-8"))["spec"]["series"]
        check("出号落盘后磁盘规格仍是新值（没被内存旧副本覆盖）", disk_series == "DW", disk_series)
    finally:
        hk.STATE_FILE = saved_state_file

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for f in FAIL:
            print("  FAILED: " + f)
    print(f"临时目录：{tmp}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
