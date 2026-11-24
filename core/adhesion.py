"""裙边（brim）定量决策：按模型实测尺寸算「倒不倒」，再定裙边多宽。

判定逻辑（都能手算复核）：

1. 倾覆指数 `tip = 高 ÷ √底面积 ×(1 + 偏移比)`
   - `高` 用模型 Z 高度（mm），`底面积` 用首层接触面积（mm²，来自 model_analysis 的 footprint）
   - `偏移比 = 重心偏移 ÷ 长边`，重心偏出底面中心越多越容易倒
   - 量纲：完全居中的 100×100×200 方块 → 200 ÷ 100 = 2.0；细高棒 10×10×100 → 100 ÷ 10 = 10
2. 小件判定：体积 < 8 cm³ 或 最短边 < 12 mm（打印时喷嘴一碰就走）
3. 分级给裙边宽度（再按耗材修正、按线宽取整到 0.5 mm）
4. 输出 `brim_width` / `brim_type` / `brim_object_gap`；倾覆风险低时不动用户的裙边设置

耗材修正：ABS/ASA 收缩大、翘边最凶 → ×1.25；PETG 粘板牢 → ×1.0 但间隙给 0.32；
TPU 撕不下来 → ×0.75；PLA → ×1.0。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# 倾覆指数门槛 → 裙边宽度（mm）
BANDS = (
    (8.0, 10.0),
    (5.0, 8.0),
    (3.0, 5.0),
    (1.8, 3.0),
)
SMALL_PART_MM3 = 8_000.0     # 8 cm³
SMALL_PART_MIN_EDGE = 12.0   # 最短边
WIDTH_MIN, WIDTH_MAX = 0.0, 20.0
LOOPS_MAX = 10

FILAMENT_WIDTH_MUL = {
    "ABS": 1.25,
    "ASA": 1.25,
    "PETG": 1.0,
    "PLA": 1.0,
    "TPU": 0.75,
}
FILAMENT_GAP = {
    "ABS": 0.30,
    "ASA": 0.30,
    "PETG": 0.32,
    "PLA": 0.28,
    "TPU": 0.35,
}


@dataclass
class AdhesionRow:
    metric: str
    measured: str
    formula: str
    conclusion: str

    def as_dict(self) -> dict:
        return {"metric": self.metric, "measured": self.measured,
                "formula": self.formula, "conclusion": self.conclusion}


@dataclass
class AdhesionDecision:
    tip: float = 0.0
    flip: float = 0.0
    small_part: bool = False
    width: float = 0.0
    gap: float = 0.0
    brim_type: str = ""
    ops: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    rows: list[AdhesionRow] = field(default_factory=list)


def _round05(x: float) -> float:
    return round(x * 2.0) / 2.0


def _max_edge(p) -> float:
    return max(float(getattr(p, "size_x", 0) or 0), float(getattr(p, "size_y", 0) or 0))


def _min_edge(p) -> float:
    xs = [v for v in (float(getattr(p, "size_x", 0) or 0),
                      float(getattr(p, "size_y", 0) or 0)) if v > 0]
    return min(xs) if xs else 0.0


def _h_f(p) -> tuple[float, float]:
    """(高, 底面积)。聚合对象上这两个派生属性可能为 0 → 逐件兜底。"""
    height = 0.0
    for name in ("size_z", "height"):
        try:
            height = max(height, float(getattr(p, name, 0) or 0))
        except (TypeError, ValueError):
            pass
    foot = 0.0
    objs = getattr(p, "objects", None) or []
    if objs:
        for o in objs:
            try:
                foot += float(getattr(o, "footprint", 0) or 0)
                height = max(height, float(getattr(o, "max_z", 0) or 0))
            except (TypeError, ValueError):
                continue
    if foot <= 1e-9:
        try:
            foot = float(getattr(p, "footprint", 0) or 0)
        except (TypeError, ValueError):
            foot = 0.0
    return height, foot


def _vol(p) -> float:
    try:
        v = float(getattr(p, "volume", 0) or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v > 0:
        return v
    total = 0.0
    for o in (getattr(p, "objects", None) or []):
        try:
            total += float(getattr(o, "volume", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def risk_of(p) -> tuple[float, float, bool]:
    """返回 (倾覆指数, 重心偏移比, 是否小件)。"""
    height, foot = _h_f(p)
    if height <= 0 or foot <= 0:
        return 0.0, 0.0, False
    offset = float(getattr(p, "centre_offset", 0) or 0)
    long_edge = _max_edge(p) or math.sqrt(foot)
    off_ratio = min(1.0, offset / long_edge) if long_edge > 0 else 0.0
    tip = height / math.sqrt(foot) * (1.0 + off_ratio)
    vol = _vol(p)
    small = vol < SMALL_PART_MM3 or (0 < _min_edge(p) < SMALL_PART_MIN_EDGE)
    return tip, off_ratio, small


def decide(profile, *, nozzle: float = 0.4, line_width: float = 0.42,
           layer_height: float = 0.2, filament_key: str = "",
           mode: str = "balanced", current: dict | None = None) -> AdhesionDecision:
    """单个模型（整个盘面的合并视图）的裙边决策。"""
    out = AdhesionDecision()
    if profile is None:
        return out

    cur = current or {}
    if str(cur.get("brim_type") or "") == "no_brim":
        out.reasons.append("工程里明确设了「不加裙边」，不动。")
        return out

    tip, off_ratio, small = risk_of(profile)
    out.tip, out.flip, out.small_part = tip, off_ratio, small
    if tip <= 0:
        out.reasons.append("没有可用的底面/高度数据，裙边不动。")
        return out

    height, foot = _h_f(profile)

    base = 0.0
    why = ""
    for limit, width in BANDS:
        if tip >= limit:
            base, why = width, f"倾覆指数 {tip:.2f} ≥ {limit:g}"
            break
    if base <= 0 and small:
        base, why = 3.0, f"小件（体积或者最短边偏小）"

    if base <= 0:
        out.reasons.append(
            f"倾覆指数 {tip:.2f}（高 {height:.0f} mm ÷ √底面积 {math.sqrt(foot):.1f} mm）"
            f"不高，裙边保持工程原值 {_fmt(current, 'brim_width')}。")
        out.rows.append(AdhesionRow(
            "裙边 brim_width",
            f"倾覆指数 {tip:.2f}（高 {height:.0f} mm ／ 底面积 {foot:.0f} mm²）",
            "高 ÷ √底面积 ×(1+重心偏移比)",
            f"低于最低门槛 1.8，不改（当前 {_fmt(current, 'brim_width')}）"))
        return out

    fk = str(filament_key or "").upper()
    mul = FILAMENT_WIDTH_MUL.get(fk, 1.0)
    width = _round05(base * mul)
    width = max(WIDTH_MIN, min(WIDTH_MAX, width))

    cur = 0.0
    try:
        cur = float((current or {}).get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    # 用户原本就给了更宽的裙边 → 不往回压（他可能是为了别的原因加的）
    if cur > width:
        out.reasons.append(f"工程里已有 {cur:g} mm 裙边，比算出的 {width:g} mm 更宽，保留原值。")
        width = cur
    else:
        out.ops["brim_width"] = {"set": width}
        if width > 0:
            out.ops["brim_type"] = {"set": "outer_only"}
            out.ops["brim_object_gap"] = {"set": FILAMENT_GAP.get(fk, 0.3)}
        out.reasons.append(
            f"{why}（重心偏移比 {off_ratio:.2f}、{'小件' if small else '非小件'}、"
            f"{fk or '未知耗材'} 修正 ×{mul:g}）→ 裙边 {cur:g} → {width:g} mm，只在外圈。")

    loops = int(min(LOOPS_MAX, max(1, round(width / max(line_width, 0.1)))))
    out.width, out.gap = width, FILAMENT_GAP.get(fk, 0.3)
    out.brim_type = "outer_only"
    out.rows.append(AdhesionRow(
        "裙边 brim_width",
        f"高 {height:.0f} mm ／ 底面积 {foot:.0f} mm² ／ 重心偏移 {off_ratio:.2f} ／ 体积 "
        f"{float(getattr(profile, 'volume', 0) or 0) / 1000:.1f} cm³",
        "倾覆指数 = 高 ÷ √底面积 ×(1+偏移)；≥8→10、≥5→8、≥3→5、≥1.8→3 mm；小件保底 3",
        f"倾覆指数 {tip:.2f} → 基准 {base:g} mm × 耗材修正 {mul:g} = {out.width:g} mm"
        f"（约 {loops} 圈，间隙 {out.gap:g} mm）"))
    return out


def _fmt(cur: dict | None, key: str) -> str:
    try:
        v = (cur or {}).get(key)
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return "—"


def tune(profile, *, nozzle: float = 0.4, line_width: float = 0.42,
         layer_height: float = 0.2, filament_key: str = "",
         mode: str = "balanced", current: dict | None = None):
    """多件盘面：逐件算，取最保守（最宽）的那个。返回 (ops, notes, rows)。"""
    if profile is None:
        return {}, [], []
    objs = getattr(profile, "objects", None) or []
    if not objs:
        d = decide(profile, nozzle=nozzle, line_width=line_width,
                   layer_height=layer_height, filament_key=filament_key,
                   mode=mode, current=current)
        return d.ops, d.reasons, d.rows

    best = None
    rows: list[AdhesionRow] = []
    notes: list[str] = []
    for i, obj in enumerate(objs, 1):
        d = decide(obj, nozzle=nozzle, line_width=line_width,
                   layer_height=layer_height, filament_key=filament_key,
                   mode=mode, current=current)
        if d.width > 0 and (best is None or d.width > best.width):
            best = d
        for r in d.rows:
            rows.append(AdhesionRow(f"件{i} {r.metric}", r.measured, r.formula, r.conclusion))
        if d.width > 0:
            notes.append(f"件{i}：倾覆指数 {d.tip:.2f} → 建议裙边 {d.width:g} mm。")

    if best is None:
        notes.append("所有件倾覆风险都低，裙边保持工程原值。")
        return {}, notes, rows
    if str((current or {}).get("brim_type") or "") == "no_brim":
        notes.append("工程里明确设了「不加裙边」，不动。")
        return {}, notes, rows
    cur = 0.0
    try:
        cur = float((current or {}).get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    if cur > best.width:
        notes.append(f"工程里已有 {cur:g} mm 裙边，比算出的 {best.width:g} mm 更宽，保留原值。")
        return {}, notes, rows
    return best.ops, best.reasons + notes, rows
