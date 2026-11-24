"""真机信息同步层：从工程文件里读出这台打印机的真实能力

用户的要求：「喷嘴信息、直径、流量都要同步打印机，板子也要同步」。

工程文件里其实已经带着这些信息，只是之前没人读：

    机器页（只读）
        nozzle_diameter                ["0.4"]           喷嘴直径
        nozzle_volume                  ["110","110",...] 热端熔池体积 (mm³)
        machine_max_speed_x/y          ["1000",...]      真实速度上限
        machine_max_acceleration_x/y   ["20000",...]     真实加速度上限
        machine_max_acceleration_travel ["10000",...]
        machine_max_jerk_x/y           ["9",...]
        machine_max_speed_z            ["20"]            Z 轴速度
        machine_max_acceleration_z      ["500"]
        min_layer_height / max_layer_height ["0.08"]/["0.28"]
        printable_area                 ["0x0","256x0","256x256","0x256"]  可打印区域
        wrapping_exclude_area          ["153x256",...]    前方禁打区
        print_extruder_variant         ["Direct Drive High Flow",...]
        hotend_heating_rate / hotend_cooling_rate

    耗材页（只读）
        filament_type                  ["PETG"]
        filament_max_volumetric_speed  ["18","15","15"]  用户标定的热端流量上限
        filament_flow_ratio            ["0.95","0.95","0.95"]

这些值**只读不写**（用户明确要求机器页耗材页不动），但要参与两件事：

    1. 钳制：算出来的工艺速度不能超过这台机器真实的速度上限；
       算出来的工艺加速度不能超过真实加速度上限；
       算出来的层高要落在机器允许的层高区间内。
    2. 展示：UI 上让用户看到「这台机器的真实上限」，便于判断结果合不合理。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .threemf import ThreeMfProject


def _arr(raw) -> list:
    """工程里的值可能是 JSON 数组字符串，也可能是标量。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    txt = str(raw).strip()
    if txt.startswith("["):
        try:
            v = json.loads(txt)
            if isinstance(v, list):
                return v
        except (ValueError, TypeError):
            pass
    return [txt] if txt else []


def _num(raw, idx: int = 0) -> float | None:
    arr = _arr(raw)
    if not arr or idx >= len(arr):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(arr[idx]))
    return float(m.group(1)) if m else None


def _first_num(raw) -> float | None:
    return _num(raw, 0)


@dataclass
class BedInfo:
    """板面信息。"""
    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0
    exclude: list[str] = field(default_factory=list)   # 前方禁打区（矩形列表）

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def depth(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def known(self) -> bool:
        return self.width > 0 and self.depth > 0

    def summary(self) -> str:
        if not self.known:
            return "板面尺寸未知"
        s = f"{self.width:.0f} × {self.depth:.0f} mm"
        if self.exclude:
            # 工程里存的是矩形角点，4 个点 = 1 块
            blocks = max(1, len(self.exclude) // 4)
            s += f"（前方禁打区 {blocks} 块）"
        return s


@dataclass
class HardwareInfo:
    """这台打印机的真实能力（全部来自工程，只读）。"""
    # ---- 喷嘴
    nozzle_diameter: float | None = None
    nozzle_volume: float | None = None            # 热端熔池体积 mm³
    extruder_variant: str = ""                    # Direct Drive High Flow 等
    hotend_heating_rate: float | None = None
    hotend_cooling_rate: float | None = None

    # ---- 机器上限
    max_speed: float | None = None
    max_accel: float | None = None
    max_travel_accel: float | None = None
    max_jerk: float | None = None
    max_speed_z: float | None = None
    max_accel_z: float | None = None
    min_layer_height: float | None = None
    max_layer_height: float | None = None

    # ---- 耗材
    filament_type: str = ""
    max_volumetric_speed: float | None = None     # 用户标定的热端流量上限 mm³/s
    filament_flow_ratio: float | None = None
    #: 流量上限的来源说明（写进 UI，避免用户以为是官方值）
    max_volumetric_source: str = ""

    # ---- 板面
    bed: BedInfo = field(default_factory=BedInfo)
    #: 打印板类型（工程 curr_bed_type，只读）
    plate_type: str = ""

    # ---- 元信息
    printer_model: str = ""
    printer_settings_id: str = ""
    ams_count: str = ""

    # ---- 来源标记
    from_project: bool = False

    # -------------------------------------------------- 展示

    def summary_lines(self) -> list[str]:
        """给 UI 展示的「真机同步」清单。"""
        out: list[str] = []
        nozzle = f"{self.nozzle_diameter:g} mm" if self.nozzle_diameter else "未读到"
        out.append(f"喷嘴直径：{nozzle}"
                   + (f"（熔池 {self.nozzle_volume:g} mm³）" if self.nozzle_volume else ""))
        if self.extruder_variant:
            out.append(f"热端类型：{self.extruder_variant}")
        sp = f"{self.max_speed:g} mm/s" if self.max_speed else "未读到"
        ac = f"{self.max_accel:g} mm/s²" if self.max_accel else "未读到"
        tv = f"{self.max_travel_accel:g} mm/s²" if self.max_travel_accel else "未读到"
        out.append(f"机器上限：速度 {sp} · 加速度 {ac} · 空走加速度 {tv}")
        if self.max_jerk:
            out.append(f"机器 Jerk 上限：{self.max_jerk:g} mm/s")
        if self.min_layer_height and self.max_layer_height:
            out.append(f"机器层高区间：{self.min_layer_height:g} ~ {self.max_layer_height:g} mm")
        fv = f"{self.max_volumetric_speed:g} mm³/s" if self.max_volumetric_speed else "未读到"
        fr = f"{self.filament_flow_ratio:g}" if self.filament_flow_ratio else "未读到"
        out.append(f"耗材流量上限：{fv}（流量比 {fr}）· 耗材 {self.filament_type or '未知'}")
        if self.max_volumetric_source:
            out.append(f"流量上限来源：{self.max_volumetric_source}")
        # 打印板类型由 core/plate.py 出（带中文名与温度标定），这里不重复
        out.append(f"板面：{self.bed.summary()}")
        return out


def read(project: ThreeMfProject) -> HardwareInfo:
    """从工程里读出真机信息。读不到就留空，由上层决定回退策略。"""
    s = project.settings
    hw = HardwareInfo(from_project=True)

    # ---- 喷嘴 ----
    hw.nozzle_diameter = _first_num(s.get("nozzle_diameter"))
    hw.nozzle_volume = _first_num(s.get("nozzle_volume"))
    ev = _arr(s.get("print_extruder_variant"))
    if ev:
        hw.extruder_variant = str(ev[0])
    hw.hotend_heating_rate = _first_num(s.get("hotend_heating_rate"))
    hw.hotend_cooling_rate = _first_num(s.get("hotend_cooling_rate"))

    # ---- 机器上限 ----
    hw.max_speed = _first_num(s.get("machine_max_speed_x")) or _first_num(s.get("machine_max_speed_y"))
    hw.max_accel = _first_num(s.get("machine_max_acceleration_x")) or _first_num(s.get("machine_max_acceleration_y"))
    hw.max_travel_accel = _first_num(s.get("machine_max_acceleration_travel"))
    hw.max_jerk = _first_num(s.get("machine_max_jerk_x")) or _first_num(s.get("machine_max_jerk_y"))
    hw.max_speed_z = _first_num(s.get("machine_max_speed_z"))
    hw.max_accel_z = _first_num(s.get("machine_max_acceleration_z"))
    hw.min_layer_height = _first_num(s.get("min_layer_height"))
    hw.max_layer_height = _first_num(s.get("max_layer_height"))

    # ---- 耗材 ----
    ft = _arr(s.get("filament_type"))
    hw.filament_type = str(ft[0]) if ft else ""
    hw.max_volumetric_speed = _first_num(s.get("filament_max_volumetric_speed"))
    hw.filament_flow_ratio = _first_num(s.get("filament_flow_ratio"))
    if hw.max_volumetric_speed:
        hw.max_volumetric_source = "工程里 filament_max_volumetric_speed（你在这台机器上实测标定的）"

    # ---- 板面 ----
    bed = BedInfo()
    pa = _arr(s.get("printable_area"))
    pts: list[tuple[float, float]] = []
    for item in pa:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*[xX]\s*(-?\d+(?:\.\d+)?)", str(item))
        if m:
            pts.append((float(m.group(1)), float(m.group(2))))
    if pts:
        bed.x_min = min(p[0] for p in pts)
        bed.x_max = max(p[0] for p in pts)
        bed.y_min = min(p[1] for p in pts)
        bed.y_max = max(p[1] for p in pts)
    bed.exclude = [str(x) for x in _arr(s.get("wrapping_exclude_area")) if str(x).strip()]
    hw.bed = bed
    hw.plate_type = str(s.get("curr_bed_type") or "").strip()

    # ---- 元信息 ----
    hw.printer_model = str(s.get("printer_model") or "")
    hw.printer_settings_id = str(s.get("printer_settings_id") or "")
    ams = _arr(s.get("extruder_ams_count"))
    hw.ams_count = str(ams[0]) if ams else ""

    if not any([hw.nozzle_diameter, hw.max_speed, hw.max_accel, hw.filament_type, bed.known]):
        hw.from_project = False
    return hw
