"""临时工具：检查真实工程里各类键的存储形态与 schema 解析是否匹配。"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import schema, threemf  # noqa: E402

P = pathlib.Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
proj = threemf.ThreeMfProject.load(P)
keys = ["outer_wall_speed", "inner_wall_speed", "sparse_infill_speed", "top_surface_speed",
        "travel_speed", "default_acceleration", "outer_wall_acceleration",
        "sparse_infill_acceleration", "inner_wall_acceleration",
        "small_perimeter_speed", "vertical_shell_speed",
        "layer_height", "line_width", "outer_wall_line_width",
        "sparse_infill_density", "top_surface_pattern", "wall_loops",
        "fan_min_speed", "fan_max_speed", "retraction_length", "z_hop",
        "filament_max_volumetric_speed", "volumetric_speed_coefficients",
        "enable_support", "support_threshold_angle", "only_one_wall_top"]
for k in keys:
    raw = proj.settings.get(k)
    s = schema.spec(k)
    if s is None:
        print(f"{k:34s} <schema 无此键> raw={raw!r}")
        continue
    pv = schema.parse_value(s, raw)
    print(f"{k:34s} kind={s.kind:12s} raw={str(raw)[:40]:42s} parsed={pv!r}")
