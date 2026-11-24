"""把「工艺页改了哪些键」写回 3mf 的 different_settings_to_system。

为什么必须有这一步
------------------
Bambu Studio 打开工程时，工艺页的值不是直接照抄 ``project_settings.config``：
它会先按 ``print_settings_id`` 找到同名的系统预设，然后只把
``different_settings_to_system[0]`` 里列出的键当作「用户改过的」，其余一律取预设值。
这份工程的 ``different_settings_to_system`` 是 ``['', '...', '']`` —— 工艺槽是空的，
意思是「工艺页与系统预设完全一致」，于是我们写进文件的 26 项改动被预设值原地覆盖。
表现出来的就是：文件里确实改了、UI 打开还是老参数。
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


def diff_keys(settings: dict, preset: dict) -> list[str]:
    """settings 中与预设不一致的键（只比「切片工艺页」的键）。

    预设文件里混着一批元数据键（``from`` / ``type`` / ``name`` / ``inherits`` /
    ``instantiation`` 等），它们不属于工艺页，列进 different_settings_to_system
    会让 Studio 困惑，所以要按 scope 白名单过滤。
    """
    try:
        from .scope_data import SCOPE
    except Exception:                                    # pragma: no cover
        SCOPE = {}
    out = []
    for k, pv in preset.items():
        if k not in settings:
            continue
        if SCOPE and SCOPE.get(k) != "process":
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
    """把工艺差异写进工程内存里的 settings，返回写进去的键数说明。

    project 需有 .settings（dict）。
    """
    settings = project.settings
    preset_name = str(settings.get("print_settings_id")
                      or settings.get("default_print_profile") or "")
    keys = process_diff(settings, preset_name, also=also)
    tri = update_settings_array(settings, process_keys=keys)
    # 保持工程原有的存储形态：这个键在 project_settings.config 里是数组，
    # 但 ThreeMfProject 内部把数组存成 JSON 文本，写回时也要还原成文本，
    # 否则底层 _typed_settings() 会再包一层。
    settings["different_settings_to_system"] = json.dumps(tri, ensure_ascii=False)
    n = len([x for x in tri[0].split(";") if x])
    return f"{n} 项（预设「{preset_name or '无法解析'}」）"
