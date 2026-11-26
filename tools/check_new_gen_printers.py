"""验收：新机型识别 + 用真实工程跑 5 个新机型 × 6 档（改动数 / 时长 / 越界）。"""

import io
import json
import sys

sys.path.insert(0, ".")

from core import detector, rules_engine, schema, threemf  # noqa: E402

RULES = json.load(io.open("rules/BambuRules.json", encoding="utf-8-sig"))
engine = rules_engine.RulesEngine(RULES)
PROJ = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

print("=== 机型下拉（%d 项）" % len(engine.printer_choices()))
for i, (k, label) in enumerate(engine.printer_choices(), 1):
    print(f"  {i:2}. {k:8} {label}")


class FakeProject:
    is_sliced = False

    def __init__(self, model: str):
        self.settings = {"printer_model": model}
        self.meta = {}

    def list_len(self, key: str) -> int:
        return 1


print("\n=== 识别测试（伪工程里只放 printer_model）")
for name in ("Bambu Lab X2D", "Bambu Lab H3C", "Bambu Lab A2L", "Bambu Lab P3C", "Bambu Lab H2C"):
    det = detector.detect(FakeProject(name), RULES)
    print(f"  {name:20} -> {det.printer_key:8} {det.printer_label}")

prj = threemf.ThreeMfProject.load(PROJ)
cur = dict(prj.settings)
print(f"\n=== 真实工程 {PROJ.split(chr(92))[-1]}：{len(cur)} 键")

MODES = ("strength", "quality", "balanced", "draft", "fine", "ultrafine")
print(f"{'机型':6}" + "".join(f"{m:>16}" for m in MODES))
for k in ("A2L", "H2C", "H3C", "P3C", "X2D"):
    cells = []
    for mode in MODES:
        res = engine.optimize(cur, printer_key=k, filament_key="PETG", nozzle=0.4, mode_key=mode)
        n = sum(1 for r in res.rows if r.changed and r.will_write)
        d = getattr(res, "time_delta_pct", 0.0) or 0.0
        bad = 0
        for key, v in res.write_values.items():
            spec = schema.PARAMS.get(key)
            if spec is None or spec.kind in (schema.ENUM, schema.BOOL, schema.ENUM_ARRAY):
                continue
            try:
                num = float(str(v).rstrip("%"))
            except ValueError:
                continue
            if not (spec.vmin <= num <= spec.vmax):
                bad += 1
        cells.append(f"{n:>4}项/{d:+6.1f}%{'!' + str(bad) if bad else ''}")
    print(f"{k:6}" + "".join(f"{c:>16}" for c in cells))
