"""把「改了哪些键」按归属写进 3mf 的 different_settings_to_system 三个槽位。

为什么必须有这一步（以及为什么旧版只对了三分之一）
--------------------------------------------------
Bambu Studio 打开工程时，三页参数各自独立解析：

    工艺页  → 按 print_settings_id 找同名系统预设，只把 different_settings_to_system[0]
              里列出的键当作「用户改过的」，其余取预设值。
    耗材页  → 同 different_settings_to_system[1]
    机器页  → 同 different_settings_to_system[2]

旧版只写了第 0 槽（工艺），于是：

    · 热床温度、风扇转速（这些键在 Bambu 里属于**耗材页**）虽然写进了
      project_settings.config，但没进第 1 槽 → Studio 用耗材预设覆盖回去。
      用户看到的现象就是「参数有时生效有时不生效」：
      同一份 3mf，工艺参数生效、热床和风扇总是回到预设值。
    · 换了机型后机器页同样没声明 → Studio 按旧机型预设重写机器页，
      表现成「生成的 3mf 不对应」。

本模块按 `core/scope.py` 的归属表分流：process → 槽 0，filament/thermal → 槽 1，
machine → 槽 2，meta 一律不写。

另外两件事：
    · `printable_area` / `printer_model` 这类**机器页结构性键**不允许进槽位声明
      （Studio 对它们的处理方式是重载整机预设，混进 different_settings 会报错）。
    · 槽位里的名字必须与项目里真实存在的键一致，否则 Studio 会认为声明无效。
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

STUDIO_DIRS = (
    Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL"),
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Bambu Studio"
    / "resources" / "profiles" / "BBL",
)
KIND_DIRS = ("process", "filament", "machine")

#: 结构性的机器页键：改了它们等于换机器，不能进 different_settings 槽位
MACHINE_STRUCTURAL = {
    "printer_model", "printer_settings_id", "printer_variant",
    "printable_area", "printable_height", "wrapping_exclude_area",
    "nozzle_diameter", "nozzle_volume", "default_print_profile",
    "default_filament_profile", "inherits_group", "printer_technology",
}

_CACHE: dict[str, dict | None] = {}


def _profiles_root() -> Path | None:
    for d in STUDIO_DIRS:
        if d.exists():
            return d
    return None


def find_preset(name: str, kind: str = "process") -> Path | None:
    root = _profiles_root()
    if not root or not name:
        return None
    direct = root / kind / f"{name}.json"
    if direct.exists():
        return direct
    for sub in KIND_DIRS:
        p = root / sub / f"{name}.json"
        if p.exists():
            return p
    return None


def load_preset(name: str, kind: str = "process") -> dict | None:
    """沿 inherits 链合并父级后返回完整键值表。"""
    key = f"{kind}:{name}"
    if key in _CACHE:
        return _CACHE[key]
    path = find_preset(name, kind)
    if path is None:
        _CACHE[key] = None
        return None
    try:
        data = json.load(io.open(path, encoding="utf-8-sig"))
    except Exception:
        _CACHE[key] = None
        return None
    parent = data.get("inherits")
    if parent:
        root = _profiles_root()
        base = None
        for sub in KIND_DIRS:
            cand = root / sub / f"{parent}.json" if root else None
            if cand and cand.exists():
                base = load_preset(parent, sub)
                break
        if base:
            merged = dict(base)
            merged.update(data)
            data = merged
    _CACHE[key] = data
    return data


def _norm(v):
    """把值归一成可比较形态：去空格、去 %、数字转 float、数组逐元素。"""
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, str):
        s = v.strip()
        if s.endswith("%"):
            s = s[:-1].strip()
        try:
            f = float(s)
            return round(f, 6)
        except ValueError:
            return s
    if isinstance(v, (int, float)):
        return round(float(v), 6)
    return v


#: 机器页的键前缀（SCOPE 表里没登记时按前缀兜底判定，否则会被错当工艺键写进槽0）
_MACHINE_PREFIXES = ("machine_", "printer_", "printable_")
_MACHINE_KEYS = frozenset({
    "nozzle_diameter", "nozzle_volume", "printer_variant", "printer_technology",
    "default_print_profile", "default_filament_profile", "inherits_group",
    "wrapping_exclude_area", "extruder_type", "extruder_variant",
})


def _scope_of(key: str) -> str:
    try:
        from .scope_data import SCOPE
    except Exception:                                    # pragma: no cover
        return "process"
    sc = SCOPE.get(key)
    if sc:
        return sc
    # SCOPE 没登记：机器页的键必须归机器槽，否则会被当成工艺键声明进槽0，
    # Studio 打开后机器页照样按旧机型覆盖回来（「选了机型却不对应」）。
    if key in _MACHINE_KEYS or key in MACHINE_STRUCTURAL:
        return "machine"
    if key.startswith(_MACHINE_PREFIXES):
        return "machine"
    return "process"


def diff_keys(settings: dict, preset: dict, *, scope_name: str = "process") -> list[str]:
    """settings 中与预设不一致的键（只比指定归属那一页的键）。"""
    out = []
    for k, pv in preset.items():
        if k not in settings:
            continue
        if _scope_of(k) != scope_name:
            continue
        if _norm(settings[k]) != _norm(pv):
            out.append(k)
    return sorted(out)


def process_diff(
    settings: dict,
    preset_name: str,
    *,
    also: list[str] | None = None,
) -> list[str]:
    """算出工艺页该写进 different_settings_to_system 的键。

    preset_name 解不出来（自定义档名）时，退化成「本次真正改过的键」（also）。
    """
    preset = load_preset(preset_name, "process") if preset_name else None
    if preset is None:
        return sorted(set(also or []))
    keys = diff_keys(settings, preset)
    if also:
        for k in also:
            # 被我们改过、但恰好等于预设值的键不必声明（Studio 会自己取预设值）
            if k in settings and k not in keys:
                pv = preset.get(k)
                if pv is not None and _norm(settings[k]) == _norm(pv):
                    continue
                keys.append(k)
    return sorted(set(keys))


def split_by_scope(keys) -> dict[str, list[str]]:
    """把键按归属拆成三槽：process / filament / machine（thermal 归耗材槽）。"""
    out: dict[str, list[str]] = {"process": [], "filament": [], "machine": []}
    for k in keys or []:
        sc = _scope_of(k)
        if sc in ("process",):
            out["process"].append(k)
        elif sc in ("filament", "thermal"):
            # 热床温度 / 风扇转速在 Bambu 里就是耗材页的键，
            # 必须走耗材槽声明，否则会被耗材预设覆盖（这正是「有时不生效」的根因）。
            out["filament"].append(k)
        elif sc == "machine":
            if k in MACHINE_STRUCTURAL:
                continue
            out["machine"].append(k)
        # meta 一律不写
    for slot in out:
        out[slot] = sorted(dict.fromkeys(out[slot]))
    return out


def _declared(preset_name: str, settings: dict, scope_name: str) -> list[str]:
    """用官方预设反查该页真正改过的键（预设读不到就返回空）。"""
    preset = load_preset(preset_name, "process" if scope_name == "process" else scope_name)
    if not preset:
        return []
    return diff_keys(settings, preset, scope_name=scope_name)


def update_settings_array(
    settings: dict,
    *,
    process_keys: list[str],
    filament_keys: list[str] | None = None,
    printer_keys: list[str] | None = None,
) -> list[str]:
    """返回新的 different_settings_to_system 三元组（就地不改 settings）。"""
    cur = settings.get("different_settings_to_system") or ["", "", ""]
    if isinstance(cur, str):
        # 工程里这个键是以「JSON 文本」形态存的（'["", "...", ""]'），先还原成列表
        txt = cur.strip()
        if txt.startswith("["):
            try:
                cur = json.loads(txt)
            except ValueError:
                cur = [cur, "", ""]
        else:
            cur = [cur, "", ""]
    cur = list(cur) + ["", "", ""]
    out = [cur[0], cur[1], cur[2]]
    for idx, extra in ((0, process_keys), (1, filament_keys), (2, printer_keys)):
        names = [x for x in str(out[idx] or "").split(";") if x]
        if extra:
            names.extend(extra)
        seen, uniq = set(), []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        out[idx] = ";".join(sorted(uniq))
    return out


def apply_to_project(project, *, also: list[str] | None = None) -> str:
    """把三页差异都写进工程内存里的 settings，返回写进去的说明。

    `also` 是本次真正改过的键（含热床/风扇），按归属自动分流到三个槽位。
    工艺槽还会额外用官方预设反查一遍，把「我们没改、但文件里本来就与预设不同」
    的键也声明上——否则那些键同样会被预设覆盖。
    """
    settings = project.settings
    preset_name = str(settings.get("print_settings_id")
                      or settings.get("default_print_profile") or "")

    buckets = split_by_scope(also or [])

    # 工艺槽：官方预设反查 + 本次改动
    p_keys = process_diff(settings, preset_name, also=buckets["process"])

    # 耗材槽：官方耗材预设反查 + 本次改的热床/风扇
    f_name = ""
    raw_ids = settings.get("filament_settings_id") or settings.get("default_filament_profile") or ""
    if isinstance(raw_ids, list):
        f_name = str(raw_ids[0] if raw_ids else "")
    else:
        txt = str(raw_ids).strip()
        if txt.startswith("["):
            try:
                arr = json.loads(txt)
                f_name = str(arr[0]) if arr else ""
            except (ValueError, TypeError):
                f_name = txt.strip('[]"\' ')
        else:
            f_name = txt
    f_keys = sorted(set(buckets["filament"]) | set(_declared(f_name, settings, "filament")))

    # 机器槽：只有非结构性键进得来（split_by_scope 已过滤）
    m_name = str(settings.get("printer_settings_id") or "")
    m_keys = sorted(set(buckets["machine"]) | set(_declared(m_name, settings, "machine")))

    tri = update_settings_array(settings, process_keys=p_keys,
                                filament_keys=f_keys, printer_keys=m_keys)
    # 保持工程原有的存储形态：这个键在 project_settings.config 里是数组，
    # 但 ThreeMfProject 内部把数组存成 JSON 文本，写回时也要还原成文本，
    # 否则底层 _typed_settings() 会再包一层。
    # 原工程里根本没有这个键时（被裁过的工程），先把它登记成数组类型，
    # 否则会作为一个纯字符串写进去，Studio 读不出来。
    if hasattr(project, "ensure_array_key"):
        project.ensure_array_key("different_settings_to_system", 3)
    settings["different_settings_to_system"] = json.dumps(tri, ensure_ascii=False)
    n_p = len([x for x in tri[0].split(";") if x])
    n_f = len([x for x in tri[1].split(";") if x])
    n_m = len([x for x in tri[2].split(";") if x])
    return (f"工艺 {n_p} 项 / 耗材 {n_f} 项 / 机器 {n_m} 项"
            f"（预设「{preset_name or '无法解析'}」）")


def declared_counts(settings: dict) -> tuple[int, int, int]:
    """读回三槽各声明了多少键（核对「是否真的生效」时用）。"""
    cur = settings.get("different_settings_to_system") or ["", "", ""]
    if isinstance(cur, str):
        txt = cur.strip()
        if txt.startswith("["):
            try:
                cur = json.loads(txt)
            except ValueError:
                cur = [txt, "", ""]
        else:
            cur = [txt, "", ""]
    cur = list(cur) + ["", "", ""]
    return tuple(len([x for x in str(cur[i] or "").split(";") if x]) for i in range(3))
