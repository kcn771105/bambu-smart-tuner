"""看看工程里「打印板 / 板面」相关都有哪些键、值是什么。"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import threemf  # noqa: E402

PROJ = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

KEYS = [k for k in (
    "curr_bed_type", "bed_shape", "printable_area", "printable_height",
    "wrapping_exclude_area", "bed_custom_model", "bed_custom_texture",
    "bed_model", "bed_texture", "nozzle_diameter", "nozzle_volume",
    "printer_model", "printer_variant", "print_extruder_variant",
    "cool_plate_temp", "cool_plate_temp_initial_layer",
    "eng_plate_temp", "eng_plate_temp_initial_layer",
    "hot_plate_temp", "hot_plate_temp_initial_layer",
    "textured_plate_temp", "textured_plate_temp_initial_layer",
    "supertack_plate_temp", "supertack_plate_temp_initial_layer",
    "filament_type", "filament_max_volumetric_speed",
    "initial_layer_print_height", "brim_type", "brim_width",
    "elefant_foot_compensation", "z_offset", "first_layer_flow_ratio",
)]


def main() -> int:
    proj = threemf.ThreeMfProject.load(PROJ)
    s = proj.settings
    print("键数", len(s))
    for k in KEYS:
        if k in s:
            print(f"  {k} = {s[k]}")
        else:
            print(f"  {k} = <不存在>")
    print("\n含 plate / bed 的所有键：")
    for k in sorted(s):
        if "plate" in k.lower() or k.lower().startswith("bed") or "exclude" in k:
            print(f"  {k} = {s[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
