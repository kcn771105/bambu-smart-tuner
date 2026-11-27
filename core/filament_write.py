"""耗材页怎么写：一个字节不碰 / 写进你当前那份 / 另存成一份新的。

对应反馈：「可以选是不是更改耗材，如果选了『新建一份耗材参数』，
就在用户原有的基础上优化、另存一份」。

三个档位：

    keep  不动耗材页。热床温度、风速、喷头温度、压力提前、流量比这些
          都属于耗材页，一并不写 —— 想只调工艺、耗材保持原样时用这档。
    file  写进工程现在用的那份耗材（默认，等于「在你自己那份上改」）。
    new   先写好同样的值，再把 `filament_settings_id` 换成
          「原名 + 优化」——Studio 打开会显示成一份**改过但没保存**的自定义耗材，
          你在耗材列表里点「保存」就多出一份新的，原 preset 一个字没动。

注意 Studio 的耗材是「预设 + 差异声明」两段式：改名只改显示与归属，
真正的参数值仍写在工程的 filament 页，并在 `different_settings_to_system`
的耗材槽里声明为「与预设不同」。这两件事由 preset_diff 一起完成。
"""

from __future__ import annotations

from dataclasses import dataclass, field

MODES = ("keep", "file", "new")

MODE_LABELS: dict[str, str] = {
    "keep": "不改耗材页（只调工艺）",
    "file": "写进当前耗材（在你自己那份上改）",
    "new": "新建一份耗材（在你原有基础上优化）",
}

SUFFIX = " 优化"


def mode_options() -> list[tuple[str, str]]:
    return [(MODE_LABELS[m], m) for m in MODES]


def normalize(mode: str | None) -> str:
    txt = (mode or "file").strip().lower()
    return txt if txt in MODES else "file"


def new_name(base: str) -> str:
    """「原名 + 优化」，已经是这个名字就不重复加。"""
    txt = (base or "").strip() or "自定义耗材"
    if txt.endswith(SUFFIX):
        return txt
    return txt + SUFFIX


@dataclass
class FilamentPlan:
    ops: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    name: str = ""
    mode: str = "file"


def plan(mode: str, *, base_name: str = "", settings: dict | None = None,
         slots: int = 1) -> FilamentPlan:
    """只负责「名字」这一件事；参数值本身由调用方照常写入。"""
    mode = normalize(mode)
    out = FilamentPlan(mode=mode)
    if mode != "new":
        return out

    settings = settings or {}
    base = base_name or str(settings.get("filament_settings_id") or "").strip()
    if base.startswith("["):
        # 工程里存成 JSON 数组文本：["Bambu PLA Basic @BBL P2S"]
        try:
            import json
            arr = json.loads(base)
            base = str(arr[0]) if arr else ""
        except ValueError:
            base = base.strip("[]").strip('"')
    name = new_name(base)
    out.name = name
    n = max(1, int(slots or 1))
    out.ops["filament_settings_id"] = [name] * n
    out.notes.append(
        f"耗材另存为「{name}」—— Studio 打开会显示成一份改过但没保存的耗材，"
        "在你原来的耗材上点「保存」就多出一份新的，原预设不会被改。")
    return out


def split_by_mode(values: dict, mode: str, scope_of) -> tuple[dict, list[str]]:
    """按档位过滤要写的键：keep 档把耗材页/热床页的键统统拿掉。

    `scope_of(key)` 返回 "process"/"filament"/"thermal"/"machine"/"meta"。
    """
    mode = normalize(mode)
    if mode != "keep":
        return dict(values or {}), []
    kept, dropped = {}, []
    for key, value in (values or {}).items():
        sc = scope_of(key)
        if sc in ("filament", "thermal"):
            dropped.append(key)
        else:
            kept[key] = value
    return kept, sorted(dropped)
