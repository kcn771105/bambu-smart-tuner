"""按模型实测尺寸做**定量**推导（不是按原型套模板）。

为什么要这一层
-------------
`shape_rules.py` 是「形状原型 → 一组经验微调」：判定成高瘦件就降加速度、
判定成薄壁件就慢外壁。这一步有用，但只能回答「这属于哪一类」，
回答不了「这件到底要几圈墙才实心」「层高最大能到多少」这类**数量**问题。

本模块把几何实测值直接代进公式：

    R1 墙圈数 ← 实测壁厚 ÷ 线宽            （薄壁件才用，实心块无意义）
    R2 层高上限 ← 最薄特征厚度 ÷ 2          （层高超过特征一半，特征就糊了）
    R3 首层速度 ← 首层接触面积              （面积越大翘曲风险越高，首层越要慢）
    R4 顶/底壳层数 ← 目标壳厚 ÷ 层高        （按 top_cap_ratio 判断顶面是否需要密封）
    R5 填充密度 ← 细高比 + 体积             （强度档：弯曲载荷需要更多内部支撑）
    R6 接缝位置 ← 扁平度 / 尖端比           （方盒放背面，细高件对齐隐藏）

R1/R2 只作用在「薄壳件」（fill_ratio < 0.55）。对实心立方体，
wall_thickness = 2V/S ≈ 边长/3，直接除以线宽会得出荒谬圈数 —— 这是
`ObjectProfile.wall_thickness` 的已知边界，必须靠 fill_ratio 挡掉。

所有公式的输出都会同时产出一行 `DerivationRow`（实测值 / 公式 / 结论），
UI 与报告直接展示，用户可以核对每一步怎么来的。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import modes as mode_registry

# 薄壳判定阈值：填充率低于它才认为「壁厚」这个词有意义
SHELL_FILL_RATIO = 0.55
# 壁厚参与推导的有效区间（mm）：太薄属网格噪声，太厚就不叫薄壁了
SHELL_T_MIN = 0.25
SHELL_T_MAX = 4.0
# 目标壳层厚度（mm）：顶面需要密封/耐磨时加厚
TOP_TARGET_SEAL = 0.8
TOP_TARGET_OPEN = 0.6
BOTTOM_TARGET = 0.6

# 墙圈数上限（按模式）：草稿档不堆墙，强度档允许堆到 6 圈
LOOP_CAP = {
    "strength": 6, "balanced": 5, "quality": 5,
    "draft": 4, "fine": 5, "ultrafine": 6,
}


@dataclass
class DerivationRow:
    """一行推导记录：给人核对用。"""
    metric: str        # 指标名
    measured: str      # 实测/依据
    formula: str       # 公式
    conclusion: str    # 结论（含写进参数的值）

    def as_dict(self) -> dict:
        return {"metric": self.metric, "measured": self.measured,
                "formula": self.formula, "conclusion": self.conclusion}


@dataclass
class Derivation:
    ops: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    rows: list[DerivationRow] = field(default_factory=list)


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _round_to(v: float, step: float) -> float:
    if step <= 0:
        return v
    return round(round(v / step) * step, 6)


def _shell_objects(profile) -> list:
    """参与壁厚推导的薄壳对象。"""
    out = []
    for o in getattr(profile, "objects", []) or []:
        if o.volume <= 0 or o.surface <= 0:
            continue
        if o.fill_ratio >= SHELL_FILL_RATIO:
            continue
        t = o.wall_thickness
        if SHELL_T_MIN <= t <= SHELL_T_MAX:
            out.append(o)
    return out


def derive(profile, *, nozzle: float = 0.4, line_width: float | None = None,
           layer_height: float = 0.2, mode: str = "balanced",
           filament_key: str = "", current: dict | None = None) -> Derivation:
    """按模型实测尺寸推导工艺参数。

    profile 为空（工程里没模型）时返回空结果 —— 不做任何猜测。
    """
    out = Derivation()
    if profile is None or not getattr(profile, "objects", None):
        return out
    cur = current or {}
    mode_key = mode if mode in LOOP_CAP else "balanced"
    w = _num(line_width, 0.0) or _num(nozzle, 0.4) * 1.05
    lh = _num(layer_height, 0.2) or 0.2

    shells = _shell_objects(profile)
    t_min = min((o.wall_thickness for o in shells), default=0.0)

    # ---------------- R1 墙圈数：实测壁厚 ÷ 线宽 ----------------
    # 只在强度档启用。理由：把壁厚「填实」是强度目标；
    # 均衡/质量/草稿档堆到 5~6 圈等于把时间翻倍换一点几乎测不出的刚度，
    # 官方 Standard 档本身也只有 2 圈。
    if t_min > 0 and mode_key == "strength":
        need_raw = math.ceil(t_min / w - 1e-9)
        cap = LOOP_CAP.get(mode_key, 5)
        need = int(_clamp(need_raw, 2, cap))
        cur_loops = int(round(_num(cur.get("wall_loops"), 2.0)))
        if need > cur_loops:
            out.ops["wall_loops"] = {"min": need}
            filled = cur_loops * w
            rest = max(0.0, t_min - filled)
            why = (f"实测最薄壁厚 {t_min:.2f} mm，线宽 {w:.2f} mm → "
                   f"需要 {need_raw} 圈才实心（{mode_key} 档封顶 {cap} 圈）。"
                   f"当前 {cur_loops} 圈只覆盖 {filled:.2f} mm，"
                   f"剩下 {rest:.2f} mm 会被填成稀疏填充，强度靠填充撑不住。")
            out.notes.append("墙圈数：" + why)
            out.rows.append(DerivationRow(
                metric="墙圈数 wall_loops",
                measured=f"最薄壁厚 {t_min:.2f} mm ／ 线宽 {w:.2f} mm ／ 当前 {cur_loops} 圈",
                formula=f"ceil({t_min:.2f} ÷ {w:.2f}) = {need_raw}，按 {mode_key} 档封顶 {cap}",
                conclusion=f"提到 {need} 圈（实心覆盖 {need * w:.2f} mm）"))
        else:
            out.rows.append(DerivationRow(
                metric="墙圈数 wall_loops",
                measured=f"最薄壁厚 {t_min:.2f} mm ／ 线宽 {w:.2f} mm ／ 当前 {cur_loops} 圈",
                formula=f"ceil({t_min:.2f} ÷ {w:.2f}) = {need_raw}",
                conclusion=f"当前 {cur_loops} 圈已够，不改"))

    # ---------------- R2 层高上限：最薄特征 ÷ 2 ----------------
    if t_min >= 0.3:
        lh_cap = _round_to(max(0.08, t_min / 2.0), 0.01)
        if lh_cap < lh - 0.005:
            out.ops["layer_height"] = {"max": lh_cap}
            why = (f"最薄特征 {t_min:.2f} mm，层高 {lh:.2f} mm 超过它的一半 "
                   f"（{lh / t_min:.2f} 倍），特征会被层纹吃掉 → 压到 {lh_cap:.2f} mm。")
            out.notes.append("层高：" + why)
            out.rows.append(DerivationRow(
                metric="层高上限 layer_height",
                measured=f"最薄特征 {t_min:.2f} mm ／ 当前层高 {lh:.2f} mm",
                formula=f"上限 = {t_min:.2f} ÷ 2 = {t_min / 2:.2f}",
                conclusion=f"压到 {lh_cap:.2f} mm"))
        else:
            out.rows.append(DerivationRow(
                metric="层高上限 layer_height",
                measured=f"最薄特征 {t_min:.2f} mm ／ 当前层高 {lh:.2f} mm",
                formula=f"上限 = {t_min:.2f} ÷ 2 = {t_min / 2:.2f}",
                conclusion="层高未超过特征一半，不改"))

    # ---------------- R3 首层速度：首层接触面积 ----------------
    area = sum(o.footprint for o in profile.objects if o.footprint > 0)
    if area > 0:
        # 250×250 = 62500 mm² 视为「满盘」→ 首层降到 25 mm/s
        fac = min(1.0, area / 62500.0)
        sp = _round_to(_clamp(55.0 - 30.0 * fac, 25.0, 55.0), 5.0)
        cur_sp = _num(cur.get("initial_layer_speed"), 50.0)
        if sp < cur_sp - 0.5:
            out.ops["initial_layer_speed"] = {"max": sp}
            why = (f"首层接触面积 {area:.0f} mm²（满盘 62500 mm² 的 "
                   f"{fac * 100:.0f}%），面积越大收缩应力越大 → 首层压到 {sp:.0f} mm/s。")
            out.notes.append("首层速度：" + why)
            out.rows.append(DerivationRow(
                metric="首层速度 initial_layer_speed",
                measured=f"首层接触面积 {area:.0f} mm²（占比 {fac * 100:.0f}%）",
                formula="55 − 30 × 面积占比",
                conclusion=f"上限 {sp:.0f} mm/s（当前 {cur_sp:.0f}）"))
        else:
            out.rows.append(DerivationRow(
                metric="首层速度 initial_layer_speed",
                measured=f"首层接触面积 {area:.0f} mm²（占比 {fac * 100:.0f}%）",
                formula="55 − 30 × 面积占比",
                conclusion=f"算出上限 {sp:.0f} ≥ 当前 {cur_sp:.0f}，不改"))

    # ---------------- R4 顶/底壳层数：目标壳厚 ÷ 层高 ----------------
    top_cap = max((o.top_cap_ratio for o in profile.objects), default=0.0)
    top_target = TOP_TARGET_SEAL if top_cap > 0.5 else TOP_TARGET_OPEN
    top_n = int(_clamp(math.ceil(top_target / lh - 1e-9), 3, 8))
    bot_n = int(_clamp(math.ceil(BOTTOM_TARGET / lh - 1e-9), 3, 8))
    out.ops.setdefault("top_shell_layers", {"min": top_n})
    out.ops.setdefault("bottom_shell_layers", {"min": bot_n})
    cur_top = int(round(_num(cur.get("top_shell_layers"), 0.0)))
    cur_bot = int(round(_num(cur.get("bottom_shell_layers"), 0.0)))
    out.rows.append(DerivationRow(
        metric="顶/底壳层数",
        measured=(f"顶盖占比 {top_cap * 100:.0f}%（>50% 视为需要密封的顶面）／ "
                  f"当前顶 {cur_top} 层、底 {cur_bot} 层"),
        formula=f"顶 = ceil({top_target:.1f} ÷ {lh:.2f})、底 = ceil({BOTTOM_TARGET:.1f} ÷ {lh:.2f})",
        conclusion=f"顶至少 {top_n} 层、底至少 {bot_n} 层"))

    # ---------------- R5 填充密度：细高比 + 体积 ----------------
    if mode_key == "strength":
        add = 0.0
        bits = []
        if profile.slender >= 2.6:
            add += 8.0
            bits.append(f"细高比 {profile.slender:.2f} ≥ 2.6（悬臂弯矩大）")
        vol = _num(getattr(profile, "volume", 0.0))
        if vol >= 200_000:
            add += 5.0
            bits.append(f"体积 {vol / 1000:.0f} cm³ ≥ 200（惯性大，塌陷风险高）")
        if add > 0:
            base = 25.0
            out.ops["sparse_infill_density"] = {"min": base + add}
            why = "；".join(bits) + f" → 强度档基础 25% + {add:.0f}% = {base + add:.0f}%。"
            out.notes.append("填充密度：" + why)
            out.rows.append(DerivationRow(
                metric="填充密度 sparse_infill_density",
                measured="；".join(bits),
                formula="25%（强度档基线）+ 8%（细高）+ 5%（大体积）",
                conclusion=f"下限 {base + add:.0f}%"))

    # ---------------- R7 悬垂跨度：要降桥接速度、加接触层 ----------------
    # 悬垂面积占比是「有多少要撑」，悬垂边上最长那条（span）是「撑得有多悬」。
    # 一大片悬空（跨度 ≥ 20 mm 且占比 ≥ 3%）时，全速跑桥接会垂丝、贴合差，
    # 必须把桥接速度压下来，接触面也多给一层，让上面那层有东西压着。
    span = _num(getattr(profile, "max_bridge_span", 0.0))
    sup_ratio = _num(getattr(profile, "support_ratio", 0.0))
    if span >= 20.0 and sup_ratio >= 0.03:
        br = _num(cur.get("bridge_speed"), 30.0) or 30.0
        cap_br = min(br, 30.0)
        out.ops.setdefault("bridge_speed", {"max": cap_br})
        why = (f"最长悬垂边 {span:.0f} mm、悬垂占比 {sup_ratio * 100:.1f}%："
               f"这是一大片悬空，桥接压到 {cap_br:.0f} mm/s（接触面层数由支撑层另算）。")
        out.notes.append("悬垂：" + why)
        out.rows.append(DerivationRow(
            metric="悬垂跨度 → 桥接速度 bridge_speed",
            measured=f"最长悬垂边 {span:.1f} mm ／ 悬垂占比 {sup_ratio * 100:.1f}%",
            formula="跨度 ≥ 20 mm 且占比 ≥ 3% → 桥接 ≤ 30 mm/s",
            conclusion=f"桥接上限 {cap_br:.0f} mm/s"))
    else:
        out.rows.append(DerivationRow(
            metric="悬垂跨度 → 桥接速度 bridge_speed",
            measured=f"最长悬垂边 {span:.1f} mm ／ 悬垂占比 {sup_ratio * 100:.1f}%",
            formula="跨度 ≥ 20 mm 且占比 ≥ 3%",
            conclusion="没到门槛，桥接速度按档位走"))

    # ---------------- R8 站得稳不稳：细高 + 脚小 → 加宽裙边 ----------------
    footprint = _num(getattr(profile, "footprint", 0.0))
    slender = _num(getattr(profile, "slender", 0.0))
    if slender >= 3.0 and 0 < footprint < 2500.0:
        wide = max(6.0, _num(cur.get("brim_width"), 0.0) or 0.0)
        out.ops.setdefault("brim_width", {"min": wide})
        out.ops.setdefault("brim_type", {"set": "outer_only"})
        out.ops.setdefault("initial_layer_speed", {"max": 40.0})
        why = (f"细高比 {slender:.2f}、脚底接触 {footprint:.0f} mm²："
               f"重心高、接触小，裙边加到 {wide:.0f} mm，首层压到 40 mm/s 换附着力。")
        out.notes.append("稳定性：" + why)
        out.rows.append(DerivationRow(
            metric="脚底接触 → 裙边/首层速度",
            measured=f"细高比 {slender:.2f} ／ 脚底 {footprint:.0f} mm²",
            formula="细高比 ≥ 3 且脚底 < 2500 mm² → 裙边 ≥ 6 mm、首层 ≤ 40 mm/s",
            conclusion=f"裙边 {wide:.0f} mm（outer_only）、首层上限 40 mm/s"))
    else:
        out.rows.append(DerivationRow(
            metric="脚底接触 → 裙边/首层速度",
            measured=f"细高比 {slender:.2f} ／ 脚底 {footprint:.0f} mm²",
            formula="细高比 ≥ 3 且脚底 < 2500 mm²",
            conclusion="站得稳，裙边按形状判定走"))

    # ---------------- R6 接缝位置：扁平度 / 尖端比 ----------------
    flat = _num(getattr(profile, "flatness", 0.0))
    neck = _num(getattr(profile, "neck_ratio", 1.0))
    aspect = _num(getattr(profile, "plan_aspect", 1.0))
    seam = ""
    seam_why = ""
    if top_cap >= 0.5 and flat >= 0.35 and aspect >= 0.6:
        seam, seam_why = "back", "方正实体件（顶面封闭、四边竖直）：接缝放背面，正面看不到"
    elif profile.slender >= 2.6:
        seam = "aligned"
        seam_why = (f"细高件（细高比 {profile.slender:.2f}）：接缝对齐成一条竖线，"
                    f"比随机点更不显眼")
    elif neck < 0.45:
        seam, seam_why = "nearest", f"带收腰（尖端比 {neck:.2f}）：接缝就近最短路径，减少空走痕迹"
    if seam and str(cur.get("seam_position") or "") != seam:
        out.ops["seam_position"] = {"set": seam}
        out.notes.append("接缝位置：" + seam_why + f" → seam_position = {seam}。")
        out.rows.append(DerivationRow(
            metric="接缝位置 seam_position",
            measured=(f"顶盖占比 {top_cap * 100:.0f}% ／ 扁平度 {flat:.2f} ／ "
                      f"平面长宽比 {aspect:.2f} ／ 尖端比 {neck:.2f}"),
            formula="方正→back；细高→aligned；收腰→nearest",
            conclusion=f"设为 {seam}"))

    return out
