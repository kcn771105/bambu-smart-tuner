"""喷嘴流量同步层。

Bambu 官方的 `filament_max_volumetric_speed` 是**按喷嘴**给的，不是按耗材：
同一个 Bambu PETG Basic 在 X1C 上

    0.2 喷嘴 → 1 mm³/s
    0.4 喷嘴 → 13 mm³/s
    0.6 喷嘴 → 13 mm³/s
    0.8 喷嘴 → 16 mm³/s

把 0.4 的 13 直接套到 0.2 喷嘴上，算出来的速度是物理跑不到的（0.2 熔池每秒只能熔
1 mm³ 料），表现就是表面糊成一片甚至堵料。反过来把 0.2 的 1 套到 0.8 上，会白
白把 0.8 的产能压掉 90%。

所以「换喷嘴」这件事必须连带把流量上限一起换 —— 这就是本模块的唯一职责。
数据来自 `rules/BambuRules.json` 的 `nozzle_flow` 段（由
`tools/_patch_nozzle_flow.py` 从官方预设生成）。
"""

from __future__ import annotations

#: 官方给出的喷嘴档位。用户工程里出现其它值（例如 0.25）时取最接近的一档。
NOZZLES = (0.2, 0.4, 0.6, 0.8)


def snap_nozzle(nozzle: float | None) -> float | None:
    """把任意喷嘴直径贴到官方档位；None 原样返回。"""
    if nozzle is None:
        return None
    try:
        v = float(nozzle)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return min(NOZZLES, key=lambda n: (abs(n - v), n))


def _key(nozzle: float) -> str:
    return f"{nozzle:g}"


def table(rules: dict | None) -> dict:
    return ((rules or {}).get("nozzle_flow") or {}).get("by_group") or {}


def limit(rules: dict | None, *, group: str, filament_key: str,
          nozzle: float | None) -> tuple[float | None, str]:
    """返回 (该机型组 + 该耗材 + 该喷嘴的官方流量上限, 来源说明)。"""
    n = snap_nozzle(nozzle)
    if n is None:
        return None, ""
    by_group = table(rules)
    node = (by_group.get(group) or by_group.get("GENERIC")
            or by_group.get("X1") or {})
    row = node.get(filament_key) or node.get("GENERIC") or {}
    raw = row.get(_key(n))
    if raw is None:
        return None, ""
    return float(raw), f"官方「{filament_key} × {group} 组 × {n:g} 喷嘴」标定 {float(raw):g}"


def ratio(rules: dict | None, *, group: str, filament_key: str,
          from_nozzle: float | None, to_nozzle: float | None) -> tuple[float | None, str]:
    """两个喷嘴之间的官方流量比（用于把用户实测标定值折算到新喷嘴）。"""
    a, _ = limit(rules, group=group, filament_key=filament_key, nozzle=from_nozzle)
    b, _ = limit(rules, group=group, filament_key=filament_key, nozzle=to_nozzle)
    if not a or not b or a <= 0:
        return None, ""
    return b / a, (f"官方 {filament_key} 从 {snap_nozzle(from_nozzle):g} 到 "
                   f"{snap_nozzle(to_nozzle):g} 喷嘴的流量比 "
                   f"{a:g} → {b:g}（×{b / a:.2f}）")


def nozzle_volume(rules: dict | None, group: str) -> float | None:
    """机型组的熔池体积（机器页 nozzle_volume，随机型不随喷嘴变）。"""
    node = ((rules or {}).get("nozzle_flow") or {}).get("nozzle_volume") or {}
    v = node.get(group) or node.get("GENERIC")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None
