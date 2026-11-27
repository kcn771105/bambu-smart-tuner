"""熨烫（ironing）：用户选要不要、熨哪儿；参数由这里按耗材/层高/喷嘴算。

熨烫是「拿热喷嘴在已经打好的平面上再刮一遍」，把顶面刮平、把层纹和缝隙抹掉。
它不动几何、不动速度体系，只加一遍低速低流量的走线，所以：

    * 用户只选「熨不熨」和「熨哪儿」（`ironing_type`），四个取值与 Studio 一致；
    * 流量/间距/速度/图案由这里按耗材、层高、喷嘴、优化模式给一组保守值；
    * 用户把「参数自动优化」关掉时，就只改类型，四个参数沿用工程原值。

对应反馈：「加入熨烫优化，用户手动选择是否开启熨烫，用户自己选择熨烫类型，参数自动优化」。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 用户能选的四种（key 与 Studio 的 ironing_type 取值一一对应）
TYPES: dict[str, str] = {
    "off": "no ironing",
    "top": "top",           # 只熨最顶上那一层
    "topmost": "topmost",   # 熨所有朝上的外露面（有台阶的件最有用）
    "solid": "solid",       # 熨所有实心层的顶面（最费时间，最平）
}

TYPE_LABELS: dict[str, str] = {
    "keep": "跟随工程（不改）",
    "off": "不熨烫",
    "top": "只熨最顶面",
    "topmost": "熨所有朝上的面（有台阶/斜面用这个）",
    "solid": "熨所有实心层顶面（最平、最慢）",
}

# 界面下拉顺序：(显示名, key)
def type_options() -> list[tuple[str, str]]:
    order = ("keep", "top", "topmost", "solid", "off")
    return [(TYPE_LABELS[k], k) for k in order]


# 引擎里「工程里没有这个键也要补写」的白名单
STANDARD_KEYS = frozenset({
    "ironing_type", "ironing_pattern", "ironing_flow", "ironing_spacing",
    "ironing_speed", "ironing_inset", "ironing_direction",
})


@dataclass
class IroningPlan:
    ops: dict = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    note: str = ""
    label: str = ""


def _f(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _table(rules: dict) -> dict:
    return (rules or {}).get("ironing") or {}


def _profile(node: dict, filament_key: str) -> dict:
    """按耗材取一组基准值；找不到就用表里的 default。"""
    profiles = node.get("profiles") or {}
    key = (filament_key or "").strip()
    if key in profiles:
        return dict(profiles[key])
    upper = key.upper()
    for name, prof in profiles.items():
        if name.upper() == upper or name.upper() in upper:
            return dict(prof)
    return dict(node.get("default") or {})


def _mul(table: dict, key: str, name: str) -> float:
    """取 `by_mode` / `nozzle_spacing_mul` 里某个条目的系数（缺失即 1.0）。"""
    node = table.get(key) or {}
    if name in node:
        try:
            return float(node[name])
        except (TypeError, ValueError):
            return 1.0
    return 1.0


def plan(*, choice: str, auto: bool = True, filament_key: str = "",
         layer_height: float = 0.2, nozzle: float = 0.4, mode_key: str = "balanced",
         current: dict | None = None, rules: dict | None = None) -> IroningPlan:
    """把用户的选择 + 耗材/层高/喷嘴 → 一组熨烫参数。

    `choice` 是界面上的 key：keep / off / top / topmost / solid。
    """
    table = _table(rules)
    out = IroningPlan()
    cur = current or {}
    choice = (choice or "keep").strip().lower()

    if choice in ("", "keep", "auto"):
        out.note = "熨烫：跟随工程原设置，没有改动。"
        return out
    if choice not in TYPES:
        out.note = f"熨烫：不认识的选择「{choice}」，没有改动。"
        return out

    studio_type = TYPES[choice]
    out.label = TYPE_LABELS.get(choice, choice)
    out.ops["ironing_type"] = studio_type

    if choice == "off":
        out.rows.append({
            "metric": "熨烫", "measured": "你选择了不熨烫",
            "formula": "ironing_type = no ironing",
            "conclusion": "已关掉熨烫，顶面保留层纹，但省时间",
        })
        out.note = "熨烫：已关掉（顶面会有层纹，换来的是一遍走线的省时）。"
        return out

    if not auto:
        out.rows.append({
            "metric": "熨烫类型", "measured": "你手动指定", "formula": "ironing_type",
            "conclusion": f"写入 {studio_type}；流量/间距/速度保持你原来的值",
        })
        out.note = f"熨烫：已开启（{out.label}），参数按你自己的设置，没有被改动。"
        return out

    prof = _profile(table, filament_key)
    lh = _f(layer_height, 0.2) or 0.2
    nz = _f(nozzle, 0.4) or 0.4
    spacing_mul = _mul(table, "by_mode", mode_key) or 1.0
    mode_node = (table.get("by_mode") or {}).get(mode_key) or {}
    speed_mul = _f(mode_node.get("speed_mul"), 1.0) or 1.0
    nz_mul = _f((table.get("nozzle_spacing_mul") or {}).get(f"{nz:g}"), 1.0) or 1.0

    flow = _f(prof.get("flow"), 10.0)
    spacing = _f(prof.get("spacing"), 0.15) * nz_mul * spacing_mul
    speed = _f(prof.get("speed"), 30.0) * speed_mul
    pattern = str(prof.get("pattern") or "monotonic")
    inset = _f(prof.get("inset"), 0.15)

    # 层高越厚，一次刮的面积越大，间距略放宽一点，别重复磨同一个位置
    spacing *= max(0.85, min(1.3, lh / 0.2))
    spacing = max(0.05, min(1.0, round(spacing, 2)))
    speed = max(5.0, min(200.0, round(speed, 1)))
    flow = max(1.0, min(60.0, round(flow, 1)))
    inset = max(0.0, min(2.0, round(inset, 2)))

    out.ops.update({
        "ironing_pattern": pattern,
        "ironing_flow": flow,
        "ironing_spacing": spacing,
        "ironing_speed": speed,
        "ironing_inset": inset,
        "ironing_direction": 0.0,
    })
    out.rows.append({
        "metric": "熨烫类型", "measured": f"你选择「{out.label}」",
        "formula": "ironing_type", "conclusion": f"写入 {studio_type}",
    })
    out.rows.append({
        "metric": "熨烫参数", "measured": f"耗材 {filament_key or '未知'} · 层高 {lh:g} mm · 喷嘴 {nz:g} mm",
        "formula": f"流量 {flow:g}% · 间距 {spacing:g} mm · 速度 {speed:g} mm/s · 图案 {pattern}",
        "conclusion": "流量小、间距密、速度低 → 表面被刮平，层纹基本消失",
    })
    out.note = (f"熨烫：已开启（{out.label}）—— 流量 {flow:g}%、间距 {spacing:g} mm、"
                f"速度 {speed:g} mm/s、图案 {pattern}。")
    return out
