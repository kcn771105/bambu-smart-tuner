"""参数规则引擎

输入：工程里读到的原始参数（字符串）、机型键、耗材键、喷嘴直径、模式键
输出：逐参数的「原始 → 优化后」对比行、写回用的字符串值、警告与说明

计算顺序（后面覆盖前面，最后统一钳制）：

    1. defaults               通用基准
    2. printers[].baseline    机型硬件基线
    3. filaments[].baseline   耗材基线
    4. modes[].ops            模式策略
    5. filaments[].mode_ops   耗材 × 模式微调
    6. interactions[]         交叉规则（含警告）
    7. nozzle 等比缩放        层高 / 线宽
    8. 钳制                   参数区间 → 机型速度/加速度上限 → 体积流量上限

任何一个值在写回前都保证落在 Bambu Studio 的合法区间内。
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import (adhesion, estimator, filament_write, hardware, hotend, ironing, nozzle_flow,
               seam_plan, special, thermal,
               support_model, support_plan, wall_compat,
               modes as modes_registry, schema, scope)


# ------------------------------------------------------------------ 数据结构

@dataclass
class ParamRow:
    key: str
    label: str
    group: str
    group_label: str
    old_raw: str | None
    new_raw: str            # 已格式化的字符串（写回内容）
    new_value: Any
    old_display: str
    new_display: str
    changed: bool
    will_write: bool
    reason: str
    skip_reason: str = ""
    scope: str = scope.PROCESS


@dataclass
class OptResult:
    rows: list[ParamRow]
    write_values: dict[str, str]
    skipped: list[ParamRow]
    warnings: list[str]
    notes: list[str]
    time: estimator.TimeEstimate
    values: dict[str, Any]
    printer_key: str
    printer_label: str
    filament_key: str
    filament_label: str
    mode_key: str
    mode_label: str
    nozzle: float
    #: 因归属被拦下的参数（机器页 / 耗材页），UI 单独列出来给用户看
    blocked: list[ParamRow] = field(default_factory=list)
    #: 本次实际使用的写入范围策略
    policy: scope.ScopePolicy | None = None
    #: 从工程同步来的真机信息
    hardware: hardware.HardwareInfo | None = None
    #: 按模型实测尺寸的定量推导明细（指标 / 实测 / 公式 / 结论），UI 与报告直接展示
    derivations: list[dict] = field(default_factory=list)
    #: 本次实际采用的体积流量上限 mm³/s（已按喷嘴折算过）
    flow_limit: float | None = None
    #: 工程喷嘴 vs 当前选择的喷嘴（不同就说明流量做过折算）
    project_nozzle: float | None = None
    #: 打印板同步结果（板型 / 温度 / 板面 / 兼容性），给 UI 与报告展示
    plate: str = ""
    hotend: str = ""
    #: 热床温度与风速的推导明细（指标 / 实测 / 公式 / 结论）
    thermal_rows: list[dict] = field(default_factory=list)
    #: 热床与风速的一句话说明
    thermal: str = ""
    #: 室温联动的一句话（「室温 12°C：热床 70→78°C、风扇再降 10 个百分点」）
    room_note: str = ""
    #: 接缝（含斜接缝）的一句话说明
    seam: str = ""
    #: 机型同步计划里的一句话说明（保存前由 UI 填）
    machine_sync_note: str = ""
    #: 支撑好拆档位（standard / easy / max）
    support_ease: str = "standard"
    #: 熨烫的推导明细与一句话说明
    ironing_rows: list[dict] = field(default_factory=list)
    ironing: str = ""
    #: 熨烫档位（keep / off / top / topmost / solid）
    ironing_choice: str = "keep"
    #: 用户手动指定的特殊模式说明（一项一行）
    special_notes: list[str] = field(default_factory=list)
    #: 耗材页处理方式（keep / file / new）与说明
    filament_mode: str = "file"
    filament_note: str = ""
    #: 每个最终写入的键「最后是被哪一层改的」。用来回答
    #: 「这是按我的模型算的，还是套预设」——按层名分组即可给出比例。
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def changed_count(self) -> int:
        return sum(1 for r in self.rows if r.changed and r.will_write)


# ------------------------------------------------------------------ 规则库加载

def default_rules_path() -> Path:
    """规则库位置。

    - 开发态：<项目>/rules/BambuRules.json
    - 打包态：优先用 exe 同级的 rules/BambuRules.json（放这里就能改，不用重新打包）；
      没有则回退到 PyInstaller 解包目录 _MEIPASS/rules 里的内置副本。
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        portable = exe_dir / "rules" / "BambuRules.json"
        if portable.exists():
            return portable
        base = Path(getattr(sys, "_MEIPASS", exe_dir))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "rules" / "BambuRules.json"


def load_rules(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else default_rules_path()
    if not p.exists():
        raise FileNotFoundError(f"规则库不存在：{p}")
    with open(p, "r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("规则库顶层必须是 JSON 对象")
    for need in ("defaults", "printers", "filaments", "modes"):
        if need not in data:
            raise ValueError(f"规则库缺少必需节点：{need}")
    return data


# ------------------------------------------------------------------ 引擎

KIND_STR = (schema.ENUM,)


def _coerce(s: schema.ParamSpec, v: Any) -> Any:
    if s.kind == schema.BOOL:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on", "开")
        return bool(v)
    if s.kind == schema.ENUM:
        return str(v)
    if s.kind in (schema.ARRAY_FLOAT, schema.ARRAY_PCT):
        # 规则库里可能写成 "50%" 或 ["50%"]，统一取数值
        f = schema.numeric(v)
        return None if f is None else f
    f = schema.numeric(v)
    if f is None:
        return None
    if s.kind == schema.INT:
        return int(round(f))
    return f


def _same(s: schema.ParamSpec, a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if s.kind in (schema.BOOL, schema.ENUM):
        return a == b
    return abs(float(a) - float(b)) < 10 ** (-max(2, s.decimals + 2))


class RulesEngine:
    def __init__(self, rules: dict):
        self.rules = rules
        self.defaults: dict = rules.get("defaults", {})
        self.printers: dict = rules.get("printers", {})
        self.filaments: dict = rules.get("filaments", {})
        self.modes: dict = rules.get("modes", {})
        self.interactions: list = rules.get("interactions", [])
        self.options: dict = rules.get("options", {})
        self.unknown_keys: set[str] = set()
        # 优化过程中的「用户当前值」缓存（由 optimize() 填）。
        # 作用：某个键如果规则库里没有基准值，但工程里有用户设好的值，
        # 那么后续层（模式/交叉/逐件形状）可以在用户值的基础上继续微调，
        # 而不是被跳过。
        self._user_values: dict[str, Any] = {}
        self.last_timecap: dict | None = None
        # 模式层/交叉规则层用「set」明确指定过的键：这些是用户选模式时的
        # 绝对意图，后续「按模型形状/几何」层不得用绝对值把它们翻掉
        # （只能在该值基础上做数值微调）。
        self._locked: set[str] = set()
        # 同一参数被多层 mul 连乘时的累计倍率（总闸用）。
        # 例：travel_speed 被「交叉规则 ×0.25」「形状层 ×0.9」「几何层 ×0.92」
        # 连乘成 ×0.207，1000 mm/s 被压到 207 —— 这不是调优，是层层叠加的副作用。
        self._gain: dict[str, float] = {}
        # 体积流量上限（_clamp_flow 算出后记录），时长估算用它算「实际能跑多快」
        self._flow_limit: float | None = None
        # 按模型实测尺寸的定量推导明细
        self._derivations: list[dict] = []
        self._plate_info: str = ""
        self._sources: dict[str, str] = {}
        self._shape_keys: set[str] = set()
        self._thermal_rows: list[dict] = []
        self._room_note = ""
        self._thermal_text: str = ""
        self._seam_text: str = ""
        self._machine_text: str = ""
        self._ironing_rows: list[dict] = []
        self._ironing_note: str = ""
        self._special_notes: list[str] = []
        self._filament_note: str = ""
        self._project_for_plate = None
        self._hotend = hotend.HotendInfo()
        self._hotend_detected = hotend.HotendInfo()
        self._hotend_mul: float = 1.0
        self._hotend_note: str = ""

    # -------------------------------------------------- 查询 / 自检

    def printer(self, key: str) -> dict:
        return self.printers.get(key) or self.printers.get("GENERIC") or {}

    def filament(self, key: str) -> dict:
        return self.filaments.get(key) or self.filaments.get("GENERIC") or {}

    def mode(self, key: str) -> dict:
        return self.modes.get(key) or {}

    def printer_choices(self) -> list[tuple[str, str]]:
        return [(k, v.get("label", k)) for k, v in self.printers.items()]

    def filament_choices(self) -> list[tuple[str, str]]:
        return [(k, v.get("label", k)) for k, v in self.filaments.items()]

    def mode_choices(self) -> list[tuple[str, str]]:
        return [(k, v.get("label", k)) for k, v in self.modes.items()]

    def validate(self) -> list[str]:
        """规则库自检：返回问题列表（键名不在参数表 / 模式引用不存在等）。"""
        problems: list[str] = []
        seen: set[str] = set()

        def check_map(where: str, mapping: dict):
            for k in mapping:
                if k not in schema.PARAMS:
                    problems.append(f"{where}：键 {k} 不在参数表中，已忽略")
                    seen.add(k)

        check_map("defaults", self.defaults)
        for key, node in self.printers.items():
            check_map(f"printers.{key}.baseline", node.get("baseline", {}))
        for key, node in self.filaments.items():
            check_map(f"filaments.{key}.baseline", node.get("baseline", {}))
            for m, ops in (node.get("mode_ops") or {}).items():
                check_map(f"filaments.{key}.mode_ops.{m}", ops)
        for m, node in self.modes.items():
            check_map(f"modes.{m}.ops", node.get("ops", {}))
        for it in self.interactions:
            check_map(f"interactions.{it.get('id', '?')}.set", it.get("set", {}))
            check_map(f"interactions.{it.get('id', '?')}.ops", it.get("ops", {}))
        if not self.modes:
            problems.append("modes 为空：没有任何优化模式可用")
        if "GENERIC" not in self.printers:
            problems.append("printers 缺少 GENERIC 兜底项")
        if "GENERIC" not in self.filaments:
            problems.append("filaments 缺少 GENERIC 兜底项")
        return problems

    # -------------------------------------------------- 主流程

    def optimize(self, current: dict[str, str], *,
                 printer_key: str, filament_key: str, nozzle: float,
                 mode_key: str, detection_warnings: list[str] | None = None,
                 detection_notes: list[str] | None = None,
                 filament_overlay: dict | None = None,
                 model_profile=None,
                 time_cap_pct: float | None = None,
                 hardware_info: hardware.HardwareInfo | None = None,
                 nozzle_explicit: bool = False,
                 hotend_flow: str | None = None,
                 support_mode: str = "auto",
                 support_ease: str = "standard",
                 room_temp_c: float | None = None,
                 bed_type: str = "",
                 fan_trim: int | None = None,
                 seam_smooth: bool = True,
                 bed_keep_temp: float | None = None,
                 ironing_choice: str = "keep",
                 ironing_auto: bool = True,
                 filament_mode: str = "file",
                 special_modes: dict | None = None) -> OptResult:
        """filament_overlay：来自 Bambu Studio 用户预设的覆盖层（bambu_profiles.to_overlay）。
        model_profile：core.model_analysis.ModelProfile，按模型形状做最后一层微调。
        time_cap_pct：时长涨幅上限（%）。给了就把算出结果往回调，直到落在上限内。
                      强度优先模式通常不设限，交给调用方决定。
        hardware_info：core.hardware.HardwareInfo，从工程读出的真机上限/喷嘴/板面，
                      用来把工艺参数钳制在这台机器真实能力之内。
        support_ease：支撑好拆程度 standard/easy/max（顶面 Z 间隙与接触面）。
        room_temp_c：室温（°C）。与 bed_type、filament_key 一起推导热床温度与风速。
        bed_type：打印板类型；留空则从工程 curr_bed_type 读。
        fan_trim：风扇强弱。None=自动（按耗材基线，冷天自动降一档）；
                  整数=手动偏置（百分点，正数更猛、负数更保守，不再叠加自动修正）。
        seam_smooth：是否对圆柱/细高件启用斜接缝（让外壁接缝几乎看不见）。
        bed_keep_temp：换板子时沿用原板温（°C）。工程原本的板本机 Studio 不认识时，
                      界面会换成它认识的板，但温度不该跟着新板基线走。
        ironing_choice：熨烫档位 keep / off / top / topmost / solid（后四个对应 Studio 的
                 ironing_type，keep = 不动你原来的设置）。
        ironing_auto：熨烫参数（流量/间距/速度/图案）是否由本工具按耗材算；False 则只改类型。
        filament_mode：耗材页怎么写 keep / file / new。keep = 耗材页一个字节都不写；
                       new = 参数照写，另外把耗材名改成「原名 + 优化」（Studio 里另存即得新预设）。
        special_modes：{参数键: 值}，用户在「特殊模式」里手动选的项；未出现的键一律不动。
        """
        pnode = self.printer(printer_key)
        fnode = self.filament(filament_key)
        mnode = self.mode(mode_key)
        if not mnode:
            raise ValueError(f"未知优化模式：{mode_key}")

        warnings: list[str] = list(detection_warnings or [])
        notes: list[str] = list(detection_notes or [])
        self.last_timecap = None          # 每次优化重置，避免读到上一次的残留
        self._gain = {}                   # 叠乘总闸的累计倍率，每次优化重置
        self._derivations = []
        self._plate_info = ""
        self._sources = {}
        self._shape_keys = set()
        self._thermal_rows = []
        self._room_note = ""
        self._thermal_text = ""
        self._seam_text = ""
        self._ironing_rows = []
        self._ironing_note = ""
        self._special_notes = []
        self._filament_note = ""
        self._project_for_plate = current
        # 热端流量类型：UI 传了就用传的，没传就按工程自动识别
        self._hotend_detected = hotend.detect(current)
        self._hotend = self._hotend_detected
        picked = hotend.normalize(hotend_flow or "")
        if picked:
            self._hotend = hotend.HotendInfo(
                picked, source_key="用户选择", source_value=str(hotend_flow),
                nozzle_volume=self._hotend.nozzle_volume,
                variants=self._hotend.variants, detected=True)
        # 分槽参数（outer_wall_speed 等）是按热端变体分槽的：先告诉 schema 有几个槽位，
        # 写回时才会把每个槽位都写上新值，否则 Studio 切到高流量热端读第 1 槽会「看起来没改」
        # 这是模块级全局，出 optimize 时复原，避免影响同一进程里的其他调用（含测试）
        _prev_slots = schema.variant_slots()
        schema.set_variant_slots(hotend.slot_count(current))
        self._hotend_mul, self._hotend_note = hotend.factor(self.rules, self._hotend.key)
        notes.append(
            f"热端流量类型：{self._hotend.label}"
            + (f"（体积流量上限 ×{self._hotend_mul:g}）" if self._hotend_mul > 1.0
               else "（按官方标配流量）")
            + (f"；{self._hotend_note}" if self._hotend_note else ""))
        values: dict[str, Any] = {}
        reasons: dict[str, list[str]] = defaultdict(list)

        write_soft = bool(self.options.get("write_soft_keys", False))
        policy = scope.ScopePolicy.from_rules(self.rules)
        # ---- 真机同步：把喷嘴/流量/机器上限对齐到工程里的真实值
        hw = hardware_info
        nozzle = float(nozzle)
        if hw is not None:
            if hw.nozzle_diameter:
                if nozzle_explicit and abs(float(hw.nozzle_diameter) - nozzle) > 1e-9:
                    warnings.append(
                        f"工程里记录的喷嘴是 {float(hw.nozzle_diameter):g} mm，"
                        f"你选的是 {nozzle:g} mm——已按你选的 {nozzle:g} mm 计算，"
                        "请确认换过喷嘴后 Bambu Studio 的机型预设也换过了。")
                else:
                    nozzle = float(hw.nozzle_diameter)
                    notes.append(f"喷嘴直径已按工程同步为 {nozzle:g} mm。")
            if hw.max_volumetric_speed:
                notes.append(
                    f"体积流量上限采用工程里用户标定的 {hw.max_volumetric_speed:g} mm³/s"
                    "（耗材页，只读不写），比内置耗材基线更贴合你的热端。")
            if hw.max_speed or hw.max_accel:
                notes.append(
                    f"机器硬件上限采用工程真值：速度 "
                    f"{hw.max_speed or 0:g} mm/s、加速度 {hw.max_accel or 0:g} mm/s²"
                    "（机器页，只读不写），工艺参数不会超过它。")
            if hw.bed.known:
                notes.append(f"板面已同步：{hw.bed.summary()}（机器页，只读不写）。")

        # ---- 0：解析工程里的用户当前值（供后续层在用户值基础上微调）
        self._user_values = {}
        for key, s in schema.PARAMS.items():
            raw = current.get(key)
            if raw is None:
                continue
            v = schema.parse_value(s, raw)
            if v is not None:
                self._user_values[key] = v

        # ---- 1/2/3：三层基线
        # 「通用基准」只在工程里没有这个键时才写默认值；
        # 工程里已经有的值 = 用户自己挑的起点，一律拿来当基准，
        # 后面几层（模式/交叉/逐件几何）在这个起点上继续调。
        respect_project = bool(self.options.get("respect_project_values", True))
        self._apply_set(values, reasons, self.defaults, "通用基准", warnings,
                        respect_project=respect_project)
        self._apply_set(values, reasons, pnode.get("baseline", {}),
                        f"机型基线 {pnode.get('label', printer_key)}", warnings)
        self._apply_set(values, reasons, fnode.get("baseline", {}),
                        f"耗材基线 {fnode.get('label', filament_key)}", warnings)

        # ---- 4/5：模式策略
        # 模式档用「set」定下的键视为用户的明确选择：逐件几何层不得再翻掉。
        mode_label = mnode.get("label", mode_key)
        self._apply_ops(values, reasons, mnode.get("ops", {}), f"{mode_label}", warnings,
                        lock=True, band=False)
        self._apply_ops(values, reasons, (fnode.get("mode_ops") or {}).get(mode_key, {}),
                        f"{mode_label} × {fnode.get('label', filament_key)}", warnings,
                        lock=True, band=False)

        # ---- 4.5：Bambu Studio 用户自定义耗材覆盖层
        # 用户/厂商在自己预设里标定过的值最可信，放在内置基线之后、交叉规则之前覆盖。
        if filament_overlay:
            ov_label = filament_overlay.get("label") or "自定义耗材"
            if filament_overlay.get("baseline"):
                self._apply_set(values, reasons, filament_overlay["baseline"],
                                f"自定义耗材 {ov_label}", warnings)
            notes.append(
                f"已套用自定义耗材「{ov_label}」的标定值（族 {filament_overlay.get('family', '?')}）；"
                f"体积流量上限取 "
                f"{(filament_overlay.get('limits') or {}).get('max_volumetric_speed', '默认')} mm³/s。"
            )

        # ---- 6：交叉规则
        ctx = {
            "printer": printer_key,
            "printer_group": pnode.get("group", ""),
            "filament": filament_key,
            "mode": mode_key,
            "nozzle": float(nozzle),
        }
        for it in self.interactions:
            if not self._match(it.get("when", {}), ctx):
                continue
            label = it.get("label") or it.get("id", "交叉规则")
            if it.get("set"):
                # 交叉规则用绝对值定下的键 = 明确选择（如 PETG 的空走 250），
                # 后续「速度下限保护」不得把它抬回去。
                self._apply_set(values, reasons, it["set"], f"交叉规则 {label}", warnings,
                                lock=True)
            if it.get("ops"):
                self._apply_ops(values, reasons, it["ops"], f"交叉规则 {label}", warnings,
                                lock=True)
            if it.get("warn"):
                warnings.append(it["warn"])

        # ---- 7：喷嘴等比缩放
        if self.options.get("nozzle_scaling", True):
            ratio = float(nozzle) / 0.4
            if abs(ratio - 1.0) > 1e-6:
                notes.append(f"已按喷嘴 {nozzle:g} mm 对层高/线宽做等比缩放（系数 {ratio:.2f}）。")
                for key, s in schema.PARAMS.items():
                    if s.nozzle_scaled and key in values and isinstance(values[key], (int, float)):
                        old = float(values[key])
                        values[key] = old * ratio
                        reasons[key].append(f"喷嘴缩放 ×{ratio:.2f}")

        # ---- 7.5：逐件形状自适应（在模式档/交叉规则之上做「按件」微调，
        #            但不改它们的绝对选项——那是模式档替用户做的选择）
        # 逐个对象判形状原型 → 逐个对象出参数 → 合并成全局（最保守者胜）
        if model_profile is not None:
            try:
                from . import shape_rules
                # 模式档自己算出的判定角（精细 20°、超精细 15°、草稿 35°）
                # 传给支撑层，让它别再自己改一档。
                mode_angle = values.get("support_threshold_angle")
                try:
                    mode_angle = float(mode_angle)
                except (TypeError, ValueError):
                    mode_angle = None
                ops, mnotes = shape_rules.suggest(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    profiles=self.rules.get("shape_profiles"),
                    support_policy=self.rules.get("support_policy"),
                    user_threshold_angle=self._user_values.get("support_threshold_angle"),
                    user_enable_support=self._user_values.get("enable_support"),
                    mode_angle=mode_angle)
                if ops:
                    self._apply_ops(values, reasons, ops, "逐件形状自适应", warnings,
                                   allow_preserve=True, respect_locked=True)
                # 记下形状层动过的键：后面几何层/推导层不得对同一个键再乘一次，
                # 否则「首层慢一点」会被三家各乘 0.85 连乘成 0.61（用户实测
                # 一个普通盒子的首层速度被 50 → 36，就是这么叠出来的）。
                self._shape_keys = {k for k, v in self._sources.items()
                                    if v == "逐件形状自适应"}
                notes.extend(mnotes)
                tags = model_profile.tags()
                if tags:
                    notes.append("形状识别：" + "、".join(tags) + "。")
            except TypeError:
                # shape_rules 还没升级到带新参数的版本（向后兼容）
                from . import shape_rules
                ops, mnotes = shape_rules.suggest(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    profiles=self.rules.get("shape_profiles"),
                    support_policy=self.rules.get("support_policy"))
                if ops:
                    self._apply_ops(values, reasons, ops, "逐件形状自适应", warnings,
                                   allow_preserve=True, respect_locked=True)
                notes.extend(mnotes)
            except Exception as exc:            # 形状层出错不能影响主流程
                warnings.append(f"模型形状分析失败（已跳过形状自适应）：{exc}")

        # ---- 7.6：几何驱动层（按几何事实逐项调工艺，覆盖全部工艺组）
        # 形状层只覆盖 34/272 项，这里补齐全工艺组的针对性调整。
        if model_profile is not None:
            try:
                from . import geom_rules
                gctx = geom_rules.build_ctx(model_profile)
                grules = geom_rules.parse_rules(self.rules.get("geometry_rules"))
                gops, gnotes = geom_rules.apply(gctx, mode=mode_key, rules=grules)
                if gops:
                    self._apply_ops(values, reasons, gops, "几何驱动细调", warnings,
                                   allow_preserve=True, respect_locked=True,
                                   no_remul=self._shape_keys)
                notes.extend(gnotes)
                self._geom_ctx = gctx
            except Exception as exc:            # 几何层出错不能影响主流程
                warnings.append(f"几何驱动层计算失败（已跳过该项细调）：{exc}")

        # ---- 7.7：按模型实测尺寸做**定量**推导
        # 形状层回答「这属于哪一类」，这一层回答「具体是多少」：
        # 墙圈数 = 实测壁厚 ÷ 线宽、层高上限 = 最薄特征 ÷ 2、
        # 首层速度 = f(接触面积)、壳层数 = 目标壳厚 ÷ 层高。
        # 放在几何层之后、钳制之前：它的输出同样要过 8a~8d 的硬约束。
        if model_profile is not None:
            try:
                from . import model_tuning
                der = model_tuning.derive(
                    model_profile,
                    nozzle=float(nozzle),
                    line_width=values.get("outer_wall_line_width"),
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    filament_key=filament_key,
                    current={**self._user_values, **values},
                )
                if der.ops:
                    self._apply_ops(values, reasons, der.ops, "按模型实测尺寸推导",
                                    warnings, respect_locked=True)
                notes.extend(der.notes)
                self._derivations = [r.as_dict() for r in der.rows]
            except Exception as exc:            # 定量推导失败不能影响主流程
                warnings.append(f"按模型实测尺寸推导失败（已跳过该项）：{exc}")

        # ---- 7.8：打印板同步（板型兼容性 / 板面尺寸 / 模型放得下吗）
        # 板型与板面都在机器页、耗材页 —— 只读不写。这一层做三件事：
        #   ① 用官方温度判断「这条料能不能在这块板上打」（温度 0 = 不支持）
        #   ② 板面尺寸与机型官方值对不上就报警（机型识别错 / 工程来自别的机器）
        #   ③ 按板型给几条工艺微调（写在 rules 的 plates 段，可自己改）
        try:
            from . import plate as plate_mod
            pinfo = plate_mod.read(self._project_for_plate or {}, self.rules)
            if pinfo is not None:
                pw, pn, pops = plate_mod.check(
                    pinfo, rules=self.rules, printer_key=printer_key,
                    filament_key=filament_key, profile=model_profile)
                warnings.extend(pw)
                notes.extend(pn)
                if pops:
                    self._apply_ops(values, reasons, pops,
                                    "打印板（板型）适配", warnings,
                                    respect_locked=True)
                self._plate_info = pinfo.summary_line()
        except Exception as exc:            # 板层出错不能影响主流程
            warnings.append(f"打印板适配计算失败（已跳过该项）：{exc}")

        # ---- 7.85：热床温度与风速（耗材 × 板子 × 室温）
        # 用户反馈第 2 条：「不同耗材、不同板子、不同室温下设置的热床温度和风速，
        # 要不然有的模型在天冷了会翘边」。
        # 这三件事必须一起看：板子决定基线温度、耗材决定风扇档位、室温决定加温量。
        # 输出写的是**耗材页**的键（*_plate_temp / fan_*），所以必须走耗材槽声明，
        # 否则 Studio 会用耗材预设把它们覆盖回去（见 core/preset_diff.py）。
        try:
            from . import thermal as thermal_mod
            th = thermal_mod.derive(
                self.rules, current,
                filament_key=filament_key,
                bed_type=bed_type or "",
                room_temp_c=room_temp_c,
                printer_key=printer_key,
                fan_trim=fan_trim,
                bed_keep_temp=bed_keep_temp)
            if th.ops:
                # 用户在自己预设里标定过的键（覆盖层 baseline）优先，本层不翻它
                ov_keys = set((filament_overlay or {}).get("baseline") or {})
                if ov_keys:
                    kept = {k: v for k, v in th.ops.items() if k not in ov_keys}
                    dropped = sorted(set(th.ops) - set(kept))
                    if dropped:
                        notes.append("热床与风速：" + "、".join(dropped)
                                     + " 沿用你在耗材预设里标定的值，没有覆盖。")
                    th.ops = kept
            if th.ops:
                # 单项 op 格式是 {"set": v}，转成 _apply_ops 认的 dict
                self._apply_ops(values, reasons, th.ops, "热床与风速（耗材×板子×室温）",
                                warnings, allow_preserve=True, respect_locked=False)
            if th.rows:
                self._thermal_rows = [r.as_dict() for r in th.rows]
                self._room_note = getattr(th, "room_note", "") or ""
                for r in th.rows:
                    self._derivations.append(r.as_dict())
            notes.extend(th.notes)
            # 官方明确不支持「这条料 × 这块板」：这是硬警告，不能只躺在 notes 里
            if getattr(th, "unsupported", ""):
                warnings.append(
                    f"⚠ 官方不支持：{th.unsupported}。板温没有改，请先在 Bambu Studio 的"
                    "「打印板类型」里换一块这块料支持的板（或换料），否则首层会粘不住或撕板。")
                self._thermal_text = f"官方不支持 {th.unsupported}：板温未改，只给警告。"
            if th.ops:
                self._thermal_text = (
                    f"热床与风速已按「{filament_key} × {thermal_mod.bed_type_of(current) if not bed_type else bed_type}"
                    f" × 室温 {room_temp_c:g}°C」推导 {len(th.ops)} 项"
                    if room_temp_c is not None else
                    f"热床与风速已按「{filament_key} × {bed_type or thermal_mod.bed_type_of(current)}」推导 {len(th.ops)} 项")
        except Exception as exc:            # 热床层出错不能影响主流程
            warnings.append(f"热床与风速计算失败（已跳过该项）：{exc}")

        # ---- 7.86：接缝与斜接缝（圆柱体接缝光滑）
        # 用户反馈第 4 条：「可以让圆柱体的接缝光滑吗」。
        # 圆件没有棱角藏接缝，只能靠斜接缝（scarf）把竖线斜过去；
        # apply_scarf_seam_on_circles 是官方那条开关，很多工程里被拷成 0。
        try:
            sp = seam_plan.plan(model_profile, layer_height=float(values.get("layer_height", 0.2) or 0.2),
                                current=current, enabled=bool(seam_smooth))
            if sp.ops:
                se_ops = {k: {"set": v} for k, v in sp.ops.items()}
                self._apply_ops(values, reasons, se_ops, "接缝与斜接缝",
                                warnings, allow_preserve=True, respect_locked=False)
            notes.extend(sp.notes)
            if sp.rows:
                for r in sp.rows:
                    self._derivations.append(r)
            if sp.ops:
                self._seam_text = ("斜接缝已开启（圆形轮廓也做斜接），"
                                   "圆柱侧面那条竖线会被斜面盖住。" if "seam_slope_type" in sp.ops
                                   else "接缝位置已按几何调整。")
        except Exception as exc:
            warnings.append(f"接缝策略计算失败（已跳过该项）：{exc}")

        # ---- 7.87：熨烫（你选熨不熨、熨哪儿；流量/间距/速度/图案按耗材算）
        try:
            ip = ironing.plan(choice=ironing_choice, auto=bool(ironing_auto),
                              filament_key=filament_key,
                              layer_height=float(values.get("layer_height", 0.2) or 0.2),
                              nozzle=float(nozzle or 0.4), mode_key=mode_key,
                              current=current, rules=self.rules)
            if ip.ops:
                self._apply_ops(values, reasons,
                                {k: {"set": v} for k, v in ip.ops.items()},
                                "熨烫", warnings,
                                allow_preserve=True, respect_locked=False)
            if ip.rows:
                self._ironing_rows = [dict(r) for r in ip.rows]
                for r in ip.rows:
                    self._derivations.append(dict(r))
            if ip.note:
                self._ironing_note = ip.note
                notes.append(ip.note)
        except Exception as exc:            # 熨烫出错不能影响主流程
            warnings.append(f"熨烫设置失败（已跳过该项）：{exc}")

        # ---- 7.88：其他页的特殊模式（只写用户手动选的那几项，其余一律不动）
        try:
            sm = special.plan(special_modes, self.rules)
            if sm.ops:
                self._apply_ops(values, reasons,
                                {k: {"set": v} for k, v in sm.ops.items()},
                                "你手动选的特殊模式", warnings,
                                allow_preserve=False, respect_locked=False)
            if sm.notes:
                self._special_notes = list(sm.notes)
                notes.extend(sm.notes)
            if sm.rows:
                for r in sm.rows:
                    self._derivations.append(dict(r))
        except Exception as exc:
            warnings.append(f"特殊模式设置失败（已跳过）：{exc}")

        # ---- 7.75：裙边定量（小件 / 底面小 / 易倒 → 加宽裙边）
        # 「倒不倒」用倾覆指数算：高 ÷ √底面积 ×(1+重心偏移比)
        if model_profile is not None:
            try:
                lw = 0.42
                try:
                    lw = float(values.get("line_width") or 0.42)
                except (TypeError, ValueError):
                    pass
                ad_ops, ad_notes, ad_rows = adhesion.tune(
                    model_profile,
                    line_width=lw,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    filament_key=filament_key,
                    mode=mode_key,
                    current={k: self._user_values.get(k, values.get(k))
                             for k in ("brim_width", "brim_type", "brim_object_gap")})
                if ad_ops:
                    self._apply_ops(values, reasons, ad_ops, "裙边定量（易倒件）",
                                    warnings, allow_preserve=True, respect_locked=False)
                notes.extend(ad_notes)
                for r in ad_rows:
                    self._derivations.append(r.as_dict())
            except Exception as exc:
                warnings.append(f"裙边定量计算失败（已跳过）：{exc}")

        # ---- 7.76：支撑按模型尺寸定量（密度/间隙/安全距/形态）
        # 白名单先给两个决策键；support_model 算出什么就允许什么
        self._support_allowed = {"enable_support", "support_threshold_angle"}
        # 支撑开关：auto = 按模型判断（默认）；on = 强制开启；off = 强制关闭
        _support_mode = (support_mode or "auto").lower()
        _support_before = support_model._truthy(values.get("enable_support"))
        # 工程原始状态（判断「这次是不是我们给打开的」，去 Studio 里核对落点用）
        _support_in_project = support_model._truthy((current or {}).get("enable_support"))
        if _support_mode == "off":
            if _support_before:
                self._apply_ops(values, reasons, {"enable_support": {"set": False}},
                                "你选择强制关闭支撑", warnings, allow_preserve=True)
                notes.append("支撑：按你的选择强制关闭（模型悬垂部分需要你自己处理）。")
        elif _support_mode == "on" and not _support_before:
            self._apply_ops(values, reasons, {"enable_support": {"set": True}},
                            "你选择强制开启支撑", warnings, allow_preserve=True)
            notes.append("支撑：按你的选择强制开启。")
        # 7.761：自动档先按几何决定「要不要开支撑、判定角多少」。
        # 不做这一步，「支撑根据模型调」只调了密度/形态，开关却一直不动 ——
        # 有悬垂的件照样一张支撑都不长，用户看到的就是「支撑还是不对」。
        if model_profile is not None and _support_mode == "auto":
            try:
                from . import support_plan as _sp

                def _ang(v):
                    try:
                        if isinstance(v, (list, tuple)):
                            v = v[0] if v else None
                        return float(str(v).strip().rstrip("%")) if v is not None else None
                    except (TypeError, ValueError):
                        return None

                dec = _sp.decide(
                    model_profile, mode=mode_key,
                    policy=self.rules.get("support_policy"),
                    user_threshold_angle=_ang((current or {}).get("support_threshold_angle")),
                    user_enable_support=(_support_in_project if current
                                         and "enable_support" in current else None),
                    has_model=True)
                if dec.ops:
                    self._support_allowed |= set(dec.ops)
                    self._apply_ops(values, reasons, dec.ops, "支撑按模型几何",
                                    warnings, allow_preserve=True, respect_locked=False)
                notes.extend(dec.reasons[:3])
                if dec.enable and not _support_before:
                    self._support_allowed.add("enable_support")
                    self._apply_ops(values, reasons, {"enable_support": {"set": True}},
                                    "支撑按模型几何（有悬垂）", warnings,
                                    allow_preserve=True, respect_locked=False)
                    warnings.append(
                        "模型有悬垂，已按几何自动开启支撑：请到 Bambu Studio 里看一眼支撑落点，"
                        "不该有支撑的位置用「阻止支撑」刷子刷掉，或在「支撑」下拉里选「强制关闭」。")
                elif not dec.enable and _support_before and not _support_in_project:
                    pass   # 用户/工程里本来就开着，几何说不用也不擅自关
            except Exception as exc:
                warnings.append(f"支撑开关的几何判断失败（已保留原设置）：{exc}")

        if model_profile is not None:
            try:
                def _as_num(v, default=None):
                    try:
                        if isinstance(v, (list, tuple)):
                            v = v[0] if v else default
                        return float(str(v).strip().rstrip("%"))
                    except (TypeError, ValueError):
                        return default

                su = support_model.tune(
                    model_profile,
                    layer_height=_as_num(values.get("layer_height"), 0.2) or 0.2,
                    mode=mode_key,
                    values=dict(values),
                    judge_angle=_as_num(values.get("support_threshold_angle")),
                    nozzle=float(nozzle or 0.4),
                    line_width=_as_num(values.get("line_width")),
                    max_speed=(hw.max_speed if hw else None),
                    ease=support_ease)
                # 支撑参数的唯一决策者是 core/support_model.py：
                # 这里只登记「本层允许写哪些键」，真正的清理在块外无条件执行
                self._support_allowed |= set(su.ops)
                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)
                notes.extend(su.reasons)
                for r in su.rows:
                    self._derivations.append(r.as_dict())
                # 自动档把支撑打开了：提醒用户去 Studio 里核一眼支撑落点
                if (_support_mode == "auto" and not _support_before
                        and support_model._truthy(values.get("enable_support"))):
                    warnings.append(
                        "已自动开启支撑（模型有悬垂）：请到 Bambu Studio 里看一眼支撑落点——"
                        "如果某些位置不该有支撑，用「支撑/阻止支撑」刷子手动拦掉，"
                        "或在模式区的「支撑」下拉里选「强制关闭」。")
            except Exception as exc:
                warnings.append(f"支撑按模型计算失败（已跳过）：{exc}")

        # 支撑键的单一来源兜底：不论有没有模型几何、不管上游哪一层写过，
        # 白名单之外的 support_* 全部撤回（否则会出现「支撑没开却改了间隙」的噪音）
        for _k in [k for k in list(values) if support_model.is_support_key(k)]:
            if _k not in getattr(self, "_support_allowed", set()):
                values.pop(_k, None)
                reasons.pop(_k, None)

        # 自动档把支撑打开了：提醒去 Studio 核一眼落点（支撑位置最终要人看过才放心）
        if (_support_mode == "auto" and not _support_in_project
                and support_model._truthy(values.get("enable_support"))):
            warnings.append(
                "已自动开启支撑（工程里原本是关的，模型有悬垂）：请到 Bambu Studio 里看一眼"
                "支撑落点——某些位置不该有支撑就用「支撑/阻止支撑」刷子手动拦掉，"
                "或在模式区的「支撑」下拉里选「强制关闭」。自动档只管开不开和用多少料，"
                "支撑落在哪里只有你能判断。")

        # ---- 7.77：交替额外墙层 / 垂直外壳厚度 / 墙层数 三者一致性
        try:
            wc_ops, wc_warns, wc_notes = wall_compat.check(values, project=current)
            if wc_ops:
                self._apply_ops(values, reasons, wc_ops, "墙参数一致性（Studio 要求成套）",
                                warnings, allow_preserve=True, respect_locked=False)
            warnings.extend(wc_warns)
            notes.extend(wc_notes)
        except Exception as exc:
            warnings.append(f"墙参数一致性检查失败（已跳过）：{exc}")

        # ---- 8a：参数自身合法区间
        self._clamp_schema(values, reasons, warnings)
        # ---- 8b：喷嘴相关收紧（层高 / 线宽）
        self._clamp_nozzle(values, reasons, float(nozzle), pnode, warnings)
        # ---- 8c：机型硬件上限（优先用工程里的真机上限）
        self._clamp_machine(values, reasons, pnode, fnode, warnings, hw=hw)
        # ---- 8d：体积流量上限（优先用工程里用户标定的流量）
        if self.options.get("volumetric_speed_guard", True):
            overlay_max = (filament_overlay or {}).get("limits", {}).get("max_volumetric_speed")
            self._clamp_flow(values, reasons, pnode, fnode, warnings,
                             overlay_max=overlay_max,
                             project_max=(hw.max_volumetric_speed if hw else None),
                             printer_key=printer_key, nozzle=float(nozzle),
                             project_nozzle=(hw.nozzle_diameter if hw else None),
                             filament_key=filament_key)

        # ---- 8e：时长上限回调
        # 调用方没给上限时，用模式档自带的预算（规则库 modes.<k>.time_budget_pct）。
        # 这样「均衡档最多慢 40%」「草稿档不该变慢」是规则库保证的，
        # 而不是靠 UI 记得去传一个数字。
        if time_cap_pct is None:
            budget = mnode.get("time_budget_pct")
            try:
                time_cap_pct = float(budget) if budget is not None else None
            except (TypeError, ValueError):
                time_cap_pct = None
            if time_cap_pct is not None:
                notes.append(
                    f"已按「{mode_label}」的时长预算执行：涨幅上限 {time_cap_pct:g}%"
                    f"（{mnode.get('time_budget_note', '可在规则库 modes 里改')}）。")
        old_for_estimate: dict[str, Any] = {}
        for key, s in schema.PARAMS.items():
            if key not in values:
                continue
            old_val = schema.parse_value(s, current.get(key))
            old_for_estimate[key] = old_val if old_val is not None else values[key]
        if time_cap_pct is not None:
            self._enforce_time_cap(values, reasons, old_for_estimate, warnings,
                                   notes, float(time_cap_pct), mode_for_budget=mode_key)
            # 回调可能把速度提回，必须再过一遍硬约束，否则会突破体积流量/机型上限。
            # 顺序要紧：喷嘴约束必须在机器/流量之前，因为回调会抬高层高，
            # 而层高抬到喷嘴允许上限之上就会写出非法值（旧版漏了这一步）。
            self._clamp_schema(values, reasons, [])
            self._clamp_nozzle(values, reasons, float(nozzle), pnode, [])
            self._clamp_machine(values, reasons, pnode, fnode, [], hw=hw)
            if self.options.get("volumetric_speed_guard", True):
                self._clamp_flow(values, reasons, pnode, fnode, [],
                                 overlay_max=(filament_overlay or {}).get("limits", {}).get("max_volumetric_speed"),
                                 project_max=(hw.max_volumetric_speed if hw else None),
                                 printer_key=printer_key, nozzle=float(nozzle),
                                 project_nozzle=(hw.nozzle_diameter if hw else None),
                                 filament_key=filament_key)

        # ---- 7.89：螺旋（花瓶）模式的配套项
        # 螺旋模式在 Studio 里不是一个孤立开关：它要求单壁、无填充、无顶面、无支撑。
        # 只把 spiral_mode 打开、别的留着，切片器直接报
        # 「Param values in 3mf/config error」拒绝切片（实测 4 种组合）。
        # 填充与顶面层由切片器自己按模式强制（schema 下限也不允许写 0），
        # 所以这里只配套两件必须由我们写的事：单壁墙 + 关支撑。
        if special.truthy(values.get("spiral_mode")):
            sp_ops = {"wall_loops": {"set": 1}, "enable_support": {"set": 0}}
            need = {k: v for k, v in sp_ops.items()
                    if str(values.get(k, "")).strip() not in (str(v["set"]).strip(),)}
            if need:
                self._apply_ops(values, reasons, need, "螺旋（花瓶）模式的配套项",
                                warnings, allow_preserve=False, respect_locked=False)
                msg = ("你选了螺旋（花瓶）模式：这个模式只能单壁、无填充、无顶面、不能加支撑，"
                       "已自动配套「墙层数 1 + 关支撑」；填充/顶面层由切片器按该模式强制，"
                       "不配套会直接切不了片。")
                warnings.append(msg)
                notes.append(msg)

        # ---- 耗材页处理方式（keep / file / new）
        _fil_mode = filament_write.normalize(filament_mode)
        if _fil_mode == "keep":
            self._filament_note = ("你选了「不改耗材页」：热床温度、风速、喷头温度、"
                                   "压力提前、流量比这些耗材页的键一个都不写，只调工艺参数。")
        elif _fil_mode == "new":
            self._filament_note = ("耗材参数照写，保存时会把耗材另存为「原名 + 优化」——"
                                   "Studio 里点保存就多出一份新耗材，你原来那份不会被改。")
        if self._filament_note:
            notes.append(self._filament_note)

        # ---- 组装
        rows: list[ParamRow] = []
        write_values: dict[str, str] = {}
        skipped: list[ParamRow] = []
        blocked: list[ParamRow] = []
        seen: set[str] = set()

        for key, s in schema.PARAMS.items():
            old_raw = current.get(key)
            old_val = schema.parse_value(s, old_raw)
            if key not in values:
                continue
            seen.add(key)

            new_val = schema.clamp(s, values[key]) if s.kind not in KIND_STR + (schema.BOOL,) else values[key]
            new_raw = schema.format_value(s, new_val, old_raw)
            changed = not _same(s, old_val, new_val)

            exists = key in current
            # 热床温度 / 风速 / 接缝是工程文件的标准键：老工程里可能没存这几行，
            # 但补写进去 Studio 认，不补就等于「热床风扇接缝怎么设都不生效」。
            will_write = (exists or write_soft
                          or key in thermal.STANDARD_KEYS
                          or key in seam_plan.STANDARD_KEYS
                          or key in support_model.SUPPORT_KEYS
                          or key in ironing.STANDARD_KEYS)
            skip_reason = ""
            if not will_write:
                skip_reason = "当前工程未存储该参数（机型/版本差异），已跳过写入"

            reason = " → ".join(dict.fromkeys(reasons.get(key, ["默认基准"])))
            row = ParamRow(
                key=key, label=s.label, group=s.group, group_label=s.group_label,
                old_raw=old_raw, new_raw=new_raw, new_value=new_val,
                old_display=schema.display(s, old_val) if old_val is not None else "—",
                new_display=schema.display(s, new_val),
                changed=changed, will_write=will_write, reason=reason,
                skip_reason=skip_reason, scope=policy.scope(key),
            )
            rows.append(row)
            if not will_write:
                skipped.append(row)
                continue
            # ---- 你选了「不改耗材页」：耗材页/热床页的键一概不写
            if _fil_mode == "keep" and policy.scope(key) in ("filament", "thermal"):
                row.will_write = False
                row.skip_reason = "你选了「不改耗材页」，这一项不写（只调工艺参数）"
                blocked.append(row)
                continue
            # ---- 写入范围闸门：机器页/耗材页/元数据一律不写
            if not policy.allows(key):
                row.will_write = False
                row.skip_reason = policy.reason(key)
                blocked.append(row)
                continue
            if changed:
                write_values[key] = new_raw

        # ---- 只读参照行：耗材页 / 机器页在工程里存着的原值，列出来给用户看
        # 「这些参数我读了、也拿来约束工艺了，但一个字都不改」。
        for key, s in schema.PARAMS.items():
            if key in seen or key not in current:
                continue
            sc = policy.scope(key)
            if policy.allows(key):
                continue
            old_raw = current.get(key)
            old_val = schema.parse_value(s, old_raw)
            row = ParamRow(
                key=key, label=s.label, group=s.group, group_label=s.group_label,
                old_raw=old_raw, new_raw=str(old_raw), new_value=old_val,
                old_display=schema.display(s, old_val) if old_val is not None else "—",
                new_display=schema.display(s, old_val) if old_val is not None else "—",
                changed=False, will_write=False,
                reason=f"只读参照：{scope.SCOPE_LABEL.get(sc, sc)}参数，按要求原样保留",
                skip_reason=policy.reason(key), scope=sc,
            )
            rows.append(row)
            blocked.append(row)

        if skipped:
            notes.append(f"有 {len(skipped)} 个参数在你的工程文件里不存在，已跳过写入（多为机型/版本差异）。")
        if blocked:
            notes.append(
                f"有 {len(blocked)} 个参数属于「耗材页 / 机器页 / 元数据」，按你的要求只读不改，"
                "这些参数的上限值仍被用来约束工艺参数。")
        if self.unknown_keys:
            notes.append("规则库里出现了参数表未定义的键（已忽略）：" + "、".join(sorted(self.unknown_keys)))

        time_est = estimator.compare(old_for_estimate, values, flow_limit=self._flow_limit)

        result = OptResult(
            rows=rows, write_values=write_values, skipped=skipped, blocked=blocked,
            warnings=warnings, notes=notes, time=time_est, values=values,
            printer_key=printer_key, printer_label=pnode.get("label", printer_key),
            filament_key=filament_key, filament_label=fnode.get("label", filament_key),
            mode_key=mode_key, mode_label=mode_label, nozzle=float(nozzle),
            policy=policy, hardware=hw,
            derivations=list(self._derivations),
            flow_limit=self._flow_limit,
            project_nozzle=(hw.nozzle_diameter if hw else None),
            plate=self._plate_info,
            hotend=self._hotend.summary_line(),
            thermal_rows=list(self._thermal_rows),
            ironing_rows=list(self._ironing_rows),
            ironing=self._ironing_note,
            ironing_choice=(ironing_choice or "keep"),
            special_notes=list(self._special_notes),
            filament_mode=_fil_mode,
            filament_note=self._filament_note,
            room_note=self._room_note,
            thermal=self._thermal_text,
            seam=self._seam_text,
            support_ease=support_ease,
            sources={k: self._sources.get(k, "保持工程原值（无需改动）")
                     for k in write_values},
        )
        # 复原分槽全局（只在本次 optimize 内生效）
        try:
            schema.set_variant_slots(_prev_slots or 0)
        except Exception:
            pass
        return result

    def _enforce_time_cap(self, values, reasons, old_values, warnings, notes,
                          cap_pct: float, mode_for_budget: str = "balanced") -> None:
        """时长涨幅超过上限时，按「先砍最不影响质量的项」的顺序回调。

        回调优先级（从代价最小开始）：
            1. 填充密度回退（降到基准与目标之间的折中）
            2. 墙层数回退到 3
            3. 稀疏/内部实心填充速度提回
            4. 层高放大（只在质量模式下才会被压小）
        最多迭代 30 轮，每轮只动一项、动完立刻重算指数，避免一次砍过头。
        """
        base = estimator.compare(old_values, values, flow_limit=self._flow_limit)
        base_idx = max(estimator.index(old_values, flow_limit=self._flow_limit), 1e-9)
        if base.delta_pct <= cap_pct:
            return
        applied: list[str] = []

        # 层高能否用来换时间，按档位决定：
        #   强度档：只能抬到 0.24 mm（再高，层间结合面太少，与「强度优先」相悖）
        #   均衡/草稿：允许按 15% 一档往上抬
        #   质量族：本来不设预算，走不到这里
        # 墙圈数在强度档不动：加墙就是这个档的存在意义，
        # 为省时间把墙从 6 圈砍回 3 圈，等于把「强度优先」偷偷变成「均衡」。
        if mode_for_budget == "strength":
            lh_cap = min(float(schema.PARAMS["layer_height"].vmax), 0.24)

            def lh_step(v, o, s):
                return min(lh_cap, max(v, o) * 1.08)
            cut_walls = False
        elif mode_for_budget in ("balanced", "draft"):
            def lh_step(v, o, s):
                return min(s.vmax, v * 1.15)
            cut_walls = True
        else:
            lh_step = None
            cut_walls = True

        steps: list[tuple[str, Any]] = ([
            ("layer_height", lh_step),
        ] if lh_step is not None else []) + [
            ("sparse_infill_density", lambda v, o, s: max(o, v * 0.6)),
            ("top_shell_layers", lambda v, o, s: max(o, min(v, 4))),
            ("bottom_shell_layers", lambda v, o, s: max(o, min(v, 3))),
        ] + ([
            # 草稿档是「快」的档：墙圈数一律不许超过用户原来的圈数
            # （多一圈墙就等于多一倍墙路径，草稿档不能靠加墙变好）。
            ("wall_loops", (lambda v, o, s: min(v, o)) if mode_for_budget == "draft"
             else (lambda v, o, s: max(o, min(v, 3)))),
        ] if cut_walls else []) + [
            ("sparse_infill_speed", lambda v, o, s: max(v, o)),
            ("internal_solid_infill_speed", lambda v, o, s: max(v, o)),
            ("top_surface_speed", lambda v, o, s: max(v, o)),
            ("inner_wall_speed", lambda v, o, s: max(v, o)),
            ("outer_wall_speed", lambda v, o, s: max(o, min(v, o * 1.6))),
            # 加速度被几何/形状层压低过的话，最后再往回拉到原值。
            # 加速度对表面质量的影响远小于速度，但对时间的影响是同量级的，
            # 「只能靠降加速度保守」是最没必要的时间浪费。
            ("default_acceleration", lambda v, o, s: max(v, o)),
            ("travel_acceleration", lambda v, o, s: max(v, o)),
            ("outer_wall_acceleration", lambda v, o, s: max(v, o)),
        ]

        for _ in range(40):
            cur_idx = estimator.index(values, flow_limit=self._flow_limit)
            if (cur_idx - base_idx) / base_idx * 100.0 <= cap_pct:
                break
            progressed = False
            for key, fn in steps:
                if key not in values or key not in old_values or old_values[key] is None:
                    continue
                s = schema.PARAMS.get(key)
                if s is None or s.kind in (schema.ENUM, schema.BOOL):
                    continue
                old = float(old_values[key])
                cur_v = float(values[key])
                new_v = fn(cur_v, old, s)
                new_v = schema.clamp(s, new_v)
                if s.kind == schema.INT:
                    new_v = int(round(new_v))
                if _same(s, cur_v, new_v):
                    continue
                values[key] = new_v
                # 这一改动必须真的让时间变短才留下：
                # 在体积流量受限时，抬层高反而压低可挤出速度，可能越调越慢。
                if estimator.index(values, flow_limit=self._flow_limit) >= cur_idx - 1e-9:
                    values[key] = cur_v
                    continue
                reasons[key].append(
                    f"时长上限 {cap_pct:g}% 回调：{schema.display(s, cur_v)} → {schema.display(s, new_v)}")
                applied.append(key)
                progressed = True
                break
            if not progressed:
                break

        final = estimator.compare(old_values, values, flow_limit=self._flow_limit)
        met = final.delta_pct <= cap_pct
        if not met:
            warnings.append(
                f"时长上限 {cap_pct:g}% 无法达到：回退填充/墙数/速度/层高后仍是 "
                f"+{final.delta_pct:.0f}%。这台机器的这一组合（{cap_pct:g}% 内）物理上做不到——"
                "当前耗材的速度与体积流量上限已经把时间压到最低了。"
                "要么接受这个时长，要么加大层高/降填充密度/换高流量热端。")
        elif applied:
            uniq = "、".join(dict.fromkeys(schema.PARAMS[k].label for k in applied if k in schema.PARAMS))
            notes.append(
                f"已按「时长上限 {cap_pct:g}%」自动回退：{uniq}；"
                f"最终时长变化 {final.delta_pct:+.1f}%（原始方案为 {base.delta_pct:+.1f}%）。")
        self.last_timecap = {"cap": cap_pct, "before": base.delta_pct, "after": final.delta_pct,
                             "met": met, "steps": list(dict.fromkeys(applied))}

    # -------------------------------------------------- 内部工具

    def _gain_band(self) -> tuple[float, float]:
        """叠乘总闸的允许区间（来自规则库 options.mul_total_band）。"""
        band = self.options.get("mul_total_band") or [0.6, 1.8]
        try:
            lo, hi = float(band[0]), float(band[1])
        except (TypeError, ValueError, IndexError):
            lo, hi = 0.6, 1.8
        if lo <= 0 or hi <= lo:
            lo, hi = 0.6, 1.8
        return lo, hi

    def _scaled(self, key: str, mul: float, warnings: list[str]) -> float:
        """把倍率乘进去，但同一参数的**累计**倍率不许跑出总闸区间。

        为什么需要这道闸
        ----------------
        参数是分十层叠出来的：机型基线、耗材基线、模式档、交叉规则、
        逐件形状、几何事实……每一层都可以写一个「温和」的 ×0.9，
        但它们是相乘的。实测 PETG 的 travel_speed 被三层连乘成 ×0.207，
        1000 mm/s 的机器被写成 207 mm/s —— 单看每层都合理，合起来是灾难。

        总闸的做法：记录该键至今的累计倍率，若这次乘完会越界，
        就把这次的有效倍率打折到边界上，并在警告里写出原始值与压制值。
        """
        lo, hi = self._gain_band()
        prev = self._gain.get(key, 1.0)
        want = prev * mul
        capped = lo if want < lo else (hi if want > hi else want)
        eff = (capped / prev) if prev > 1e-12 else mul
        self._gain[key] = capped
        if abs(eff - mul) > 1e-6:
            warnings.append(
                f"叠乘总闸：{key} 累计倍率本来会到 ×{want:.2f}（超出允许的 "
                f"×{lo:g}~×{hi:g}），已压到 ×{capped:.2f}，"
                f"本次实际按 ×{eff:.2f} 生效。")
        return eff

    def _lookup(self, key: str) -> schema.ParamSpec | None:
        s = schema.PARAMS.get(key)
        if s is None:
            self.unknown_keys.add(key)
        return s

    def _apply_set(self, values, reasons, mapping: dict, why: str, warnings: list[str],
                   respect_project: bool = False, lock: bool = False) -> None:
        for key, raw in mapping.items():
            s = self._lookup(key)
            if s is None:
                continue
            if isinstance(raw, dict):
                # 基线层也允许写相对操作（{"mul": 0.9} / {"min": 150} / {"max": 300}）：
                # 这样「耗材差异」是相对用户当前值的一个温和修正，
                # 而不是用我们自造的绝对值把用户的设置覆盖掉。
                self._apply_ops(values, reasons, {key: raw}, why, warnings,
                                respect_locked=True, lock=lock)
                continue
            if s.preserve and key in self._user_values:
                # 用户实测标定值：不覆盖，但仍要把用户值放进基准，
                # 这样后续层（模式/交叉）能在这个基准上做加减，而不是找不到基线。
                values[key] = self._user_values[key]
                reasons[key].append("保留工程中的用户标定值")
                continue
            if respect_project and key in self._user_values:
                # 「工程里已有值 = 用户自己挑的起点」：
                # 通用基准层不覆盖它，只把它当基准，后续层在此之上继续调。
                values[key] = self._user_values[key]
                reasons[key].append(
                    f"以工程当前值 {schema.display(s, self._user_values[key])} 为基准（工程里已有该设置，不套用默认值）")
                continue
            v = _coerce(s, raw)
            if v is None:
                warnings.append(f"规则库 {why} 的 {key} 值无法解析（{raw!r}），已忽略。")
                continue
            prev = values.get(key)
            values[key] = v
            if lock:
                self._locked.add(key)
            if prev is None:
                reasons[key].append(why)
            elif not _same(s, prev, v):
                reasons[key].append(f"{why}：{schema.display(s, prev)} → {schema.display(s, v)}")

    def _apply_ops(self, values, reasons, ops: dict, why: str, warnings: list[str],
                   allow_preserve: bool = False,
                   respect_locked: bool = False,
                   lock: bool = False,
                   band: bool = True,
                   no_remul: set[str] | frozenset[str] = frozenset()) -> None:
        """band=False：这一层的倍率是**作者意图**（如模式档把层高 ×0.4），
        不参与叠乘总闸；只有「在别人结果上再打折」的层才需要闸。"""
        for key, op in ops.items():
            s = self._lookup(key)
            if s is None:
                continue
            if no_remul and key in no_remul and "mul" in op:
                # 上层（形状层）已经因为同一个理由调过这个键的量级，
                # 这里再乘一次就是重复扣分（用户感知为「降速严重」）。
                reasons[key].append(f"{why}：{why.split('（')[0]}已按形状意图调过，不再叠乘")
                continue
            if respect_locked and "set" in op and key in self._locked:
                # 上层（模式档 / 交叉规则）已经用绝对值定过这个键：
                # 逐件几何层不得把它翻掉——几何层是「在既有选择上微调」，
                # 不是替用户改选项。
                reasons[key].append(f"{why}：保留上层已确定的值，不覆盖")
                continue
            if key not in values:
                # 规则库里没有基准值，但工程里有用户设好的值：
                # 以用户值为基准继续微调（而不是跳过）。
                if key in self._user_values:
                    values[key] = self._user_values[key]
                    reasons[key].append(f"以工程当前值 {schema.display(s, values[key])} 为基准")
                else:
                    warnings.append(f"规则库 {why} 引用了无基准值的参数 {key}，已跳过。")
                    continue
            elif s.preserve and key in self._user_values and not allow_preserve:
                # 用户实测标定值：模式/交叉层不覆盖（形状层可覆盖，见 allow_preserve）
                values[key] = self._user_values[key]
                continue
            cur = values[key]
            if s.kind in KIND_STR or s.kind == schema.BOOL:
                if "set" in op:
                    nv = _coerce(s, op["set"])
                    if nv is not None and nv != cur:
                        values[key] = nv
                        self._sources[key] = why
                        if lock:
                            self._locked.add(key)
                        reasons[key].append(f"{why}：{cur} → {nv}")
                continue
            try:
                nv = float(cur)
                if "set" in op:
                    nv = float(op["set"])
                    if lock:
                        self._locked.add(key)   # 上层用绝对值定过，后续层不得翻掉
                elif "mul" in op:
                    nv = nv * (self._scaled(key, float(op["mul"]), warnings)
                               if band else float(op["mul"]))
                elif "add" in op:
                    nv = nv + float(op["add"])
                if "min" in op:
                    nv = max(nv, float(op["min"]))
                if "max" in op:
                    nv = min(nv, float(op["max"]))
            except (TypeError, ValueError):
                warnings.append(f"规则库 {why} 的 {key} 运算格式不正确，已忽略。")
                continue
            if s.kind == schema.INT:
                nv = int(round(nv))
            if not _same(s, cur, nv):
                values[key] = nv
                self._sources[key] = why
                reasons[key].append(f"{why}：{schema.display(s, cur)} → {schema.display(s, nv)}")

    def _match(self, when: dict, ctx: dict) -> bool:
        for k, v in when.items():
            if k == "filament" and ctx["filament"] != v:
                return False
            if k == "printer" and ctx["printer"] != v:
                return False
            if k == "printer_group" and ctx["printer_group"] != v:
                return False
            if k == "mode":
                # 支持写模式名，也支持写「族名」（quality 命中 quality/fine/ultrafine）
                want = str(v)
                members = modes_registry.group_members(want)
                if ctx["mode"] not in members:
                    return False
            if k == "nozzle_le" and not ctx["nozzle"] <= float(v) + 1e-9:
                return False
            if k == "nozzle_ge" and not ctx["nozzle"] >= float(v) - 1e-9:
                return False
            if k not in ("filament", "printer", "printer_group", "mode", "nozzle_le", "nozzle_ge"):
                return False
        return True

    def _clamp_schema(self, values, reasons, warnings) -> None:
        for key, s in schema.PARAMS.items():
            if key not in values or s.kind in KIND_STR + (schema.BOOL,):
                continue
            v = float(values[key])
            c = schema.clamp(s, v)
            if not _same(s, v, c):
                values[key] = c
                reasons[key].append(f"参数合法区间 {s.vmin:g}~{s.vmax:g}：{schema.display(s, v)} → {schema.display(s, c)}")

    def _clamp_nozzle(self, values, reasons, nozzle: float, pnode: dict, warnings) -> None:
        ratio_min = float(pnode.get("limits", {}).get("min_layer_height_ratio", 0.2))
        ratio_max = float(pnode.get("limits", {}).get("max_layer_height_ratio", 0.75))
        for key, s in schema.PARAMS.items():
            if key not in values or s.kind in KIND_STR + (schema.BOOL,):
                continue
            v = float(values[key])
            if "layer_height" in key:
                lo, hi = max(0.04, nozzle * ratio_min), nozzle * ratio_max
            elif "line_width" in key:
                lo, hi = nozzle * 0.5, nozzle * 1.6
            else:
                continue
            c = min(max(v, lo), hi)
            if abs(c - v) > 1e-9:
                values[key] = round(c, 4)
                reasons[key].append(
                    f"喷嘴 {nozzle:g} mm 约束 {lo:g}~{hi:g}：{schema.display(s, v)} → {schema.display(s, values[key])}"
                )

    def _clamp_machine(self, values, reasons, pnode: dict, fnode: dict, warnings,
                       hw: hardware.HardwareInfo | None = None) -> None:
        """钳制到机器真实硬件上限。

        优先用工程里读到的真机上限（machine_max_speed_x / machine_max_acceleration_x），
        读不到才回退到规则库的机型 limits。工程真值更准——同一台机器可能被人改过预设。
        """
        lim = pnode.get("limits", {})
        max_speed = float(lim.get("max_speed", 300))
        max_travel = float(lim.get("max_travel_speed", max(max_speed, 500)))
        max_accel = float(lim.get("max_accel", 10000))
        src = "机型规则库"
        if hw is not None:
            # 真机上限与规则库上限「取小」，不是覆盖：
            # 规则库代表这台机型系列的上限，工程值代表这台机器实际的设定，
            # 两个都要满足。同时 acc_x（机器最大加速度）才是加速度的上限，
            # acc_travel（空走加速度）只约束 travel_acceleration。
            if hw.max_speed:
                if float(hw.max_speed) < max_speed:
                    max_speed = float(hw.max_speed)
                    src = "工程真机上限"
                else:
                    src = "机型规则库（真机记录更高，未采纳）"
                    warnings.append(
                        f"工程里记录的最大速度 {float(hw.max_speed):g} mm/s 高于"
                        f"「{pnode.get('label', '')}」的机型上限 {float(lim.get('max_speed', 0)):g} mm/s，"
                        "已按机型上限计算——请确认机型识别是否正确。")
            if hw.max_accel:
                max_accel = min(max_accel, float(hw.max_accel))
                src = "工程真机上限"
            if hw.max_travel_accel:
                max_travel = min(max_travel, float(hw.max_travel_accel))
        accel_travel_cap = float(lim.get("max_travel_accel", max_accel))
        if hw is not None and hw.max_travel_accel:
            accel_travel_cap = min(accel_travel_cap, float(hw.max_travel_accel))
        # 这几个键的数值语义不是「mm/s」，而是「相对默认值的百分比」：
        #   small_perimeter_speed 50%  = 小周长按默认速度的 50%
        #   vertical_shell_speed  80%  = 竖直薄壁按默认速度的 80%
        #   inner_wall_acceleration 0    = 跟随 default_acceleration
        #   sparse_infill_acceleration 100% = 跟随 default_acceleration
        # 拿它们去和机器的绝对上限比大小没有意义，钳制只会把语义改坏。
        pct_semantic = {
            "small_perimeter_speed", "vertical_shell_speed",
            "inner_wall_acceleration", "sparse_infill_acceleration",
            "min_resonance_avoidance_speed", "max_resonance_avoidance_speed",
        }
        for key, s in schema.PARAMS.items():
            if key not in values or s.kind in KIND_STR + (schema.BOOL,):
                continue
            if key in pct_semantic:
                continue
            v = float(values[key])
            cap: float | None = None
            if key.endswith("_speed"):
                if key == "travel_speed":
                    cap = max_travel
                else:
                    cap = max_speed
            elif key.endswith("_acceleration"):
                # 空走加速度用空走上限，其余加速度用机器加速度上限
                cap = accel_travel_cap if key == "travel_acceleration" else max_accel
            if cap is None:
                continue
            if v > cap + 1e-9:
                values[key] = round(cap)
                reasons[key].append(f"{src} {cap:g}：{schema.display(s, v)} → {schema.display(s, values[key])}")
                warnings.append(
                    f"{s.label} 原始/计算值 {v:g} 超过 {src} {cap:g}，已钳制到 {cap:g}。"
                )
        # 层高还要落在机器允许的区间内（min_layer_height / max_layer_height）
        if hw is not None and hw.min_layer_height and hw.max_layer_height:
            key = "layer_height"
            if key in values:
                v = float(values[key])
                lo, hi = float(hw.min_layer_height), float(hw.max_layer_height)
                c = min(max(v, lo), hi)
                if abs(c - v) > 1e-9:
                    values[key] = round(c, 4)
                    s = schema.PARAMS[key]
                    reasons[key].append(
                        f"工程真机层高区间 {lo:g}~{hi:g}：{schema.display(s, v)} → {schema.display(s, c)}")
                    warnings.append(f"层高 {v:g} mm 超出这台机器允许的 {lo:g}~{hi:g} mm，已调整为 {c:g} mm。")

    def _clamp_flow(self, values, reasons, pnode: dict, fnode: dict, warnings,
                    overlay_max: float | None = None,
                    project_max: float | None = None,
                    printer_key: str = "",
                    nozzle: float | None = None,
                    project_nozzle: float | None = None,
                    filament_key: str = "") -> None:
        """钳制到体积流量上限。

        取值来源按「越具体越优先」排：
            1. 官方「耗材 × 机型」标定（同一个 PETG，X1C 是 13 mm³/s，A1 只有 9）
            2. Bambu Studio 自定义耗材预设里的上限
            3. 工程里你标定的 filament_max_volumetric_speed
        这些都是「上限」，最终取**最小值**——宁可慢一点也不超出热端能力。

        注意：耗材通用基线（filament/@base）只在没有具体机型标定时才参与，
        否则 PETG 的通用值 8 会把 X1C 的官方 13 覆盖掉（那是「更严格的通用兜底」，
        不是这台机器的真实能力）。
        """
        lim = pnode.get("limits", {})
        flim = fnode.get("limits", {}) or {}
        flow_p = float(lim.get("max_volumetric_speed", 20))
        flow_f = float(flim.get("max_volumetric_speed", flow_p))

        by_printer = flim.get("flow_by_printer") or {}
        per_machine = (by_printer.get(pnode.get("group"))
                       or by_printer.get(printer_key))
        srcs: list[str] = []
        official = None
        if per_machine:
            official = float(per_machine)
            srcs.append(f"官方 {fnode.get('label', '')}×{pnode.get('label', '')} 标定 {official:g}")
        else:
            official = min(flow_p, flow_f)
            srcs.append(f"规则库机型/耗材基线 {official:g}")
        # ---- 喷嘴同步：工程里的流量标定是按工程那个喷嘴标的
        # 用户在下拉里换了喷嘴（例如 0.4 → 0.2），流量上限必须一起换，
        # 否则 0.2 喷嘴会被按 0.4 的 13 mm³/s 去算速度（物理跑不到，堵料）。
        group = pnode.get("group") or printer_key
        fkey = str(fnode.get("key") or filament_key or "")
        noz_official, noz_src = nozzle_flow.limit(
            self.rules, group=group, filament_key=fkey, nozzle=nozzle)
        if noz_official is not None:
            srcs.append(noz_src or f"官方 {nozzle:g} 喷嘴标定 {noz_official:g}")
            official = min(official, noz_official) if official else noz_official
        proj_noz = nozzle_flow.snap_nozzle(project_nozzle)
        pick_noz = nozzle_flow.snap_nozzle(nozzle)
        if (project_max and proj_noz and pick_noz and proj_noz != pick_noz):
            r, rsrc = nozzle_flow.ratio(
                self.rules, group=group, filament_key=fkey,
                from_nozzle=proj_noz, to_nozzle=pick_noz)
            if r is not None:
                scaled = float(project_max) * r
                if noz_official:
                    # 折算值与新喷嘴的官方上限取小 —— 工程标定只对原喷嘴成立
                    final = min(scaled, float(noz_official))
                else:
                    final = scaled
                warnings.append(
                    f"喷嘴同步：工程里的流量 {float(project_max):g} mm³/s 是按 "
                    f"{proj_noz:g} 喷嘴标的（{rsrc}），折算到 {pick_noz:g} 喷嘴为 "
                    f"{scaled:.1f} mm³/s，与官方 {pick_noz:g} 喷嘴上限 "
                    f"{noz_official or 0:g} 取小后按 {final:.1f} mm³/s 计算。")
                project_max = final
        if official and self._hotend_mul > 1.0:
            official = float(official) * self._hotend_mul
            srcs.append(
                f"热端流量类型「{self._hotend.label}」×{self._hotend_mul:g}")
        # 工程里 filament_max_volumetric_speed 是「在工程那根热端上标出来的」：
        # 用户把下拉改成高流量 = 换了热端，标定值要按两根热端的比例折算。
        if project_max:
            base_mul, _ = hotend.factor(self.rules, self._hotend_detected.key)
            if abs(self._hotend_mul - base_mul) > 1e-9:
                ratio = self._hotend_mul / max(base_mul, 1e-9)
                scaled = float(project_max) * ratio
                warnings.append(
                    f"热端流量同步：工程里的 {float(project_max):g} mm³/s 是在"
                    f"「{self._hotend_detected.label}」热端上标的，按「{self._hotend.label}」"
                    f"折算 ×{ratio:g} 后为 {scaled:.1f} mm³/s。"
                    f"（换热端后请用 Bambu Studio 重新做一次流量标定，这个折算只是估计。）")
                project_max = scaled
        max_flow = official
        if overlay_max:
            # 自定义耗材预设：用户在 Bambu Studio 里自己标的值，比通用基线具体
            max_flow = min(max_flow, float(overlay_max))
            srcs.append(f"自定义耗材预设 {float(overlay_max):g}")
        if project_max:
            # 工程里 filament_max_volumetric_speed 是「这台机器 + 这卷料」实测标定的
            # 热端流量上限 —— 它比官方通用标定更贴近当前这台机器，优先采用。
            # （P2S 官方 PETG 标定 13，但换了高流量热端/好料的用户实测能到 18。）
            # 只有当工程里的值明显高于官方标定时才提示复核，避免把用户的
            # 实测标定压回通用值、把速度白白限制住。
            pm = float(project_max)
            if official > 0 and pm > official * 1.3:
                warnings.append(
                    f"工程里你标定的热端流量 {pm:g} mm³/s 明显高于官方 "
                    f"{fnode.get('label', '')}×{pnode.get('label', '')} 标定 {official:g} mm³/s，"
                    "已按你的标定值计算——请确认这条料在这台机器上确实能跑这个流量。")
            max_flow = pm
            srcs.append(f"工程里你标定的热端流量 {pm:g}")
        src = "、".join(srcs)
        self._flow_limit = float(max_flow)
        lh = float(values.get("layer_height", 0.2) or 0.2)
        flow_keys = {
            "outer_wall_speed": "outer_wall_line_width",
            "inner_wall_speed": "inner_wall_line_width",
            "sparse_infill_speed": "sparse_infill_line_width",
            "internal_solid_infill_speed": "internal_solid_infill_line_width",
            "top_surface_speed": "top_surface_line_width",
            "gap_infill_speed": "line_width",
            "support_speed": "support_line_width",
            "support_interface_speed": "support_line_width",
        }
        for speed_key, width_key in flow_keys.items():
            if speed_key not in values:
                continue
            lw = float(values.get(width_key, values.get("line_width", 0.42)) or 0.42)
            cap = max_flow / max(lh * lw, 1e-6)
            v = float(values[speed_key])
            if v > cap + 1e-6:
                values[speed_key] = round(cap, 1)
                s = schema.PARAMS[speed_key]
                reasons[speed_key].append(
                    f"体积流量上限 {max_flow:g} mm³/s（层高 {lh:g} × 线宽 {lw:g}，{src}）："
                    f"{schema.display(s, v)} → {schema.display(s, values[speed_key])}"
                )
                warnings.append(
                    f"{s.label} 受体积流量上限约束（{max_flow:g} mm³/s，{src}），"
                    f"已从 {v:g} 降到 {values[speed_key]:g} mm/s。想更快需要换高流量热端。"
                )

        # 支撑接触面必须比支撑本体慢（接触面决定好不好撕）。
        # 流量钳制会把两者都压到同一个上限，这里把比例再拉回来。
        try:
            body = float(values.get("support_speed") or 0)
            iface = float(values.get("support_interface_speed") or 0)
            if body > 0 and iface > body * 0.72:
                values["support_interface_speed"] = round(max(10.0, body * 0.6), 1)
                reasons.setdefault("support_interface_speed", []).append(
                    f"支撑接触面要慢于本体（本体 {body:g} → 接触面 ×0.6），"
                    f"已调整到 {values['support_interface_speed']:g} mm/s。")
        except (TypeError, ValueError):
            pass


def build_engine(path: str | os.PathLike | None = None) -> RulesEngine:
    return RulesEngine(load_rules(path))
