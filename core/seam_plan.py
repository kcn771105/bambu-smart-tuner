"""接缝（seam）与圆柱体斜接缝。

用户反馈第 4 条：「这个软件可以让圆柱体的接缝光滑吗」。

为什么圆柱体接缝最难看
----------------------
Bambu / Orca 的接缝是「每层外壁的起止点」。方盒件的接缝藏在棱角上，
而圆柱件没有棱角可藏——对齐接缝会在侧面留下一条竖直的凹线；
随机接缝则变成麻点。官方为此提供了「斜接缝 / scarf joint」：

    seam_slope_type = external     外壁做斜切，把接缝斜面化（看起来几乎看不见）
    scarf_angle_threshold          只在角度平缓处斜切（避免尖角处糊料）
    seam_slope_start_height        从第 N% 高度才开始斜切（底部实心段不做）
    seam_slope_steps               斜切分几层过渡
    seam_slope_gap                 斜切首尾的间隙
    apply_scarf_seam_on_circles    ← 关键开关：**圆形轮廓也做斜接缝**

默认 `apply_scarf_seam_on_circles = 1` 在官方预设里是开的，但很多工程里
被拷贝成 0（尤其是从旧工程长期沿用的档），于是圆柱件的斜接缝一直不生效。
这一层做的就是：**认出圆形件之后，把斜接缝成套打开**，并按几何给参数。

判据（都在 core/model_analysis.py 里算，几何实测、不看名字）
------------------------------------------------------------
    circle_score >= 0.6       → 圆柱/圆管
    circle_score >= 1.0       → 明确的圆（截面面积比 ≈ π/4）
    细高比 >= 2.6             → 竖着摆的柱子，斜接缝最见效
    扁平度 < 0.25             → 平躺的圆盘，接缝在侧壁一圈，斜接缝同样有效

成本口径
--------
斜接缝不是白拿的：它要额外走一段重叠路径，**每一层都会慢一点**（约 2~5%），
小直径圆件（< 15 mm）斜切段放不下，会退化成普通接缝。所以这里对直径
也设了下限，并且把代价写进 `notes` 里，UI 与报告都看得见。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SeamPlan", "STANDARD_KEYS", "plan"]

#: 本层会写的接缝键。都是 Bambu Studio 工程文件的标准键：老工程里缺这几行时
#: 也允许补写（见 threemf.apply(allow_missing=...)），否则「斜接缝开了却没生效」。
STANDARD_KEYS = frozenset({
    "seam_position",
    "seam_slope_type", "seam_slope_conditional", "seam_slope_inner_walls",
    "seam_slope_steps", "seam_slope_start_height", "seam_slope_min_length",
    "seam_slope_gap", "scarf_angle_threshold",
    "apply_scarf_seam_on_circles", "has_scarf_joint_seam",
})


@dataclass
class SeamPlan:
    ops: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    enabled: bool = False


def _num(v, default: float = 0.0) -> float:
    try:
        if isinstance(v, (list, tuple)):
            v = v[0] if v else default
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return default


def plan(profile, *, layer_height: float = 0.2, current: dict | None = None,
         enabled: bool = True) -> SeamPlan:
    """按几何决定接缝位置与斜接缝参数。

    profile  : core.model_analysis.ModelProfile（可以为 None，那就只用兜底策略）
    current  : 工程当前值（用来判断「本来就是这个值」而不必重复写）
    enabled  : 界面开关；关掉就完全不碰接缝键
    """
    out = SeamPlan()
    if not enabled:
        return out
    cur = current or {}
    lh = max(0.04, float(layer_height or 0.2))

    circle = 0.0
    slender = 0.0
    flatness = 1.0
    min_dia = 0.0
    if profile is not None:
        try:
            circle = float(getattr(profile, "circle_score", 0.0) or 0.0)
            slender = float(getattr(profile, "slender", 0.0) or 0.0)
            flatness = float(getattr(profile, "flatness", 1.0) or 1.0)
            for o in (getattr(profile, "objects", None) or []):
                w = min(float(getattr(o, "size_x", 0) or 0), float(getattr(o, "size_y", 0) or 0))
                if w > 0 and (min_dia == 0.0 or w < min_dia):
                    min_dia = w
        except Exception:
            pass

    is_round = circle >= 0.6
    plain_round = circle >= 1.0

    # ---- 1 接缝位置：圆件用 aligned（一条竖线，斜切后几乎看不见）；
    #      太小的圆（<15 mm）用 nearest，斜切段放不下
    if is_round:
        if min_dia and min_dia < 15.0:
            out.ops["seam_position"] = "nearest"
            out.notes.append(
                f"接缝位置：最小圆形件直径约 {min_dia:.0f} mm（<15 mm），"
                "斜切段放不下，改用最短路径接缝（nearest）。")
            out.rows.append({
                "metric": "接缝位置 seam_position",
                "measured": f"最细圆件 {min_dia:.0f} mm ／ 圆柱度 {circle:.2f}",
                "formula": "圆形件且直径 <15 mm → nearest",
                "conclusion": "设为 nearest（斜切放不下）",
            })
            out.enabled = True
            return out
        out.ops["seam_position"] = "aligned"
        out.notes.append(
            f"接缝位置：识别到圆形件（圆柱度 {circle:.2f}）→ 接缝对齐成一条竖线，"
            "再叠斜接缝把这条线斜过去。")
        out.rows.append({
            "metric": "接缝位置 seam_position",
            "measured": f"圆柱度 {circle:.2f} ／ 细高比 {slender:.2f} ／ 扁平度 {flatness:.2f}",
            "formula": "圆柱度 ≥0.6 → aligned（一条竖线，便于斜切遮住）",
            "conclusion": "设为 aligned",
        })
    elif slender >= 2.6:
        out.ops["seam_position"] = "aligned"
        out.notes.append(
            f"接缝位置：细高件（细高比 {slender:.2f}）→ 接缝对齐成一条竖线，比随机点更不显眼。")
        out.rows.append({
            "metric": "接缝位置 seam_position",
            "measured": f"细高比 {slender:.2f}",
            "formula": "细高比 ≥2.6 → aligned",
            "conclusion": "设为 aligned",
        })
    else:
        out.enabled = True
        return out

    # ---- 2 斜接缝（scarf）：只对外露轮廓做，且只在平缓处做
    out.ops["seam_slope_type"] = "external"
    out.ops["seam_slope_conditional"] = True
    # 圆形件必须打开这个官方开关，否则 Studio 会跳过多边形化后的圆轮廓
    out.ops["apply_scarf_seam_on_circles"] = True
    out.ops["has_scarf_joint_seam"] = True
    out.ops["seam_slope_inner_walls"] = True

    # 斜切高度：取 2~4 个层高，层高越大取越多层（保证斜切段有足够长度盖住接缝）
    steps = int(max(2, min(12, round(0.6 / lh))))
    out.ops["seam_slope_steps"] = steps
    # 斜切起始高度：圆件从底层往上 10% 起步（底部实心段不斜切，避免首层糊边）
    start_pct = 10.0 if not plain_round else 5.0
    out.ops["seam_slope_start_height"] = start_pct
    # 斜切最小长度：外露轮廓周长的一小段即可，给 6 mm（小件也不会被跳过）
    out.ops["seam_slope_min_length"] = 6.0
    # 斜切间隙：0（首尾接上，否则会留凹坑）；圆件尤其不能留缝
    out.ops["seam_slope_gap"] = 0.0
    # 角度阈值：155° 是官方默认，只在接近平角处斜切（尖角处斜切会糊）
    out.ops["scarf_angle_threshold"] = 155.0

    out.enabled = True
    out.notes.append(
        f"斜接缝：已为一整套斜切参数（{steps} 层过渡、起始 {start_pct:.0f}% 高度、"
        f"间隙 0、圆形轮廓也做斜接）→ 圆柱侧面那条竖线会被斜面盖住，"
        "肉眼几乎看不到。代价是每层多走一段重叠路径，整体约慢 2~5%。")
    out.rows.append({
        "metric": "斜接缝 scarf",
        "measured": f"圆柱度 {circle:.2f} ／ 层高 {lh:g} mm",
        "formula": "steps = 0.6 ÷ 层高（夹 2~12）；起始高度 圆 5% / 细高 10%；间隙 0",
        "conclusion": f"seam_slope_type=external，{steps} 层过渡",
    })

    # ---- 3 已经是这个值就不写（避免把用户自己的选择顶掉）
    final: dict = {}
    for key, val in out.ops.items():
        if key in cur and str(_norm_cmp(cur.get(key))) == str(_norm_cmp(val)):
            continue          # 工程里本来就是这值 → 不必写、也不必声明
        final[key] = val
    out.ops = final
    return out


def _norm_cmp(v):
    """把 1 / "1" / true / "true" 归一，判断「值其实没变」。"""
    if isinstance(v, bool):
        return "1" if v else "0"
    txt = str(v).strip().lower()
    if txt in ("true", "yes", "on"):
        return "1"
    if txt in ("false", "no", "off"):
        return "0"
    try:
        f = float(txt.rstrip("%"))
        return str(int(f)) if abs(f - int(f)) < 1e-9 else f"{f:g}"
    except (TypeError, ValueError):
        return txt
