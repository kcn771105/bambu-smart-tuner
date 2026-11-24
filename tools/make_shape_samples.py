"""生成几个不同形状的测试 3mf：齿轮(小)、花瓶(高瘦)、盒子(扁平板)、塔(小脚高塔+悬垂)。

用法：python tools/make_shape_samples.py
输出：samples/shape_*.3mf
"""

from __future__ import annotations

import json
import math
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.rules_engine import load_rules   # noqa: E402
from make_sample_3mf import CONTENT_TYPES, RELS, MODEL_SETTINGS, build_settings  # noqa: E402


def _model_xml(verts, tris) -> str:
    v = "".join(f'<vertex x="{x:.3f}" y="{y:.3f}" z="{z:.3f}"/>' for x, y, z in verts)
    t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US"
  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
  <metadata name="Application">BambuStudio-01.09.00.00</metadata>
  <resources>
    <object id="1" type="model">
      <mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh>
    </object>
  </resources>
  <build><item objectid="1"/></build>
</model>
"""


def box(w: float, d: float, h: float, ox=0.0, oy=0.0):
    verts = [
        (ox, oy, 0), (ox + w, oy, 0), (ox + w, oy + d, 0), (ox, oy + d, 0),
        (ox, oy, h), (ox + w, oy, h), (ox + w, oy + d, h), (ox, oy + d, h),
    ]
    tris = [
        (0, 2, 1), (0, 3, 2),          # 底
        (4, 5, 6), (4, 6, 7),          # 顶
        (0, 1, 5), (0, 5, 4),
        (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6),
        (3, 0, 4), (3, 4, 7),
    ]
    return verts, tris


def cylinder(r: float, h: float, seg: int = 48, cx: float = 0.0, cy: float = 0.0):
    verts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a), 0.0))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a), h))
    tris = []
    for i in range(seg):
        j = (i + 1) % seg
        tris.append((i, j, seg + i))
        tris.append((j, seg + j, seg + i))
    # 封底/封顶（扇形）
    for i in range(1, seg - 1):
        tris.append((0, i + 1, i))
        tris.append((seg, seg + i, seg + i + 1))
    return verts, tris


def gear(r_out: float, h: float, teeth: int = 16):
    """简单齿轮：外圈锯齿 + 内孔，靠外轮廓起伏产生薄壁与悬垂。"""
    seg = teeth * 4
    verts = []
    inner_r = r_out * 0.45
    for i in range(seg):
        a = 2 * math.pi * i / seg
        phase = i % 4
        rr = r_out if phase in (1, 2) else inner_r
        verts.append((rr * math.cos(a), rr * math.sin(a), 0.0))
    for i in range(seg):
        a = 2 * math.pi * i / seg
        phase = i % 4
        rr = r_out if phase in (1, 2) else inner_r
        verts.append((rr * math.cos(a), rr * math.sin(a), h))
    tris = []
    for i in range(seg):
        j = (i + 1) % seg
        tris.append((i, j, seg + i))
        tris.append((j, seg + j, seg + i))
    for i in range(seg):
        j = (i + 1) % seg
        tris.append((i, j, i))
        tris.append((seg + i, seg + j, seg + i))
    # 中心孔
    hole = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        hole.append((r_out * 0.18 * math.cos(a), r_out * 0.18 * math.sin(a), 0.0))
    base = len(verts)
    verts += hole
    verts += [(x, y, h) for x, y, z in hole]
    for i in range(seg):
        j = (i + 1) % seg
        tris.append((base + i, base + j, base + seg + i))
        tris.append((base + j, base + seg + j, base + seg + i))
    return verts, tris


def tower_with_overhang(w: float, h: float, arm: float):
    """柱体 + 悬挑横臂：制造大面积朝下的悬垂，触发支撑策略。"""
    v1, t1 = box(w, w, h)
    v2, t2 = box(w * 3.0, w, w * 0.9, ox=-w, oy=0.0)
    off = len(v1)
    verts = v1 + [(x, y, z + h - w * 0.9) for x, y, z in v2]
    tris = t1 + [(a + off, b + off, c + off) for a, b, c in t2]
    return verts, tris


SHAPES = {
    "shape_gear_small": (gear(18.0, 8.0, 18), "小齿轮（薄壁 + 细节）"),
    "shape_vase_tall": (cylinder(30.0, 190.0, 56), "高瘦花瓶（晃动风险）"),
    "shape_plate_flat": (box(160.0, 120.0, 8.0), "扁平板（翘边风险）"),
    "shape_tower_overhang": (tower_with_overhang(20.0, 120.0, 60.0), "高塔带悬挑（支撑重）"),
}


def build(path: Path, geom, name: str) -> Path:
    verts, tris = geom
    settings = build_settings("Bambu Lab X1 Carbon", "PLA", 0.4)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", _model_xml(verts, tris))
        z.writestr("Metadata/model_settings.config", MODEL_SETTINGS)
        z.writestr("Metadata/project_settings.config",
                   json.dumps(settings, ensure_ascii=False, indent=4))
        z.writestr("Metadata/plate_1.json", json.dumps({"version": 2}))
        z.writestr("Metadata/plate_1.png", b"\x89PNG\r\n\x1a\n")
    return path


def main() -> int:
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    for stem, (geom, desc) in SHAPES.items():
        p = build(out / f"{stem}.3mf", geom, desc)
        print(f"{desc:24s} → {p.name}  ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
