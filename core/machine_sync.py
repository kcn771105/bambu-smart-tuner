"""机型同步层：把「你在界面里选的那台机器」写进 3mf 的机器页。

为什么需要这一层
----------------
用户反馈：「选择了机型后生成的 3mf 不对应」——点「保存为 3mf」之后，
文件里 `printer_model` / `printer_settings_id` / `printable_area` /
`machine_max_speed_*` 还是原工程那台机器的值，Bambu Studio 打开后
按机器页认机器，于是仍然显示成旧机型，工艺参数也就跟着旧机器的上限走。

本层的口径
----------
1. 只有「界面选的机型 ≠ 工程里识别出的机型」时才动手（`printer_key != detected_key`）。
   没换机型就一个字都不改，避免把本来正常的工程改坏。
2. 写的是**机器页**的键，全部从规则库 `printers[<key>]` 的官方机读值来：
       printer_model             ← printers[key].label
       printer_settings_id       ← "<label> <喷嘴> nozzle"
       printable_area            ← printers[key].bed 的四个角点
       printable_height          ← printers[key].bed[2]
       machine_max_speed_x/y     ← limits.max_speed
       machine_max_acceleration_x/y ← limits.max_accel
       machine_max_acceleration_travel ← limits.max_travel_accel
       machine_max_jerk_x/y      ← limits.max_jerk
       nozzle_volume             ← limits.nozzle_volume
3. 工程里没有的键一律不新增（threemf.apply(skip_missing=True) 兜底），
   因为不同版本的 Studio 对未知键容忍度不一样。
4. 写机器页等于「换机器」，所以必须声明进 different_settings_to_system 的第 3 槽
   （机器槽），否则 Studio 会按旧的机型预设把机器页覆盖回去。

本模块不参与工艺参数的钳制：钳制用的是工程里的真机上限（core/hardware.py），
这里只负责「保存出来的文件跟界面上选的是同一台机器」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

__all__ = ["MachinePlan", "SYNC_KEYS", "plan"]

#: 本模块会写的机器页键。这些都是 Bambu Studio 工程文件的标准键，
#: 老工程里缺这几行时也允许补写（见 threemf.apply(allow_missing=...)）。
SYNC_KEYS = frozenset({
    "printer_model", "printer_settings_id", "printer_variant",
    "printable_area", "printable_height", "wrapping_exclude_area",
    "nozzle_diameter", "nozzle_volume",
    "machine_max_speed_x", "machine_max_speed_y",
    "machine_max_acceleration_x", "machine_max_acceleration_y",
    "machine_max_acceleration_travel", "machine_max_jerk_x", "machine_max_jerk_y",
    # 换机型时**必须一起换**的预设名：Bambu Studio 切片前会校验
    # 「工艺/耗材预设的 compatible_printers 里有没有这台机器」，
    # 只改机器页不改预设名 → 直接报 `process not compatible with printer`，一张图都不出。
    "print_settings_id", "default_print_profile",
    "filament_settings_id", "default_filament_profile",
    # 工程里抄了一份「这个工艺预设能配哪些机器」，换机型必须一起改
    "print_compatible_printers",
})


@dataclass
class MachinePlan:
    """一次机型同步的结果。"""
    ops: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changed: bool = False


def _as_list(v: Any) -> list[str]:
    """`["a","b"]` / `'["a","b"]'` / `"a"` 一律摊成 list[str]。"""
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    if isinstance(v, str) and v.strip().startswith("["):
        try:
            data = json.loads(v)
            if isinstance(data, list):
                return [str(x) for x in data]
        except (TypeError, ValueError):
            pass
    if v is None or str(v).strip() == "":
        return []
    return [str(v)]


def _first_str(v: Any) -> str:
    items = _as_list(v)
    return items[0] if items else ""


def _slots(v: Any) -> int:
    return max(1, len(_as_list(v)))


def _area_points(bed: list[float]) -> list[str]:
    """板面四角点，写成 Bambu 的 ["0x0","256x0","256x256","0x256"]。"""
    if len(bed) < 2:
        return []
    w = float(bed[0])
    d = float(bed[1])

    def _n(v: float) -> str:
        return str(int(v)) if abs(v - int(v)) < 1e-9 else f"{v:g}"

    return [f"0x0", f"{_n(w)}x0", f"{_n(w)}x{_n(d)}", f"0x{_n(d)}"]


def _num(v: Any) -> float | None:
    """取值并转数字。工程里的键常是 ["0.4"] 这种按热端分槽的 JSON 文本，先拆。"""
    try:
        if isinstance(v, str) and v.strip().startswith("["):
            try:
                v = json.loads(v)
            except (TypeError, ValueError):
                v = [t.strip().strip('"') for t in v.strip().strip("[]").split(",")]
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if v is None:
            return None
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def plan(rules: dict, printer_key: str, *, nozzle: float = 0.4,
         detected_key: str = "", current: dict | None = None,
         enabled: bool = True) -> MachinePlan:
    """按界面选择的机型给出机器页写入项。

    参数
    ----
    rules         : 规则库
    printer_key   : 界面里选的机型键（printers 的键）
    nozzle        : 喷嘴直径（写进 printer_settings_id）
    detected_key  : 工程里原本识别出的机型键；与 printer_key 相同则什么都不做
    current       : 工程当前 settings（用来判断哪些键值得写、哪些已经一致）
    enabled       : 用户关掉「同步机型」时为 False，直接返回空计划
    """
    out = MachinePlan()
    if not enabled:
        return out
    if not printer_key:
        return out
    node = (rules.get("printers") or {}).get(printer_key)
    if not node:
        out.warnings.append(f"机型同步：规则库里没有「{printer_key}」，机器页保持原样。")
        return out

    label = str(node.get("label") or printer_key)

    if detected_key and printer_key == detected_key:
        # 同一台机器也**不能直接不管**：喷嘴换了却没同步机器页时，
        # Studio 会按旧喷嘴的机器预设切片（线宽/层高上限/体积流量全按旧喷嘴算），
        # 表现就是用户说的「选了机型后生成的 3mf 不对应」。
        cur = current or {}
        if not current:
            # 没有工程可对比，就不猜（调用方一般都有工程，这里只是防御）
            out.notes.append(f"机型同步：机型与识别结果相同（{printer_key}），机器页保持原样。")
            return out
        cur_noz = _num(cur.get("nozzle_diameter"))
        cur_var = str(cur.get("printer_variant") or "").strip()
        want = f"{float(nozzle):g}"
        same_noz = cur_noz is not None and abs(cur_noz - float(nozzle)) < 1e-6
        same_var = (not cur_var) or cur_var == want
        if same_noz and same_var:
            out.notes.append(
                f"机型同步：界面选的机型与工程里识别到的相同（{printer_key}），"
                f"喷嘴 {want} mm 也一致，机器页保持原样不动。")
            return out
        # 只补喷嘴相关的键，别的机器参数一个都不碰
        out.ops["printer_settings_id"] = f"{label} {want} nozzle"
        # 换喷嘴也等于换机器预设名（`Bambu Lab P2S 0.4 nozzle` → `… 0.6 nozzle`），
        # 工程里抄的工艺兼容列表不改，Studio 会判「工艺预设不认这台机器」拒绝切片。
        out.ops["print_compatible_printers"] = json.dumps(
            [f"{label} {want} nozzle"], ensure_ascii=False)
        # 换喷嘴后「0.20mm Standard」这个工艺预设在新喷嘴上可能不存在，
        # 挑一个这台机器 + 这个喷嘴认的、层高最接近的（0.6 喷嘴 → 0.30mm Standard）。
        try:
            from . import preset_names
            proc_new = preset_names.remap(
                cur.get("print_settings_id"), f"{label} {want} nozzle", "process")
        except Exception:                          # noqa: BLE001 - 没装 Studio 就不换
            proc_new = None
        if proc_new and proc_new != str(cur.get("print_settings_id") or "").strip():
            out.ops["print_settings_id"] = proc_new
            if cur.get("default_print_profile"):
                out.ops["default_print_profile"] = proc_new
            out.notes.append(
                f"机型同步：工艺预设换成「{proc_new}」（{want} mm 喷嘴上没有原预设，"
                "选了同机器、层高最接近的那个）。")
        if not same_noz:
            cnt = 1
            raw = cur.get("nozzle_diameter")
            if isinstance(raw, list):
                cnt = max(1, len(raw))
            elif isinstance(raw, str):
                try:
                    _d = json.loads(raw)
                    cnt = max(1, len(_d)) if isinstance(_d, list) else 1
                except Exception:
                    cnt = 1
            out.ops["nozzle_diameter"] = json.dumps([float(nozzle)] * cnt)
        if not same_var:
            out.ops["printer_variant"] = want
        out.ops = {k: v for k, v in out.ops.items()
                   if str((current or {}).get(k, "")).strip() != str(v).strip()}
        out.changed = bool(out.ops)
        out.notes.append(
            f"机型同步：机型没换，但喷嘴从工程里的 {cur_noz or '?'} mm 改成了 {want} mm，"
            "机器页的 nozzle_diameter / printer_settings_id / printer_variant 已按新喷嘴改好"
            "（不改这几行，Studio 会继续按旧喷嘴切片）。")
        return out
    bed = [float(x) for x in (node.get("bed") or [])]
    lim = node.get("limits") or {}
    cur = current or {}

    # ---- 机型标识
    out.ops["printer_model"] = label
    noz_txt = f"{float(nozzle):g}"
    out.ops["printer_settings_id"] = f"{label} {noz_txt} nozzle"

    # ---- 板面
    pts = _area_points(bed)
    if pts:
        out.ops["printable_area"] = json.dumps(pts, ensure_ascii=False)
    if len(bed) >= 3:
        out.ops["printable_height"] = str(int(bed[2])) if abs(bed[2] - int(bed[2])) < 1e-9 else f"{bed[2]:g}"

    # ---- 硬件上限
    sp = _num(lim.get("max_speed"))
    ac = _num(lim.get("max_accel"))
    tv = _num(lim.get("max_travel_accel"))
    jk = _num(lim.get("max_jerk"))
    vol = _num(lim.get("nozzle_volume"))
    if sp:
        for axis in ("x", "y"):
            out.ops[f"machine_max_speed_{axis}"] = str(int(sp)) if sp == int(sp) else f"{sp:g}"
    if ac:
        for axis in ("x", "y"):
            out.ops[f"machine_max_acceleration_{axis}"] = str(int(ac)) if ac == int(ac) else f"{ac:g}"
    if tv:
        out.ops["machine_max_acceleration_travel"] = str(int(tv)) if tv == int(tv) else f"{tv:g}"
    if jk:
        for axis in ("x", "y"):
            out.ops[f"machine_max_jerk_{axis}"] = str(int(jk)) if jk == int(jk) else f"{jk:g}"
    if vol:
        out.ops["nozzle_volume"] = str(int(vol)) if vol == int(vol) else f"{vol:g}"

    # ---- 工艺 / 耗材预设名也要一起换
    # Studio 切片前先校验「预设的 compatible_printers 里有没有这台机器」，
    # 不匹配就报 `process not compatible with printer`，一张图都不出。
    psid_new = out.ops.get("printer_settings_id") or f"{label} {noz_txt} nozzle"
    try:
        from . import preset_names
        proc_new = preset_names.remap(cur.get("print_settings_id"), psid_new, "process")
        fil_new = preset_names.remap(_first_str(cur.get("filament_settings_id")),
                                     psid_new, "filament", strict=True)
        compat = preset_names.compat_of(proc_new) if proc_new else []
    except Exception:                              # noqa: BLE001 - 没装 Studio 就不换
        proc_new = fil_new = None
        compat = []
    if proc_new:
        out.ops["print_settings_id"] = proc_new
        if cur.get("default_print_profile"):
            out.ops["default_print_profile"] = proc_new
        # 工程里还把「这个工艺预设能配哪些机器」抄了一份：`print_compatible_printers`。
        # 这一行不改，Studio 仍然按旧的机型列表判定不兼容，报
        # `process not compatible with printer` 直接拒绝切片（实测就是它）。
        # 只能写成「当前这台机器」这一项：写成整个兼容列表时 Studio 反而拒（实测）。
        out.ops["print_compatible_printers"] = json.dumps([psid_new], ensure_ascii=False)
        out.notes.append(
            f"机型同步：工艺预设从「{cur.get('print_settings_id')}」换成「{proc_new}」"
            "（Studio 切片前会校验预设认不认这台机器，不换就直接拒绝切片）。")
    if fil_new:
        cnt = _slots(cur.get("filament_settings_id"))
        out.ops["filament_settings_id"] = json.dumps([fil_new] * cnt, ensure_ascii=False)
        if cur.get("default_filament_profile"):
            out.ops["default_filament_profile"] = json.dumps([fil_new] * cnt, ensure_ascii=False)
        out.notes.append(
            f"机型同步：耗材预设名换成「{fil_new}」（同一段耗材，这台机器认的那个名字）。")
    elif _first_str(cur.get("filament_settings_id")):
        out.warnings.append(
            "机型同步：没在这台机器上找到对应的耗材预设，耗材名保持原样。"
            "如果 Studio 提示耗材不兼容，请在软件里手动选一条该机型的耗材。")

    # ---- 只保留「值真的不同」的项。
    # 工程里没存这一行的标准键（printable_area / machine_max_* 等）也要写：
    # 不写的话 Studio 会按**旧机型**的机器预设去补，等于换机型没换全。
    # 这些键都在 SYNC_KEYS 里，保存时按 allow_missing 补写，不会被当成脏键。
    effective: dict[str, str] = {}
    for key, val in out.ops.items():
        if key in cur and str(cur.get(key)).strip() == str(val).strip():
            continue
        effective[key] = val
    added = sorted(k for k in effective if k not in cur)

    out.ops = effective
    out.changed = bool(effective)
    if effective:
        out.notes.append(
            f"机型同步：按你选的「{label}」重写机器页 {len(effective)} 项"
            f"（printer_model / printer_settings_id / 板面 / 硬件上限），"
            "并声明进 3mf 的机器槽，Bambu Studio 打开后会认成这台机器。")
    else:
        out.notes.append(
            f"机型同步：机器页已经是「{label}」的值，无需改动。")
    if added:
        out.notes.append(
            "机型同步：这 %d 个标准键你的工程里原来没有，已一并补上（Studio 认这些键）：%s"
            % (len(added), "、".join(added[:8])))
    if detected_key and detected_key != printer_key:
        out.warnings.append(
            f"你把机型从「{detected_key}」改成了「{label}」：机器页会被重写。"
            "首次在这台机器上打印前，请先在 Bambu Studio 里按这台机器做一次校准（振动补偿/流量/热床网格），"
            "否则参数是给新机器算的、机器的校准数据还是旧的。")
    return out
