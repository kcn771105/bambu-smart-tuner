"""生成一份优化后的 3mf 并做文本级逐键 diff（人工核对用）。

用法：
    python tools/_write_optimized.py [工程路径] [模式] [输出路径]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import hardware, model_analysis, rules_engine, threemf  # noqa: E402

DEFAULT = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    mode = sys.argv[2] if len(sys.argv) > 2 else "balanced"
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(r"%TEMP%") / "tuner_out.3mf"

    eng = rules_engine.build_engine()
    proj = threemf.ThreeMfProject.load(src)
    orig = dict(proj.settings)
    hw = hardware.read(proj)
    prof = model_analysis.analyse(proj)

    res = eng.optimize(orig, printer_key=hw.printer_model or "P2S",
                       filament_key=(hw.filament_type or "PETG").upper(),
                       nozzle=hw.nozzle_diameter or 0.4,
                       mode_key=mode, model_profile=prof, hardware_info=hw)
    proj.apply(res.write_values)
    proj.save_as(out)
    print(f"已写出：{out}（写入 {len(res.write_values)} 项）")

    back = threemf.ThreeMfProject.load(out)
    diff = [(k, orig.get(k), back.settings.get(k))
            for k in sorted(set(orig) | set(back.settings))
            if orig.get(k) != back.settings.get(k)]
    print(f"实际变化 {len(diff)} 键：")
    for k, a, b in diff:
        print(f"  {k:<46} {a!r}  →  {b!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
