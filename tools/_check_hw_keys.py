"""打印工程里的机器上限原始值（核对硬件钳制用）。

用法：
    python tools/_check_hw_keys.py [工程路径]
"""
from __future__ import annotations

import json
import sys
import zipfile

DEFAULT = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

KEYS = [
    "machine_max_speed_x", "machine_max_speed_y",
    "machine_max_acceleration_x", "machine_max_acceleration_y",
    "machine_max_acceleration_travel",
    "machine_max_jerk_x", "machine_max_jerk_y",
    "machine_max_speed_z", "machine_max_acceleration_z",
    "min_layer_height", "max_layer_height",
    "nozzle_volume", "nozzle_diameter",
    "filament_max_volumetric_speed", "filament_flow_ratio",
    "default_acceleration", "travel_acceleration",
    "outer_wall_acceleration", "top_surface_acceleration",
]


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    with zipfile.ZipFile(path) as zf:
        cfg = json.loads(zf.read("Metadata/project_settings.config").decode("utf-8"))
    for key in KEYS:
        print(f"{key:<36} {cfg.get(key)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
