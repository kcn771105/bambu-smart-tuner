"""生成一个「仿 Bambu Studio 工程」的测试用 3mf

用途：
  - 没有真机文件时，用来跑通「加载 → 优化 → 保存」全流程
  - 单元测试的固定夹具

用法：
    python tools/make_sample_3mf.py                    # 生成 samples/sample_x1c_pla.3mf
    python tools/make_sample_3mf.py --printer P1S --filament PETG --nozzle 0.6 --sliced
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import schema                       # noqa: E402
from core.rules_engine import load_rules      # noqa: E402

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
  <Default Extension="config" ContentType="text/xml"/>
  <Default Extension="json" ContentType="application/json"/>
  <Default Extension="png" ContentType="image/png"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0"
    Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Application">BambuStudio-01.09.00.00</metadata>
  <resources>
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="0" y="0" z="0"/><vertex x="20" y="0" z="0"/>
          <vertex x="0" y="20" z="0"/><vertex x="0" y="0" z="20"/>
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2"/><triangle v1="0" v2="1" v3="3"/>
          <triangle v1="1" v2="2" v3="3"/><triangle v1="2" v2="0" v3="3"/>
        </triangles>
      </mesh>
    </object>
  </resources>
  <build><item objectid="1"/></build>
</model>
"""

MODEL_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <object id="1">
    <metadata key="name" value="test_cube"/>
    <metadata key="extruder" value="1"/>
  </object>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <model_instance><metadata key="object_id" value="1"/><metadata key="instance_id" value="0"/></model_instance>
  </plate>
</config>
"""

SLICE_INFO = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <metadata key="printer_model" value="{printer_model}"/>
    <metadata key="nozzle_diameter" value="{nozzle}"/>
    <metadata key="filament_type" value="{filament}"/>
    <metadata key="prediction" value="3542"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="prediction" value="3542"/>
    <metadata key="weight" value="12.4"/>
  </plate>
</config>
"""

NOZZLE_VARIANT = {0.2: "0.20", 0.4: "0.40", 0.6: "0.60", 0.8: "0.80"}

# 故意写几个“用户工程里常见”的原始值，好让对比表有变化
OVERRIDES = {
    "layer_height": 0.2,
    "outer_wall_speed": 200,
    "inner_wall_speed": 300,
    "wall_loops": 2,
    "sparse_infill_density": 15,
    "sparse_infill_pattern": "grid",
    "sparse_infill_speed": 270,
    "inner_wall_acceleration": 8000,
    "travel_speed": 500,
    "fan_min_speed": 70,
}


def build_settings(printer_model: str, filament: str, nozzle: float,
                   rules: dict | None = None) -> dict[str, str]:
    rules = rules or load_rules()
    out: dict[str, str] = {}

    out["printer_model"] = printer_model
    out["printer_settings_id"] = printer_model
    out["printer_variant"] = NOZZLE_VARIANT.get(nozzle, "0.40")
    out["nozzle_diameter"] = json.dumps([f"{nozzle:.1f}"])
    out["filament_type"] = json.dumps([filament])
    out["filament_settings_id"] = json.dumps([f"Bambu {filament} @BBL"])
    out["filament_colour"] = json.dumps(["#FFFFFF"])
    out["filament_ids"] = json.dumps(["GFA00"])
    out["filament_diameter"] = json.dumps(["1.75"])

    for key, s in schema.PARAMS.items():
        raw = rules["defaults"].get(key)
        if raw is None:
            continue
        if key in OVERRIDES:
            raw = OVERRIDES[key]
        out[key] = schema.format_value(s, raw, None)

    # Bambu 里几个布尔值写的是字符串 true/false
    out["enable_overhang_speed"] = "1"
    out["reduce_crossing_wall"] = "1"
    out["enable_prime_tower"] = "1"
    return out


def build_sample(path: str | Path, *, printer_model: str = "Bambu Lab X1 Carbon",
                 filament: str = "PLA", nozzle: float = 0.4,
                 sliced: bool = False) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    settings = build_settings(printer_model, filament, nozzle)

    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", MODEL)
        z.writestr("Metadata/model_settings.config", MODEL_SETTINGS)
        z.writestr("Metadata/project_settings.config",
                   json.dumps(settings, ensure_ascii=False, indent=4))
        z.writestr("Metadata/plate_1.json", json.dumps({"bbox_all": [0, 0, 20, 20],
                                                       "filament_ids": [0],
                                                       "version": 2}))
        z.writestr("Metadata/plate_1.png", b"\x89PNG\r\n\x1a\n")
        if sliced:
            z.writestr("Metadata/slice_info.config",
                       SLICE_INFO.format(printer_model=printer_model,
                                         nozzle=f"{nozzle:.1f}", filament=filament))
            z.writestr("Metadata/plate_1.gcode", b"; fake gcode\n")
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="生成仿 Bambu Studio 工程 3mf")
    ap.add_argument("--out", default="samples/sample_x1c_pla.3mf")
    ap.add_argument("--printer", default="Bambu Lab X1 Carbon")
    ap.add_argument("--filament", default="PLA")
    ap.add_argument("--nozzle", type=float, default=0.4)
    ap.add_argument("--sliced", action="store_true", help="附带 slice_info / gcode，测试清理逻辑")
    a = ap.parse_args()
    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT / out
    p = build_sample(out, printer_model=a.printer, filament=a.filament,
                     nozzle=a.nozzle, sliced=a.sliced)
    print(f"已生成：{p}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
