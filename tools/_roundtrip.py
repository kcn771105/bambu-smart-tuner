"""复现「导出后参数没生效」：写出 → 重新打开 → 逐项比对。

同时看工程里这些值的原始 JSON 类型（Bambu Studio 期望字符串还是数字）。
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import detector, hardware, rules_engine, threemf  # noqa: E402

PROJ = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
OUT = Path(r"F:\deep seek\bambu_smart_tuner\dist\_roundtrip.3mf")


def dump_types(path: Path, keys: list[str]) -> None:
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith("project_settings.config"))
        raw = z.read(name)
    data = json.loads(raw)
    print(f"--- {path.name}  ({len(data)} 键, settings 大小 {len(raw)} bytes)")
    for k in keys:
        if k in data:
            print(f"  {k!r:38} = {data[k]!r:28} type={type(data[k]).__name__}")


KEYS = ["layer_height", "wall_loops", "outer_wall_speed", "sparse_infill_density",
        "sparse_infill_pattern", "initial_layer_print_height", "inner_wall_speed",
        "default_acceleration", "nozzle_diameter", "printable_area",
        "filament_max_volumetric_speed", "curr_bed_type", "brim_width"]


def main() -> int:
    print("=== 原始工程里的原始类型")
    dump_types(PROJ, KEYS)

    proj = threemf.ThreeMfProject.load(PROJ)
    rules = rules_engine.load_rules()
    det = detector.detect(proj, rules)
    hw = hardware.read(proj)
    eng = rules_engine.RulesEngine(rules)
    res = eng.optimize(proj.settings, printer_key=det.printer_key,
                       filament_key=det.filament_key, nozzle=0.4,
                       mode_key="balanced", hardware_info=hw)

    print("\n=== UI 里会显示的优化后值（res.write_values）")
    for k in KEYS:
        if k in res.write_values:
            print(f"  {k:34} -> {res.write_values[k]!r}")

    written, skipped = proj.apply(res.write_values)
    print(f"\napply(): 写入 {len(written)}，跳过 {len(skipped)}")
    out = proj.save_as(OUT)
    print("save_as ->", out)

    print("\n=== 重新打开新文件，读回来的值")
    again = threemf.ThreeMfProject.load(out)
    bad = []
    for k, v in res.write_values.items():
        got = again.settings.get(k)
        if str(got) != str(v):
            bad.append((k, v, got)
                       )
    print(f"  write_values 共 {len(res.write_values)} 项，不一致 {len(bad)} 项")
    for k, want, got in bad[:25]:
        print(f"  ✗ {k:34} 期望 {want!r}  实际 {got!r}")
    dump_types(out, KEYS)

    print("\n=== ZIP 结构对照")
    with zipfile.ZipFile(PROJ) as a, zipfile.ZipFile(out) as b:
        na, nb = set(a.namelist()), set(b.namelist())
        print("  原文件条目", len(na), "新文件条目", len(nb))
        print("  只在原文件:", sorted(na - nb)[:10])
        print("  只在新文件:", sorted(nb - na)[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
