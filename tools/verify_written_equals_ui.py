"""逐项核对：UI 表格里显示「写入=是」的每一行，在写出的 3mf 里是否真的一致。

这是用户 m05100 第 1 条 BUG 的验收口径：
「保证写入新3mf的切片参数和UI展示的优化后参数保持一致」。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, rules_engine, schema, threemf  # noqa: E402

PROJ = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
OUT_DIR = ROOT / "dist" / "_verify"
MODES = ("balanced", "strength", "quality", "draft", "fine", "ultrafine")


def one(mode: str) -> int:
    proj = threemf.ThreeMfProject.load(PROJ)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)
    res = eng.optimize(proj.settings, printer_key=det.printer_key,
                       filament_key=det.filament_key, nozzle=0.4,
                       mode_key=mode, hardware_info=hw)

    should = [r for r in res.rows if r.changed and r.will_write]
    written, skipped = proj.apply(res.write_values)
    out = proj.save_as(OUT_DIR / f"verify_{mode}.3mf")

    again = threemf.ThreeMfProject.load(out)
    bad: list[str] = []
    for row in should:
        spec = schema.PARAMS.get(row.key)
        want = res.write_values.get(row.key)
        got = again.settings.get(row.key)
        if got is None:
            bad.append(f"{row.key}: 文件里没有这个键")
            continue
        # 用同一套 parse 比较语义值，避免 "162" vs 162 vs ["162",...] 的形态差异误报
        try:
            v_want = schema.parse_value(spec, want) if spec else want
        except Exception:
            v_want = want
        try:
            v_got = schema.parse_value(spec, got) if spec else got
        except Exception:
            v_got = got
        if isinstance(v_want, float) and isinstance(v_got, float):
            if abs(v_want - v_got) > 1e-6:
                bad.append(f"{row.key}: UI {v_want!r} != 文件 {v_got!r}")
        elif v_want != v_got:
            bad.append(f"{row.key}: UI {v_want!r} != 文件 {v_got!r}")

    print(f"[{mode:9}] UI 写入行 {len(should):3} / apply {len(written):3} / "
          f"文件核对不一致 {len(bad)}")
    for b in bad[:12]:
        print("     ✗", b)
    return len(bad)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = sum(one(m) for m in MODES)
    print("\n合计不一致：", total)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
