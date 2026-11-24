"""打印板同步层：板型（curr_bed_type）+ 板面尺寸。

用户的要求（m01443 / m04966）：「板子也要同步」「打印板也要同步」。

工程里其实带着三组和板有关的信息，之前只读了第三组：

    板型（耗材页 / 打印页，只读）
        curr_bed_type                     "Supertack Plate"
        cool_plate_temp / eng_plate_temp / hot_plate_temp
        textured_plate_temp / supertack_plate_temp       各板的首层与其它层温度

    板面（机器页，只读）
        printable_area                    ["0x0","256x0","256x256","0x256"]
        printable_height                  "256"
        wrapping_exclude_area             ["153x256",...]  前方禁打区

    机型官方板面（规则库 printers[*].bed）
        A1 mini 180×180、X1/P1/P2/A1 256×256、H2D 350×320、H2S 340×320

本模块做四件事：

    1. 认出板型，并把它对应到官方温度键；
    2. **兼容性判据直接用官方数据**：某条料在某板上不可用时，官方预设里那块板
       的温度就是 0（本工程实测 PETG 的 cool_plate_temp = 0）。看到 0 就报硬警告。
    3. 板面尺寸与机型官方尺寸对不上时报警（机型识别错、或工程还是别的机器的）；
    4. 按板型给几条工艺微调（写在 rules/BambuRules.json 的 plates 段，可自己改）。

板型和板面都在机器页 / 耗材页，按约定只读不写 —— 这里只「读 + 判 + 调工艺」。
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 板型名 → 官方温度键。Bambu 的「光面 PEI」复用纹理板温度键。
PLATE_TEMP_KEYS = {
    "cool plate": "cool_plate_temp",
    "engineering plate": "eng_plate_temp",
    "high temp plate": "hot_plate_temp",
    "high temperature plate": "hot_plate_temp",
    "textured pei plate": "textured_plate_temp",
    "smooth pei plate": "textured_plate_temp",
    "supertack plate": "supertack_plate_temp",
    "supertack": "supertack_plate_temp",
}

DEFAULT_PLATE = "Supertack Plate"


def _as_list(val) -> list:
    """工程里的数组可能是 list，也可能是 JSON 字符串或逗号分隔串。"""
    import json

    if val is None:
        return []
    if isinstance(val, list):
        return list(val)
    txt = str(val).strip()
    if not txt:
        return []
    if txt.startswith("["):
        try:
            v = json.loads(txt)
            if isinstance(v, list):
                return v
        except (ValueError, TypeError):
            pass
    return [txt]


def _num(val, idx: int = 0) -> float | None:
    """工程里的值可能是 '60' 也可能是 ['60','60']。"""
    import json
    import re

    if val is None:
        return None
    if isinstance(val, list):
        seq = val
    else:
        txt = str(val).strip()
        if txt.startswith("["):
            try:
                seq = json.loads(txt)
            except (ValueError, TypeError):
                seq = [txt]
        else:
            seq = [txt]
    if not seq or idx >= len(seq):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(seq[idx]))
    return float(m.group(1)) if m else None


@dataclass
class PlateInfo:
    """这块板是什么、能不能跑这条料、板面多大。"""

    name: str = ""                     # 工程里的 curr_bed_type 原值
    key: str = ""                      # 规则库 plates.items 的键
    label: str = ""                    # 中文名
    temp_key: str = ""                 # 对应的官方温度键
    temp: float | None = None          # 其它层温度
    temp_initial: float | None = None  # 首层温度
    supported: bool = True             # 官方是否支持这条料（温度 0 = 不支持）
    note: str = ""

    # 板面（机器页）
    bed_w: float = 0.0
    bed_d: float = 0.0
    bed_h: float = 0.0
    exclude_blocks: int = 0

    # 机型官方板面（规则库）
    expect_w: float = 0.0
    expect_d: float = 0.0
    expect_h: float = 0.0

    @property
    def known(self) -> bool:
        return bool(self.name)

    @property
    def area(self) -> float:
        return self.bed_w * self.bed_d

    def summary_line(self) -> str:
        """给 UI「真机同步」用的一行。

        只写板型与温度 —— 板面尺寸/禁打区由 hardware 的「板面」那一行负责，
        两边都写会在同一行里重复两遍。
        """
        if not self.known:
            return "打印板：工程里没读到 curr_bed_type（按出厂默认 Supertack 超粘板对待）"
        parts = [f"打印板：{self.label or self.name}"]
        if self.temp is not None and self.supported:
            t0 = f"{self.temp_initial:g}℃" if self.temp_initial else "未读到"
            parts.append(f"首层 {t0} / 其它层 {self.temp:g}℃")
        elif not self.supported:
            parts.append("⚠ 耗材页这块板的温度是 0，表示这条料在它上面不可用")
        return " ｜ ".join(parts)


def resolve_name(name: str, rules: dict | None) -> tuple[str, dict]:
    """把工程里的板型名对上规则库里的板型节点，返回 (键, 节点)。"""
    items = ((rules or {}).get("plates") or {}).get("items") or {}
    low = (name or "").strip().lower()
    if not low:
        return DEFAULT_PLATE, items.get(DEFAULT_PLATE, {}) or {}
    # 先精确比键与别名
    for key, node in items.items():
        if str(key).strip().lower() == low:
            return key, node
        for alias in (node.get("aliases") or []):
            if str(alias).strip().lower() == low:
                return key, node
    # 再模糊：板型名互含
    for key, node in items.items():
        k = str(key).strip().lower()
        if k and (k in low or low in k):
            return key, node
    for alias_key, temp_key in PLATE_TEMP_KEYS.items():
        if alias_key in low:
            for key, node in items.items():
                if (node or {}).get("temp_key") == temp_key:
                    return key, node
    return DEFAULT_PLATE, items.get(DEFAULT_PLATE, {}) or {}


def read(project, rules: dict | None = None) -> PlateInfo:
    """从工程（或直接给 settings 字典）读出板型与板面。"""
    s = getattr(project, "settings", None)
    if s is None:
        s = project or {}
    info = PlateInfo(name=str(s.get("curr_bed_type") or "").strip())

    key, node = resolve_name(info.name, rules)
    info.key = key
    info.label = str(node.get("label") or key)
    info.temp_key = str(node.get("temp_key") or PLATE_TEMP_KEYS.get(key.lower(), ""))
    info.note = str(node.get("note") or "")

    if info.temp_key:
        info.temp = _num(s.get(info.temp_key))
        info.temp_initial = _num(s.get(info.temp_key + "_initial_layer"))
        # 官方约定：不支持该板时温度写 0
        info.supported = bool(info.temp and info.temp > 0)

    # ---- 板面：printable_area 是 4 个角点，形如 ["0x0","256x0","256x256","0x256"]
    xs: list[float] = []
    ys: list[float] = []
    for pt in _as_list(s.get("printable_area")):
        txt = str(pt)
        if "x" in txt:
            a, _, b = txt.partition("x")
            try:
                xs.append(float(a))
                ys.append(float(b))
            except ValueError:
                continue
    if xs and ys:
        info.bed_w = max(xs) - min(xs)
        info.bed_d = max(ys) - min(ys)
    info.bed_h = _num(s.get("printable_height")) or 0.0
    info.exclude_blocks = len(_as_list(s.get("wrapping_exclude_area"))) // 4

    return info


def expected_bed(rules: dict | None, printer_key: str) -> list[float]:
    node = ((rules or {}).get("printers") or {}).get(printer_key) or {}
    bed = node.get("bed") or []
    return [float(x) for x in bed] if bed else []


def check(plate: PlateInfo, *, rules: dict | None, printer_key: str,
          filament_key: str, profile=None) -> tuple[list[str], list[str], dict]:
    """返回 (警告, 说明, 工艺 op)。"""
    warns: list[str] = []
    notes: list[str] = []
    ops: dict = {}

    exp = expected_bed(rules, printer_key)
    if exp:
        plate.expect_w, plate.expect_d = exp[0], exp[1]
        plate.expect_h = exp[2] if len(exp) > 2 else 0.0

    # ---- 1. 板型兼容性（官方温度 0 = 不支持）
    if plate.known and plate.temp_key:
        if plate.temp is not None and plate.temp <= 0:
            warns.append(
                f"打印板不兼容：工程里选的是「{plate.label}」，而耗材页 {plate.temp_key} 是 0 —— "
                f"官方预设用 0 表示 {filament_key} 不能在这个板上打印。"
                f"请先到 Bambu Studio 的「打印板类型」里换成该耗材支持的板"
                f"（或把耗材换成该板支持的材料），否则首层会粘不住或撕板。")
        elif plate.temp is not None:
            notes.append(
                f"打印板已同步：{plate.label}（{plate.temp_key} = {plate.temp:g}℃"
                + (f"，首层 {plate.temp_initial:g}℃" if plate.temp_initial else "")
                + f"）。板型与温度属耗材页，只读不改。")

    # ---- 2. 板面尺寸对不上机型官方值
    if plate.bed_w and plate.bed_d and exp:
        dw, dd = abs(plate.bed_w - exp[0]), abs(plate.bed_d - exp[1])
        if dw > 1.0 or dd > 1.0:
            warns.append(
                f"板面尺寸与机型不符：工程机器页的可打印区域是 "
                f"{plate.bed_w:g} × {plate.bed_d:g} mm，而「{printer_key}」官方板面是 "
                f"{exp[0]:g} × {exp[1]:g} mm。要么机型识别错了，要么这个工程还是别的机器导出的 —— "
                f"请确认机型下拉；板面本身只读不改，工艺参数不受影响，但模型是否放得下按工程板面判断。")
        # 尺寸一致时不再重复 hardware 那条「板面已同步」

    # ---- 3. 模型放得下吗
    # 用「你选的那台机器」的官方板面判断（选错机型时这里也会暴露出来）；
    # 规则库里没有该机型板面时才退回工程 printable_area。
    fit_w = plate.expect_w or plate.bed_w
    fit_d = plate.expect_d or plate.bed_d
    if profile is not None and fit_w and fit_d:
        objs = getattr(profile, "objects", None) or []
        for i, obj in enumerate(objs, 1):
            sx, sy = float(getattr(obj, "size_x", 0)), float(getattr(obj, "size_y", 0))
            if sx <= 0 or sy <= 0:
                continue
            fits_a = sx <= fit_w + 1e-6 and sy <= fit_d + 1e-6
            fits_b = sx <= fit_d + 1e-6 and sy <= fit_w + 1e-6   # 旋转 90° 能不能放下
            if not (fits_a or fits_b):
                warns.append(
                    f"模型放不下：第 {i} 件 {sx:g} × {sy:g} mm，超过板面 "
                    f"{fit_w:g} × {fit_d:g} mm。请先在 Bambu Studio 里旋转/缩放，"
                    f"本程序不改模型几何。")
    # 禁打区已由 hardware 的「板面」行说明，这里不重复

    # ---- 4. 板型相关的工艺微调（规则库 plates.items.<key>.process）
    # 只放「非 preserve」的键：preserve 的键（如 brim_width）是用户自己的值，
    # 引擎会静默跳过，写了也不生效，所以这类建议走文字 advice。
    items = ((rules or {}).get("plates") or {}).get("items") or {}
    node = items.get(plate.key) or {}
    for key, op in (node.get("process") or {}).items():
        ops[key] = dict(op)
    advice = str(node.get("advice") or "")
    if advice:
        notes.append(f"打印板建议（{plate.label}）：{advice}")

    return warns, notes, ops
