"""热端流量类型（标准流量 / 高流量 / E3D 高流量）。

用户要求（m05100 第 2 条）：解析 3mf 识别热端流量类型，UI 显示且可手改，
并把流量类型作为调参规则的一个判断维度。

工程里表达「这根热端是什么」的键有六个（都在机器页，**只读**）：

    nozzle_volume_type            ["Standard"]                     首选
    default_nozzle_volume_type    ["Standard"]
    extruder_nozzle_stats         ["Standard#1"]                   带数量后缀
    extruder_nozzle_stats_new     ["Standard#1"]
    printer_extruder_variant      ["Direct Drive Standard", ...]   整机支持的变体列表
    print_extruder_variant        ["Direct Drive Standard", ...]   本工程用的变体列表
    nozzle_volume                 ["110","110","110"]              熔池体积，随类型变化

这三种热端的差别是**熔化能力**，不是精度：

    标准流量    Standard        熔池小，官方 filament_max_volumetric_speed 就是按它标的
    高流量      High Flow       熔池更大，同直径下可推更高流量（Bambu 官方标称约 +30~40%）
    E3D 高流量  E3D High Flow   E3D 结构，流量更高（约 +50~60%），但回抽与压力提前要更谨慎

所以流量类型不能只当标签：它必须参与「体积流量上限」和「速度基准」两处判断，
否则高流量热端会被按标准热端的流量钳着跑，白买。
"""

from __future__ import annotations

import json

#: 规范键 → 中文名
FLOW_LABELS = {
    "standard": "标准流量",
    "high": "高流量",
    "e3d": "E3D 高流量",
}

#: 官方/用户可能写出来的各种叫法 → 规范键
ALIASES = {
    "standard": "standard",
    "std": "standard",
    "标准": "standard",
    "标准流量": "standard",
    "direct drive standard": "standard",
    "high flow": "high",
    "highflow": "high",
    "high": "high",
    "高流量": "high",
    "direct drive high flow": "high",
    "e3d high flow": "e3d",
    "e3d": "e3d",
    "e3d 高流量": "e3d",
    "direct drive e3d high flow": "e3d",
    "e3dhighflow": "e3d",
}

#: 检测顺序：先看 nozzle_volume_type，再看 *_nozzle_stats，最后看 variant
DETECT_KEYS = (
    "nozzle_volume_type",
    "default_nozzle_volume_type",
    "extruder_nozzle_stats_new",
    "extruder_nozzle_stats",
    "printer_extruder_variant",
    "print_extruder_variant",
)


def _first(val) -> str:
    """工程里的值多半是数组，取第 0 槽；字符串原样返回。"""
    import json

    if val is None:
        return ""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    txt = str(val).strip()
    if txt.startswith("["):
        try:
            v = json.loads(txt)
            if isinstance(v, list) and v:
                return str(v[0])
        except (ValueError, TypeError):
            pass
    return txt


def normalize(name: str) -> str:
    """任意写法 → standard / high / e3d；认不出来返回空串。"""
    low = (name or "").strip().lower()
    if not low:
        return ""
    # "Standard#1" / "High Flow#1" 这种带数量后缀的
    low = low.split("#")[0].strip()
    if low in ALIASES:
        return ALIASES[low]
    # 互含兜底：先判 e3d，再判 high，避免 "e3d high flow" 被 high 抢走
    if "e3d" in low:
        return "e3d"
    if "high" in low or "高流量" in low:
        return "high"
    if "standard" in low or "标准" in low:
        return "standard"
    return ""


class HotendInfo:
    """识别结果：类型 + 中文名 + 依据。"""

    __slots__ = ("key", "label", "source_key", "source_value", "nozzle_volume",
                 "variants", "detected")

    def __init__(self, key: str = "", *, source_key: str = "",
                 source_value: str = "", nozzle_volume: float | None = None,
                 variants: list[str] | None = None, detected: bool = False):
        self.key = key or "standard"
        self.label = FLOW_LABELS.get(self.key, self.key)
        self.source_key = source_key
        self.source_value = source_value
        self.nozzle_volume = nozzle_volume
        self.variants = variants or []
        self.detected = detected

    def summary_line(self) -> str:
        """给 UI「真机同步」的一行。"""
        parts = [f"热端流量类型：{self.label}"]
        if self.nozzle_volume:
            parts.append(f"熔池 {self.nozzle_volume:g} mm³")
        if self.detected and self.source_key:
            parts.append(f"依据 {self.source_key} = {self.source_value!r}")
        elif not self.detected:
            parts.append("工程里没读到流量类型，按标准流量对待（可在下拉里手改）")
        return " ｜ ".join(parts)

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label,
            "source_key": self.source_key, "source_value": self.source_value,
            "nozzle_volume": self.nozzle_volume, "detected": self.detected,
        }


def _num(val) -> float | None:
    """工程里的数值可能是 '110'，也可能是 ['110','110']。"""
    txt = _first(val)
    if not txt:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def detect(settings: dict) -> HotendInfo:
    """从工程（或 settings 字典）里识别热端流量类型。

    优先级：nozzle_volume_type > default_nozzle_volume_type > *_nozzle_stats
            > printer_extruder_variant > print_extruder_variant
    """
    flow_key = ""
    src_key = ""
    src_val = ""
    for key in DETECT_KEYS:
        if key not in settings:
            continue
        raw = _first(settings.get(key))
        norm = normalize(raw)
        if norm:
            flow_key, src_key, src_val = norm, key, raw
            break

    variants: list[str] = []
    for key in ("printer_extruder_variant", "print_extruder_variant"):
        val = settings.get(key)
        if isinstance(val, list) and val:
            variants = [str(x) for x in val]
            break

    return HotendInfo(flow_key or "standard",
                      source_key=src_key, source_value=src_val,
                      nozzle_volume=_num(settings.get("nozzle_volume")),
                      variants=variants, detected=bool(flow_key))


def slot_count(settings: dict) -> int:
    """本工程「按热端变体分槽」的数组有几个槽位。

    依据 print_extruder_variant / printer_extruder_variant 的条目数：
        P2S: ["Direct Drive Standard", "Direct Drive High Flow",
              "Direct Drive E3D High Flow"] -> 3
    没有这两个键的工程返回 0（表示不分槽，按标量处理）。
    """
    for key in ("print_extruder_variant", "printer_extruder_variant",
                "extruder_variant_list"):
        raw = (settings or {}).get(key)
        if not raw:
            continue
        try:
            val = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        if isinstance(val, list) and len(val) > 1:
            return len(val)
    return 0


def factor(rules: dict, flow_type: str) -> tuple[float, str]:
    """热端类型对**体积流量上限**的倍率（永远 ≥ 1.0，只会放宽不会收紧）。"""
    node = ((rules or {}).get("hotend_flow") or {}).get("types") or {}
    spec = node.get(flow_type) or node.get("standard") or {}
    try:
        mul = float(spec.get("volumetric_mul", 1.0))
    except (TypeError, ValueError):
        mul = 1.0
    mul = max(1.0, mul)
    note = str(spec.get("note") or "")
    return mul, note


def options(rules: dict) -> list[tuple[str, str]]:
    """给 UI 下拉用：[(key, label), ...]，第一项是「自动」。"""
    out = [("", "自动识别")]
    node = ((rules or {}).get("hotend_flow") or {}).get("types") or {}
    order = ["standard", "high", "e3d"]
    for k in order:
        label = str((node.get(k) or {}).get("label") or FLOW_LABELS.get(k, k))
        out.append((k, label))
    for k in node:
        if k not in order:
            out.append((k, str((node.get(k) or {}).get("label") or k)))
    return out
