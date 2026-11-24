"""支撑按模型尺寸定量调整——支撑参数的**唯一**决策者。

分工（避免三方抢写）：
    core/support_plan.decide   只回答「要不要支撑、悬垂判定角多少」
    core/support_model.tune    回答「用多少料、离多远、长什么样、多快」
    core/shape_rules / geom_rules  **不再写任何 support_* 键**

全部按模型实测值算（数据来自 core/model_analysis）：

1. 密度（support_base_pattern_spacing）← 悬垂总面积
   ≥4000 → 1.6 mm；≥1500 → 2.0；≥400 → 2.5；其余 3.0（稀一点好拆）
2. 顶面间隙（support_top_z_distance）← 层高 × 0.7，夹 0.12~0.30
   底面间隙（support_bottom_z_distance）← 层高 × 1.0，夹 0.15~0.35
3. 水平间距（support_object_xy_distance）← 细高比 / 高度 / 底面积
   细高比≥3 或高≥120 → 0.8；底面积<600 mm² → 0.9（喷头空走不蹭柱）
4. 接触面（interface）：
   层数 support_interface_top_layers = 2（零星）/3（大面积）
   bottom_layers 同理
   线距 support_interface_spacing = 0.5（大面积平整）/0.7（好撕）
   线宽 support_line_width = 喷嘴线宽 × 0.9（接触面细一点更好撕）
5. 形态：
   细高（≥3.2）或高（≥150） → tree(auto)；细高比≥3.5 用 tree_strong，其余 tree_slim
   大面积低矮悬垂（≥1500）     → normal(auto) + grid 底座
   零星悬垂                    → 保持工程原形态，只调密度
6. 速度：支撑本体可以快（看不见），接触面要慢（决定好不好撕）
   support_speed          ← 机型上限 × 0.7，按模式微调
   support_interface_speed← 支撑速度 × 0.6（质量档 0.5）
   这两个是**按热端变体分槽的数组**，由 schema 的整槽写入统一处理
7. 质量向（仅 quality 族）：
   support_critical_regions_only = 1（只在与模型真正接触处生成）
   support_ironing_* 打开，接触面平整、拆下来不留疤
8. 支撑关掉时：一个 support_* 键都不写（以前会留下 top_z / xy 这种噪音）
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SupportRow:
    metric: str
    measured: str
    formula: str
    conclusion: str

    def as_dict(self) -> dict:
        return {"metric": self.metric, "measured": self.measured,
                "formula": self.formula, "conclusion": self.conclusion}


@dataclass
class SupportTune:
    ops: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    rows: list[SupportRow] = field(default_factory=list)


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def _num(v, default: float = 0.0) -> float:
    try:
        if isinstance(v, (list, tuple)):
            v = v[0] if v else default
        return float(str(v).strip().rstrip("%"))
    except (TypeError, ValueError):
        return default


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    if isinstance(v, (list, tuple)):
        s = str(v[0]).strip().lower() if v else ""
    return s in ("1", "true", "yes", "on")


def _total(profile, name: str) -> float:
    """ModelProfile 是聚合视图，逐件属性要自己求和。"""
    v = getattr(profile, name, None)
    try:
        if v is not None and float(v) > 0:
            return float(v)
    except (TypeError, ValueError):
        pass
    total = 0.0
    for o in (getattr(profile, "objects", None) or []):
        try:
            total += float(getattr(o, name, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _geom(profile) -> tuple[float, float, float]:
    """(高, 底面积, 细高比)。"""
    height = 0.0
    for name in ("size_z", "height"):
        try:
            height = max(height, float(getattr(profile, name, 0) or 0))
        except (TypeError, ValueError):
            pass
    for o in (getattr(profile, "objects", None) or []):
        try:
            height = max(height,
                         float(getattr(o, "max_z", 0) or getattr(o, "size_z", 0) or 0))
        except (TypeError, ValueError):
            pass
    foot = _total(profile, "footprint")
    slender = 0.0
    if foot > 1e-9 and height > 0:
        slender = height / (foot ** 0.5)
    try:
        slender = max(slender, float(getattr(profile, "slender", 0) or 0))
    except (TypeError, ValueError):
        pass
    return height, foot, slender


def spacing_for(overhang_area: float) -> tuple[float, str]:
    if overhang_area >= 4000:
        return 1.6, "悬垂面积 ≥4000 mm²（大面积悬垂，撑密一点防塌）"
    if overhang_area >= 1500:
        return 2.0, "悬垂面积 1500~4000 mm²"
    if overhang_area >= 400:
        return 2.5, "悬垂面积 400~1500 mm²"
    return 3.0, "悬垂面积 <400 mm²（零星悬垂，稀一点好拆）"


#: 模式对支撑的倾向：速度快慢、接触面精细度
MODE_SPEED = {          # support_speed = 机型上限 × 该系数
    "strength": 0.70, "balanced": 0.75, "draft": 0.85,
    "quality": 0.60, "fine": 0.60, "ultrafine": 0.55,
}
MODE_IFACE = {          # support_interface_speed = support_speed × 该系数
    "strength": 0.60, "balanced": 0.60, "draft": 0.70,
    "quality": 0.50, "fine": 0.50, "ultrafine": 0.45,
}
QUALITY_FAMILY = {"quality", "fine", "ultrafine"}

SUPPORT_KEYS_PREFIXES = (
    "support_", "tree_support_", "enable_support",
    "raft_", "support_ironing_",
)


def is_support_key(key: str) -> bool:
    return key.startswith(SUPPORT_KEYS_PREFIXES)


def tune(profile, *, layer_height: float = 0.2, mode: str = "balanced",
         values: dict | None = None, judge_angle: float | None = None,
         nozzle: float = 0.4, line_width: float | None = None,
         max_speed: float | None = None) -> SupportTune:
    """按模型实测尺寸给支撑参数。values 是当前值（判断支撑有没有开）。"""
    out = SupportTune()
    if profile is None:
        return out
    vals = values or {}
    if not _truthy(vals.get("enable_support")):
        return out        # 没开支撑就一个键都不写

    overhang_area = _total(profile, "overhang_area")
    height, foot, slender = _geom(profile)

    # ---- 1 密度
    spacing, why = spacing_for(overhang_area)
    out.ops["support_base_pattern_spacing"] = {"set": spacing}
    out.reasons.append(f"{why} → 支撑线距 {spacing:g} mm。")
    out.rows.append(SupportRow(
        "支撑密度 support_base_pattern_spacing",
        f"悬垂面积 {overhang_area:.0f} mm² ／ 模型高 {height:.0f} mm",
        "≥4000→1.6、≥1500→2.0、≥400→2.5、其余 3.0 mm",
        f"取 {spacing:g} mm"))

    # ---- 2 间隙（顶/底）
    top_z = _round2(max(0.12, min(0.30, layer_height * 0.7)))
    bot_z = _round2(max(0.15, min(0.35, layer_height * 1.0)))
    out.ops["support_top_z_distance"] = {"set": top_z}
    out.ops["support_bottom_z_distance"] = {"set": bot_z}
    out.reasons.append(
        f"支撑间隙按层高 {layer_height:g} mm 算：顶 {top_z:g} mm（×0.7）、底 {bot_z:g} mm（×1.0）。")
    out.rows.append(SupportRow(
        "支撑分离间隙",
        f"层高 {layer_height:g} mm",
        "顶 = 层高×0.7 夹 0.12~0.30；底 = 层高×1.0 夹 0.15~0.35",
        f"顶 {top_z:g} mm ／ 底 {bot_z:g} mm"))

    # ---- 3 水平间距
    xy = 0.5
    why_xy = "普通件 0.5 mm"
    if slender >= 3.0 or height >= 120:
        xy, why_xy = 0.8, "细高/高件，喷头空走容易扫到支撑柱"
    if 0 < foot < 600:
        xy, why_xy = max(xy, 0.9), "底面积小于 600 mm²，支撑不能贴太近"
    out.ops["support_object_xy_distance"] = {"set": xy}
    out.rows.append(SupportRow(
        "支撑水平间距 support_object_xy_distance",
        f"细高比 {slender:.2f} ／ 高 {height:.0f} mm ／ 底面积 {foot:.0f} mm²",
        "细高比≥3 或高≥120 → 0.8；底面积<600 mm² → 0.9；其余 0.5",
        f"取 {xy:g} mm（{why_xy}）"))

    # ---- 4 接触面：层数 / 线距 / 线宽
    big = overhang_area >= 1500
    top_layers = 3 if big else 2
    bot_layers = 3 if big else 2
    iface = 0.5 if big else 0.7
    lw = _round2((line_width or nozzle * 1.05) * 0.9)
    out.ops["support_interface_top_layers"] = {"set": top_layers}
    out.ops["support_interface_bottom_layers"] = {"set": bot_layers}
    out.ops["support_interface_spacing"] = {"set": iface}
    out.ops["support_line_width"] = {"set": lw}
    out.reasons.append(
        f"接触面：顶/底各 {top_layers}/{bot_layers} 层、线距 {iface:g} mm、线宽 {lw:g} mm"
        f"（{'大面积悬垂求平整' if big else '零星悬垂求好撕'}）。")
    out.rows.append(SupportRow(
        "支撑接触面",
        f"悬垂面积 {overhang_area:.0f} mm² ／ 线宽基准 {line_width or nozzle * 1.05:.2f} mm",
        "层数 大面积3/零星2；线距 0.5/0.7；线宽 = 线宽基准 ×0.9",
        f"{top_layers} 层 ／ 线距 {iface:g} ／ 线宽 {lw:g} mm"))

    # ---- 5 形态
    tall_ish = slender >= 3.2 or height >= 150
    if tall_ish:
        out.ops["support_type"] = {"set": "tree(auto)"}
        out.ops["support_style"] = {"set": "tree_strong" if slender >= 3.5 else "tree_slim"}
        out.reasons.append("高瘦件用树状支撑：落点少、避开模型侧面，树干加粗防晃。")
        out.rows.append(SupportRow(
            "支撑形态 support_type",
            f"细高比 {slender:.2f} ／ 高 {height:.0f} mm",
            "细高比≥3.2 或高≥150 → tree(auto)；细高比≥3.5 → tree_strong",
            "树状支撑" + ("（加粗）" if slender >= 3.5 else "（细枝）")))
    elif big:
        out.ops["support_type"] = {"set": "normal(auto)"}
        out.ops["support_base_pattern"] = {"set": "grid"}
        out.reasons.append("大面积低矮悬垂用普通支撑 + 网格底座，撑得稳。")
        out.rows.append(SupportRow(
            "支撑形态 support_type",
            f"悬垂面积 {overhang_area:.0f} mm² ／ 细高比 {slender:.2f}",
            "大面积低矮悬垂 → normal(auto) + grid",
            "普通支撑（网格底座）"))

    # ---- 6 速度（数组键，schema 会整槽写入）
    cap = float(max_speed) if max_speed else 500.0
    spd = max(20.0, min(cap, round(cap * MODE_SPEED.get(mode, 0.75))))
    ispd = max(10.0, min(spd, round(spd * MODE_IFACE.get(mode, 0.6))))
    out.ops["support_speed"] = {"set": spd}
    out.ops["support_interface_speed"] = {"set": ispd}
    out.rows.append(SupportRow(
        "支撑速度",
        f"机型上限 {cap:.0f} mm/s ／ 模式 {mode}",
        "支撑本体 = 上限 ×0.55~0.85；接触面 = 本体 ×0.45~0.70",
        f"本体 {spd:g} ／ 接触面 {ispd:g} mm/s（最终还要受体积流量上限钳制）"))

    # ---- 7 质量向
    if mode in QUALITY_FAMILY:
        out.ops["support_critical_regions_only"] = {"set": True}
        out.ops["support_ironing_flow"] = {"set": 10}
        out.ops["support_ironing_spacing"] = {"set": 0.15}
        out.reasons.append(
            "质量档：支撑只在与模型真正接触处生成（省料且少留痕），"
            "接触面做支撑熨烫，拆下来更平整。")
        out.rows.append(SupportRow(
            "支撑接触面处理",
            f"模式 {mode}",
            "质量族 → critical_regions_only + 支撑熨烫（流量 10%、线距 0.15）",
            "只在接触处生成 + 熨烫"))
    elif mode == "draft":
        out.ops["support_remove_small_overhang"] = {"set": True}
        out.rows.append(SupportRow(
            "零星悬垂过滤",
            f"模式 {mode}",
            "草稿档 → 小于阈值的悬垂不生成支撑",
            "开启"))

    return out
