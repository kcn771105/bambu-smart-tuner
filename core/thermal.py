"""热床温度与风速推导层（v1.2）。

为什么要单独一层
----------------
用户反馈：「再加一个不同耗材、不同板子、不同室温下，设置的热床温度和风速，
要不然有的模型在天冷了会翘边」。

热床温度决定首层能不能粘住（凉 → 翘边、底面波浪），风速决定冷却强度
（风太猛 → 翘边 + 层间粘合变差；风太小 → 拉丝、悬垂糊料）。两者都和
「耗材类型」「板子类型」「室温」三个维度强相关，所以放在一个独立模块里
按维度查表，并把每一项的推导过程写成说明（UI 和报告里都能看到）。

推导口径
--------
1. 板子基线：`rules.thermal.plate_baseline[板子][耗材]`，
   数值取官方耗材预设里 `*_plate_temp` 的默认值（实测见 README 表）。
2. 首层温度 = 基线 + `initial_layer_delta`（默认 −5°C，首层要慢一点粘得更实）。
3. 室温修正：低于 20°C 时按 `room_temp_correction` 档位加温（冷天翘边），
   高于 30°C 时减温（夏天散热差，过温反而粘不住）。
4. 风扇：`rules.thermal.fan[耗材]` 给出 min/max 转速（百分比）、
   首层是否开风扇、前几层关风扇、悬垂风扇转速。
   - PLA 冷却需求高 → 风扇给足，但首层关、前几层慢升；
   - PETG/ASA 要防拉丝与粘支撑 → 风扇压低，首层开少量；
   - ABS 收缩大 → 风扇尽量关，靠热床保温；
   - TPU 柔软、易堵 → 风扇压低、首层关。
5. 每个结论都记一条 `DerivationRow(metric, measured, formula, conclusion)`，
   UI 的「热床与风速」表直接显示，不需要用户去读一堆参数值。

本模块只产出 op，写入与否由引擎的 scope 闸门决定
（thermal 组已加入 options.write_scopes，所以会写回）。
"""

from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Any

from . import schema

__all__ = ["ThermalOps", "ThermalRow", "bed_type_of", "derive", "plate_types",
           "fan_table", "STANDARD_KEYS"]

#: 只列 **Bambu Studio 切片器里真实有、且工程文件里有独立温度键** 的板型。
#: Studio 的工程里就这五个键：cool / eng / hot / textured / supertack。
#: 「光滑 PEI 板（Smooth PEI Plate）」在 Studio 里和「高温板」是同一格
#: （官方 machine 预设写的就是 `Smooth PEI Plate / High Temp Plate`，共用一个键），
#: 所以它只是别名，不再作为独立选项出现在下拉里。
PLATE_TYPES = ("Supertack Plate", "Textured PEI Plate", "High Temp Plate",
               "Engineering Plate", "Cool Plate")

#: 别名 → 规范名。工程里可能出现的各种写法都收敛到这五个。
PLATE_ALIASES = {
    "smooth pei plate": "High Temp Plate",
    "smooth pei": "High Temp Plate",
    "光面 pei 板": "High Temp Plate",
    "光滑 pei 板": "High Temp Plate",
    "光面板": "High Temp Plate",
    "光滑板": "High Temp Plate",
    "high temperature plate": "High Temp Plate",
    "supertack": "Supertack Plate",
    "cool plate (superTack)".lower(): "Supertack Plate",
    "textured": "Textured PEI Plate",
    "engineering": "Engineering Plate",
    "cool": "Cool Plate",
}

#: 板型的中文名。工程文件里必须写英文（Studio 只认那几个串），
#: 界面上给人看的一律用中文 —— 用户反馈「打印板用中文」。
PLATE_LABELS = {
    "Supertack Plate": "超粘板 Supertack",
    "Textured PEI Plate": "纹理 PEI 板",
    "High Temp Plate": "高温板（含光滑 PEI）",
    "Engineering Plate": "工程板",
    "Cool Plate": "低温板",
}

#: 这些键是 Bambu Studio 工程文件里的**标准键**：任何一台机器的工程都认。
#: 老工程/被裁过的工程里可能没存这几行，但补进去不会被 Studio 当成脏键，
#: 反而是「热床温度和风速没改成功」的根因之一 —— 所以缺失时也允许写入。
STANDARD_KEYS = frozenset({
    "curr_bed_type",
    "supertack_plate_temp", "supertack_plate_temp_initial_layer",
    "textured_plate_temp", "textured_plate_temp_initial_layer",
    "hot_plate_temp", "hot_plate_temp_initial_layer",
    "cool_plate_temp", "cool_plate_temp_initial_layer",
    "eng_plate_temp", "eng_plate_temp_initial_layer",
    "nozzle_temperature", "nozzle_temperature_initial_layer",
    "fan_min_speed", "fan_max_speed",
    "first_x_layer_fan_speed", "close_fan_the_first_x_layers",
    "overhang_fan_speed", "fan_cooling_layer_time",
})


@dataclass
class ThermalRow:
    """一条推导记录（UI 直接显示）。"""

    metric: str
    measured: str
    formula: str
    conclusion: str

    def as_dict(self) -> dict:
        return {"metric": self.metric, "measured": self.measured,
                "formula": self.formula, "conclusion": self.conclusion}


@dataclass
class ThermalOps:
    ops: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    rows: list[ThermalRow] = field(default_factory=list)
    #: 「因为室温 X°C，所以热床 Y、风扇 Z」这一句（没有室温时为空）
    room_note: str = ""


def normalize_plate(name: str) -> str:
    """任意写法 → 五个规范名之一；认不出来就给空串（调用方自己兜底）。"""
    txt = str(name or "").strip()
    if not txt:
        return ""
    if txt in PLATE_TYPES:
        return txt
    low = txt.lower()
    if low in PLATE_ALIASES:
        return PLATE_ALIASES[low]
    for t in PLATE_TYPES:
        if t.lower() == low:
            return t
    for t in PLATE_TYPES:
        if t.lower() in low or low in t.lower():
            return t
    return ""


def unsupported_plates(text: str | None) -> set[str]:
    """解析机器预设里的 `not_support_bed_type`。

    官方写法是分号分隔、`/` 表示「这两种其实是同一格」，例如
        "Cool Plate;Smooth PEI Plate / High Temp Plate;3D Effect Plate"
    只保留本程序认识的板型，其它（3D 效应板之类）不管。
    """
    out: set[str] = set()
    for chunk in str(text or "").replace("；", ";").split(";"):
        for piece in chunk.split("/"):
            name = normalize_plate(piece)
            if name:
                out.add(name)
    return out


def plate_types(not_support: str | None = None) -> tuple[str, ...]:
    """给下拉用的板型列表；给了机型的 not_support_bed_type 就滤掉不支持的。"""
    bad = unsupported_plates(not_support)
    if not bad:
        return PLATE_TYPES
    left = tuple(t for t in PLATE_TYPES if t not in bad)
    return left or PLATE_TYPES


def plate_label(name: str) -> str:
    """板型 → 给人看的中文名（认不出来就原样返回）。"""
    txt = str(name or "").strip()
    if not txt:
        return ""
    for key, label in PLATE_LABELS.items():
        if txt == key:
            return label
    low = txt.lower()
    for key, label in PLATE_LABELS.items():
        if key.lower() in low or low in key.lower():
            return label
    return txt


def plate_options(not_support: str | None = None) -> list[tuple[str, str]]:
    """界面下拉用：(中文名, 写进工程的值)。"""
    return [(plate_label(t), t) for t in plate_types(not_support)]


def _num(v: Any, fallback: float = 0.0) -> float:
    return schema.numeric(v) if schema.numeric(v) is not None else fallback


def bed_type_of(settings: dict) -> str:
    """读工程里的板子类型；缺省按 Supertack（实测绝大多数工程是它）。"""
    raw = (settings or {}).get("curr_bed_type")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    txt = str(raw or "").strip()
    name = normalize_plate(txt)
    if name:
        return name
    return "Supertack Plate"


#: 板型 → 板温键（写进工程的键名）
PLATE_TEMP_KEY = {
    "Supertack Plate": "supertack_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Smooth PEI Plate / High Temp Plate": "hot_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "Cool Plate": "cool_plate_temp",
}


def plate_temp_key(name: str) -> str:
    return PLATE_TEMP_KEY.get(str(name or "").strip(), "supertack_plate_temp")


def read_bed_temp(settings: dict, bed_name: str = "") -> float | None:
    """读工程里这块板现在的温度；读不到返回 None。

    用在「换板子」的场合：工程原本的板本机 Studio 不认识，只能换一块，
    但温度得接着用原来的值，不能套新板的基线。
    """
    def _read(raw: Any) -> float:
        """工程里的值可能是 ["60"] 这种按热端分槽的 JSON 文本，先拆再取首个非零。"""
        if isinstance(raw, str):
            txt = raw.strip()
            if txt.startswith("["):
                try:
                    raw = json.loads(txt)
                except (ValueError, TypeError):
                    raw = [t.strip().strip('"') for t in txt.strip("[]").split(",")]
        if isinstance(raw, (list, tuple)):
            for item in raw:
                got = _read(item)
                if got > 0:
                    return got
            return 0.0
        got = schema.numeric(raw)
        return float(got) if got is not None else 0.0

    bed = str(bed_name or "").strip() or bed_type_of(settings)
    key = plate_temp_key(bed)
    value = _read((settings or {}).get(key))
    if value > 0:
        return value
    # 工程里可能只存了首层温度，或者键名和板型对不上，兜一圈找非零值
    for cand in (key + "_initial_layer", "hot_plate_temp", "textured_plate_temp"):
        value = _read((settings or {}).get(cand))
        if value > 0:
            return value
    return None


def fan_table(rules: dict, filament_key: str) -> dict:
    """取某耗材的风扇基线。"""
    node = (rules.get("thermal") or {}).get("fan", {})
    return node.get(filament_key) or {}


# 各打印板的热床上限（°C）：低温板加热过头反而更难取件，工程板/高温板才耐得住
_PLATE_MAX = {
    "Supertack Plate": 85.0,
    "Textured PEI Plate": 85.0,
    "High Temp Plate": 90.0,
    "Engineering Plate": 90.0,
    "Cool Plate": 45.0,
}


def _room_delta(rules: dict, room_c: float | None) -> tuple[float, str]:
    """室温修正：返回 (加温量, 说明)。"""
    if room_c is None:
        return 0.0, ""
    corr = (rules.get("thermal") or {}).get("room_temp_correction", {})
    above = corr.get("above")
    below = corr.get("below", [])
    if above is not None and room_c >= above.get("at", 30.0):
        d = -above.get("delta", 2.0)
        return d, f"室温 {room_c:.0f}°C 高于 {above.get('at')}°C，散热变差，减温 ×{d}"
    for step in below:
        if room_c <= step.get("at", 0.0):
            return float(step.get("delta", 0.0)), f"室温 {room_c:.0f}°C 低于 {step.get('at')}°C，加温 +{step.get('delta')}°C"
    return 0.0, ""


def derive(rules: dict, current: dict, *, filament_key: str = "", bed_type: str = "",
           room_temp_c: float | None = None, printer_key: str = "",
           fan_trim: int | None = None, bed_keep_temp: float | None = None) -> ThermalOps:
    """按耗材 × 板子 × 室温推导热床温度与风速。

    参数
    ----
    rules       : 规则库
    current     : 工程当前设置（用来取「现在是多少」作对比）
    filament_key: 耗材键（PLA/PETG/ABS/ASA/TPU），缺省按 PLA
    bed_type    : 板子类型，缺省从 current 里读 curr_bed_type
    room_temp_c : 室温（°C），不传就不改
    printer_key : 机型键（仅用于说明，未来可按机型微调）
    fan_trim    : 风扇整体偏置（百分点）。负数更保守（更不容易翘边/拉丝），
                  正数更猛（悬垂更好看）。只对 min/max 生效，首层关风不受影响。
    bed_keep_temp: 指定板温（°C）。用在「换板子」的场合：工程原本用的是本机 Studio
                  不认识的板（比如 Supertack），只能换成它认识的板，这时板温要沿用
                  用户原来的温度，而不是套用新板的基线，否则等于偷偷改了温度。
    """
    out = ThermalOps()
    filament_key = filament_key or "PLA"
    bed = bed_type or bed_type_of(current)

    node = rules.get("thermal") or {}
    base = (node.get("plate_baseline") or {}).get(bed) or {}
    if not base:
        out.notes.append(f"热床温度：规则库里没有「{plate_label(bed)}」的基线表，改用该耗材的通用基线。")
        # 退到任意板子的第一个可用行
        for _p, row in (node.get("plate_baseline") or {}).items():
            if filament_key in row:
                base = row
                break

    if bed_keep_temp is not None and float(bed_keep_temp) > 0:
        target = float(bed_keep_temp)
        base = {filament_key: target}          # 让下游算公式时用的是这个值
        out.notes.append(
            f"板子换成「{plate_label(bed)}」，板温以你原来的 {target:.0f}°C 为基准"
            "（不套用这块板的基线，免得悄悄改温度；室温修正照常叠加）。")
    else:
        target = _num(base.get(filament_key), 0.0)
    if target <= 0:
        out.notes.append(f"热床温度：规则库里没有「{filament_key} × {plate_label(bed)}」的基线，保持工程原值不动。")
        return out

    # 首层要比其余层「更热」才抓得住底板（Bambu 自带预设也是这么配的：
    # Textured PEI + PLA = 首层 65 / 其余 60）。负数等于首层更凉，会直接掉附着。
    delta_init = _num(node.get("initial_layer_delta", 5.0), 5.0)
    room_delta, room_txt = _room_delta(rules, room_temp_c)

    # 加温别越界：delta 最多 +12°C（再高板子受不了、也未必更粘），
    # 各板另有物理上限：低温板 45°C 就是上限，超了反而更难取件。
    room_delta = max(-8.0, min(12.0, room_delta))
    ceiling = _PLATE_MAX.get(bed, 85.0)
    temp_target = max(0.0, min(ceiling, target + room_delta))
    temp_init = max(0.0, min(ceiling + 5.0, temp_target + delta_init))

    # 板子温度键按板型映射
    plate_key = {
        "Supertack Plate": "supertack_plate_temp",
        "Textured PEI Plate": "textured_plate_temp",
        "High Temp Plate": "hot_plate_temp",
        "Engineering Plate": "eng_plate_temp",
        "Cool Plate": "cool_plate_temp",
    }.get(bed, "supertack_plate_temp")
    plate_key_init = plate_key + "_initial_layer"

    # 板子本身也要写进工程：Studio 是按 curr_bed_type 决定读哪一块板的温度键，
    # 只改温度不改板名，它照样按旧板解释（换板后「导入不对」的另一半原因）。
    curr_bed = str(current.get("curr_bed_type") or "").strip()
    if isinstance(current.get("curr_bed_type"), list):
        items = current.get("curr_bed_type") or []
        curr_bed = str(items[0]).strip() if items else ""
    if bed and curr_bed and curr_bed != bed:
        out.ops["curr_bed_type"] = {"set": bed}
        out.notes.append(f"打印板已从「{plate_label(curr_bed)}」改成「{plate_label(bed)}」"
                         "（Studio 按板名决定读哪块板的温度，板名不改温度就等于白改）。")

    now = _num(current.get(plate_key), 0.0)
    if now > 0:
        if abs(now - temp_target) >= 1.0:
            out.ops[plate_key] = {"set": temp_target}
            out.rows.append(ThermalRow(
                metric=f"{plate_label(bed)} 温度",
                measured=f"{now:.0f}°C",
                formula=f"基线 {target:.0f}°C" + (f" + 室温修正 {room_delta:+.0f}" if room_delta else ""),
                conclusion=f"调到 {temp_target:.0f}°C" + (f"（首层 {temp_init:.0f}°C）" if delta_init else ""))
            )
        else:
            out.rows.append(ThermalRow(
                metric=f"{plate_label(bed)} 温度", measured=f"{now:.0f}°C",
                formula=f"基线 {target:.0f}°C" + (f" + 室温修正 {room_delta:+.0f}" if room_delta else ""),
                conclusion="已接近推导值，不改"))
    else:
        out.ops[plate_key] = {"set": temp_target}
        out.rows.append(ThermalRow(
            metric=f"{plate_label(bed)} 温度", measured="工程里没存",
            formula=f"基线 {target:.0f}°C" + (f" + 室温修正 {room_delta:+.0f}" if room_delta else ""),
            conclusion=f"设为 {temp_target:.0f}°C"))

    if delta_init:
        out.ops[plate_key_init] = {"set": temp_init}
        out.rows.append(ThermalRow(
            metric=f"{plate_label(bed)} 首层温度", measured=f"{temp_target:.0f}°C",
            formula=f"基线 + 首层修正 {delta_init:+.0f}°C",
            conclusion=f"设为 {temp_init:.0f}°C"))

    # ---------------- 风扇
    fan = fan_table(rules, filament_key)
    # 风扇强弱：None=自动，数字=手动。这里先给默认，风扇表缺失时也不至 NameError。
    auto_fan = fan_trim is None
    trim = 0

    if fan:
        fan_min = _num(fan.get("min"), 0.0)
        fan_max = _num(fan.get("max"), 0.0)
        first_x = _num(fan.get("first_x_layer_fan_speed"), -1.0)
        close_layers = _num(fan.get("close_the_first_x_layers"), 0.0)
        overhang = fan.get("overhang_fan_speed")

        # 风扇强弱：None = 自动（按耗材基线，冷天再自动降一档）；
        # 给了数字 = 用户手动指定，照他说的来，不再叠加自动修正。
        trim_txt = ""
        if auto_fan:
            if room_temp_c is not None and room_temp_c < 18.0:
                trim = -10
                trim_txt = f"，室温 {room_temp_c:.0f}°C 偏冷，自动降 10 个百分点防翘边"
            else:
                trim_txt = "，自动（按耗材基线）" if room_temp_c is None else ""
        else:
            trim = int(fan_trim)
            trim_txt = f"，手动 {trim:+d}" if trim else "，手动不动"
        if trim:
            fan_min = min(100.0, max(0.0, fan_min + trim))
            fan_max = min(100.0, max(0.0, fan_max + trim))
            if overhang is not None:
                overhang = min(100.0, max(0.0, _num(overhang, 0.0) + trim))
            if fan_max and fan_min > fan_max:
                fan_min = fan_max

        if fan_min > 0:
            out.ops["fan_min_speed"] = {"set": fan_min}
        if fan_max > 0:
            out.ops["fan_max_speed"] = {"set": fan_max}
        if first_x is not None and first_x >= 0:
            out.ops["first_x_layer_fan_speed"] = {"set": first_x}
        if close_layers > 0:
            out.ops["close_fan_the_first_x_layers"] = {"set": close_layers}
        if overhang is not None:
            out.ops["overhang_fan_speed"] = {"set": _num(overhang, 0.0)}

        ftxt = (f"风扇 min {fan_min:.0f}% / max {fan_max:.0f}%"
                + (f"、首层 {first_x:.0f}%" if first_x >= 0 else "")
                + (f"、前 {close_layers:.0f} 层关闭" if close_layers > 0 else "")
                + (f"、悬垂 {overhang:.0f}%" if overhang is not None else "")
                + trim_txt)
        out.rows.append(ThermalRow(
            metric=f"{filament_key} 风扇策略",
            measured=f"工程原值 {_num(current.get('fan_min_speed')):.0f}%/"
                     f"{_num(current.get('fan_max_speed')):.0f}%",
            formula="按耗材冷却需求分档（规则库 thermal.fan）" + trim_txt,
            conclusion=ftxt))
        out.notes.append(f"风速：{filament_key} → {ftxt}。")

    if room_txt:
        out.notes.append(room_txt)

    # 室温联动的一句话总结：用户填了室温就想知道「到底动了什么」。
    # 只要填了就给一句，哪怕这次推导值没变（否则界面看起来像没生效）。
    if room_temp_c is not None:
        moved = []
        delta_bed = temp_target - target
        if abs(delta_bed) >= 0.5:
            moved.append(f"热床 {target:.0f} → {temp_target:.0f}°C")
        if auto_fan and trim:
            moved.append(f"风扇再降 {abs(trim)} 个百分点")
        if moved:
            why = "天冷防翘边" if delta_bed > 0 else "天热防粘死、好取件"
            out.room_note = f"室温 {room_temp_c:.0f}°C：{'、'.join(moved)}，{why}"
        elif room_temp_c < 18.0:
            out.room_note = (f"室温 {room_temp_c:.0f}°C：板温已到 {temp_target:.0f}°C 上限，"
                             "再高板子受不了，改靠关门/加罩保温")
        else:
            out.room_note = (f"室温 {room_temp_c:.0f}°C：常规区间，热床 {temp_target:.0f}°C、"
                             "风扇按标定值走")
    out.notes.append(f"热床：{filament_key} × {plate_label(bed)}，目标 {temp_target:.0f}°C"
                     + (f"，首层 {temp_init:.0f}°C" if delta_init else "") + "。")
    return out
