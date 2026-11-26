"""参数方案（预设）：把「机型 + 耗材 + 喷嘴 + 模式 + 板子 + 室温 + 支撑档 + 几何开关」
存成一套，下次一键套用。

用户反馈第 3 条：「就是预设几套参数在软件里呗」。

更实际的问题是（同一条反馈里紧接着的抱怨）：参数改了、说明太绕、每次都要重来一遍。
所以这里的「方案」不只是存参数值，而是**存整条决策链的输入**：

    printer / filament / nozzle / mode        —— 你选的东西
    bed_type / room_c / fan_trim              —— 环境（第 2 条反馈要的）
    support_ease / support_mode               —— 支撑好拆程度
    shape / seam_smooth                       —— 两个几何开关
    machine_sync / time_cap                   —— 两个保存/回调开关

套用时把这些填回界面 → 引擎重算 → 得到和上次完全一样的参数。
参数值本身不落盘（规则库改了以后方案会自动用上新规则，而不是固化成旧值）。

存储
----
    %APPDATA%/BambuSmartTuner/presets.json      （Windows）
    ~/.config/BambuSmartTuner/presets.json      （其它平台）
格式：
    {
      "version": 1,
      "presets": [
        {"name": "A1 mini · PETG · 冷天", "builtin": false, "values": {...}},
        ...
      ]
    }
内置三套（只读，不可删）拷在下面 BUILTIN 里。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Preset", "BUILTIN", "load_all", "save_all", "upsert", "remove",
           "store_path", "to_values", "from_values"]

#: 方案里最多保存这些字段（其余一律忽略，避免存进一堆无关状态）
FIELDS = (
    "printer", "filament", "nozzle", "mode",
    "bed_type", "room_c", "fan_trim",
    "support_ease", "support_mode",
    "shape", "seam_smooth", "machine_sync", "time_cap",
)


@dataclass
class Preset:
    name: str
    values: dict = field(default_factory=dict)
    builtin: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "builtin": self.builtin,
                "values": {k: v for k, v in self.values.items() if k in FIELDS}}

    def summary(self) -> str:
        v = self.values
        bits = [
            str(v.get("printer") or "—"),
            str(v.get("filament") or "—"),
            f"{v.get('nozzle', 0.4):g} mm" if v.get("nozzle") else "—",
            str(v.get("mode") or "—"),
        ]
        if v.get("bed_type"):
            bits.append(str(v["bed_type"]))
        if v.get("room_c") not in (None, ""):
            bits.append(f"室温 {float(v['room_c']):g}°C")
        if v.get("support_ease") and v["support_ease"] != "standard":
            bits.append({"easy": "支撑好拆", "max": "支撑极好拆"}.get(v["support_ease"], ""))
        if v.get("seam_smooth"):
            bits.append("斜接缝")
        return " · ".join(x for x in bits if x)


#: 内置三套：覆盖用户最常问的三个场景
BUILTIN: tuple[Preset, ...] = (
    Preset(
        name="快速出件（草稿 · PLA）",
        builtin=True,
        values={"filament": "PLA", "mode": "draft", "nozzle": 0.4,
                "support_ease": "standard", "support_mode": "auto",
                "shape": True, "seam_smooth": False, "machine_sync": True,
                "time_cap": True, "room_c": 22, "fan_trim": 0},
    ),
    Preset(
        name="外观优先（精细 · 圆柱斜接缝）",
        builtin=True,
        values={"filament": "PLA", "mode": "fine", "nozzle": 0.4,
                "support_ease": "easy", "support_mode": "auto",
                "shape": True, "seam_smooth": True, "machine_sync": True,
                "time_cap": True, "room_c": 22, "fan_trim": 0},
    ),
    Preset(
        name="冷天不翘边（PETG · 室温 12°C）",
        builtin=True,
        values={"filament": "PETG", "mode": "balanced", "nozzle": 0.4,
                "bed_type": "Textured PEI Plate", "room_c": 12, "fan_trim": -10,
                "support_ease": "easy", "support_mode": "auto",
                "shape": True, "seam_smooth": False, "machine_sync": True,
                "time_cap": True},
    ),
)


def store_path() -> Path:
    """方案文件位置（打包后也写在用户目录，不写程序目录）。"""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "BambuSmartTuner" / "presets.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "BambuSmartTuner" / "presets.json"


def _read_file(path: Path) -> list[Preset]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    out: list[Preset] = []
    for row in (data.get("presets") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        vals = row.get("values") or {}
        out.append(Preset(name=name, values=to_values(vals),
                          builtin=bool(row.get("builtin"))))
    return out


def to_values(raw: dict) -> dict:
    """只保留白名单字段，并把数值字段转成正确类型。"""
    out: dict = {}
    for k in FIELDS:
        if k not in (raw or {}):
            continue
        v = raw[k]
        if k == "nozzle":
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = 0.4
        elif k == "room_c":
            if v in (None, ""):
                out[k] = None
            else:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    out[k] = None
        elif k == "fan_trim":
            try:
                out[k] = int(round(float(v)))
            except (TypeError, ValueError):
                out[k] = 0
        elif k in ("shape", "seam_smooth", "machine_sync", "time_cap"):
            out[k] = bool(v)
        else:
            out[k] = str(v)
    return out


def from_values(values: dict, name: str) -> Preset:
    """从界面状态造一个方案（用于「保存当前设置为方案」）。"""
    return Preset(name=name, values=to_values(values), builtin=False)


def load_all() -> list[Preset]:
    """内置 + 用户方案（用户方案在后，同名时用户方案优先）。"""
    user = [p for p in _read_file(store_path()) if not p.builtin]
    names = {p.name for p in user}
    merged = [p for p in BUILTIN if p.name not in names] + user
    return merged


def save_all(presets: list[Preset]) -> Path:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "presets": [p.as_dict() for p in presets if not p.builtin],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def upsert(presets: list[Preset], preset: Preset) -> list[Preset]:
    """同名覆盖，返回新的用户方案列表（不含内置）。"""
    user = [p for p in presets if not p.builtin and p.name != preset.name]
    user.append(Preset(name=preset.name, values=to_values(preset.values),
                       builtin=False))
    return user


def remove(presets: list[Preset], name: str) -> list[Preset]:
    return [p for p in presets if p.builtin or p.name != name]
