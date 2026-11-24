"""同步 Bambu Studio / OrcaSlicer 里的用户自定义耗材预设

原理
----
Bambu Studio 的耗材预设是「继承链 + 差分覆盖」：

    %APPDATA%\\BambuStudio\\user\\<user_id>\\filament\\我的耗材.json
        { "name": "彩格petg", "inherits": "Generic PETG @BBL P2S", ... 只写改过的键 }

    C:\\Program Files\\Bambu Studio\\resources\\profiles\\BBL\\filament\\Generic PETG @BBL P2S.json
        { "inherits": "Generic PETG @base", ... }

    ...  Base @base → fdm_filament_pet → fdm_filament_common

要把「我这个耗材到底是什么特性」算出来，必须沿 inherits 一路解析合并。
本模块做这件事，并把结果转成规则引擎可以直接吃的「耗材覆盖层」：

    filament_overrides[name] = {
        "filament_family": "PETG",          # 归到内置五族之一（决定用哪套基线）
        "limits.max_volumetric_speed": 12,   # 真实体积流量上限（用户/厂商给的）
        "baseline": {...},                   # 覆盖到基线里的真实值
        "source": "bambu", "raw_name": "彩格petg", "path": "..."
    }

这样用户在「自定义耗材」里选到自己那一支，就能拿到厂商/自己标定过的
体积流量、风扇、流量比例、回抽，而不是套内置的五族平均值。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 内置五族 + 兜底；顺序也会决定下拉框顺序
FAMILIES = ("PLA", "PETG", "ASA", "ABS", "TPU")

# 名称 → 族 的识别表（顺序敏感：先匹配长串，避免 "PA6-CF" 被 "PA" 吃掉）
FAMILY_HINTS: tuple[tuple[str, str], ...] = (
    ("TPU", "TPU"), ("TPE", "TPU"), ("PEBA", "TPU"),
    ("PETG", "PETG"), ("PET", "PETG"),
    ("ASA", "ASA"),
    ("ABS", "ABS"), ("HIPS", "ABS"),
    ("PLA", "PLA"),
    ("PC", "ABS"), ("PA", "ABS"), ("NYLON", "ABS"),   # 高温工程料按 ABS 保守基线走
    ("PVA", "PLA"), ("BVOH", "PLA"),
    ("SUPPORT", "PLA"),
)

FAN_KEYS = ("fan_min_speed", "fan_max_speed", "overhang_fan_speed")
RETRACT_KEYS = (
    "filament_retraction_length", "filament_retraction_speed",
    "filament_deretraction_speed", "filament_z_hop", "filament_wipe",
    "filament_wipe_distance", "filament_retract_before_wipe",
    "filament_retract_restart_extra", "filament_retraction_minimum_travel",
)


class ProfileError(Exception):
    """预设目录不可读、JSON 坏掉等，消息可直接展示。"""


@dataclass
class FilamentPreset:
    name: str
    path: Path
    source: str                      # bambu / orca
    inherits: str = ""
    family: str = "PLA"
    raw_type: str = ""
    chain: list[str] = field(default_factory=list)
    merged: dict = field(default_factory=dict)
    # 抽出并经转换的关键特性（都是「最终生效值」）
    volumetric_speed: float | None = None
    fan_min: float | None = None
    fan_max: float | None = None
    flow_ratio: float | None = None
    pressure_advance: float | None = None
    nozzle_temp: float | None = None
    density: float | None = None
    cost: float | None = None
    filament_id: str = ""
    is_base: bool = False            # 名字以 @base 结尾（不是可选中项）
    resolvable: bool = True
    problems: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.family}"

    @property
    def display_detail(self) -> str:
        bits = [f"族 {self.family}"]
        if self.volumetric_speed:
            bits.append(f"流量上限 {self.volumetric_speed:g} mm³/s")
        if self.flow_ratio:
            bits.append(f"流量比 {self.flow_ratio:g}")
        if self.fan_max is not None:
            bits.append(f"风扇 {self.fan_min or 0:g}~{self.fan_max:g}%")
        if self.nozzle_temp:
            bits.append(f"喷嘴 {self.nozzle_temp:g}°C")
        return " ｜ ".join(bits)


# ------------------------------------------------------------------ 目录发现

def candidate_roots() -> list[tuple[str, Path]]:
    """返回 [(来源标签, 用户预设根目录)]，只含真实存在的。"""
    out: list[tuple[str, Path]] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        for tag, sub in (("bambu", "BambuStudio"), ("bambu", "BambuStudioBeta"),
                         ("orca", "OrcaSlicer")):
            base = Path(appdata) / sub / "user"
            if base.is_dir():
                out.append((tag, base))
    # Linux/macOS 也顺手支持一下（用户可能在那边跑）
    home = Path.home()
    for tag, rel in (("bambu", ".config/BambuStudio/user"),
                     ("orca", ".config/OrcaSlicer/user"),
                     ("bambu", "Library/Application Support/BambuStudio/user")):
        p = home / rel
        if p.is_dir():
            out.append((tag, p))
    return out


def system_profile_dirs() -> list[Path]:
    """Bambu Studio / Orca 安装目录里的系统预设（解析继承链要用）。"""
    dirs: list[Path] = []
    env = os.environ
    cands = [
        Path(env.get("ProgramFiles", r"C:\Program Files")) / "Bambu Studio" / "resources" / "profiles",
        Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Bambu Studio" / "resources" / "profiles",
        Path(env.get("LOCALAPPDATA", "")) / "Programs" / "Bambu Studio" / "resources" / "profiles",
        Path("/usr/share/BambuStudio/resources/profiles"),
        Path("/Applications/BambuStudio.app/Contents/Resources/profiles"),
    ]
    for c in cands:
        try:
            if c.is_dir():
                dirs.append(c)
        except OSError:
            continue
    return dirs


# ------------------------------------------------------------------ 继承链解析

def _load_json(p: Path) -> dict | None:
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _iter_filament_files(user_root: Path):
    """用户目录下所有 filament/*.json；兼容 <user_id>/filament 与直接 filament。"""
    found = 0
    direct = user_root / "filament"
    if direct.is_dir():
        for f in direct.glob("*.json"):
            yield f
            found += 1
    for sub in user_root.iterdir() if user_root.is_dir() else ():
        fdir = sub / "filament"
        if sub.is_dir() and fdir.is_dir():
            for f in fdir.glob("*.json"):
                yield f
                found += 1
    if not found:
        # 兜底：递归找 filaments（老版本或第三方分支）
        for f in user_root.rglob("filament/*.json"):
            yield f


def build_index(system_dirs: list[Path] | None = None) -> dict[str, dict]:
    """名字 → {"path": Path, "data": dict}，用户预设优先覆盖系统同名项。"""
    index: dict[str, dict] = {}
    for root in (system_dirs if system_dirs is not None else system_profile_dirs()):
        fdir = root / "BBL" / "filament"
        search = fdir if fdir.is_dir() else root
        for f in search.rglob("*.json"):
            d = _load_json(f)
            if not d or d.get("type") not in (None, "filament"):
                continue
            name = d.get("name") or f.stem
            index[name] = {"path": f, "data": d}
    return index


def resolve(name: str, index: dict[str, dict], _seen: set[str] | None = None) -> tuple[dict, list[str]]:
    """沿 inherits 向上合并，返回 (合并结果, 继承链名字列表)。"""
    seen = _seen or set()
    chain: list[str] = []
    merged: dict = {}
    cur = name
    while cur and cur not in seen:
        seen.add(cur)
        node = index.get(cur)
        if not node:
            break
        chain.append(cur)
        merged = {**node["data"], **merged}       # 上层先铺，下层覆盖
        cur = node["data"].get("inherits")
    # 反向：让「子类覆盖父类」成立
    merged = {}
    for nm in reversed(chain):
        merged.update(index[nm]["data"])
    return merged, chain


def _num(v) -> float | None:
    """预设里的值几乎都是 ["0.98", "0.98"] / "15%" / "nil" 这种。"""
    if v is None:
        return None
    if isinstance(v, list):
        for x in v:
            r = _num(x)
            if r is not None:
                return r
        return None
    txt = str(v).strip()
    if txt.lower() in ("nil", "none", "", "null"):
        return None
    txt = txt.rstrip("%")
    try:
        return float(txt)
    except ValueError:
        return None


def _first_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        for x in v:
            if str(x).lower() not in ("nil", "", "none"):
                return str(x)
        return ""
    return str(v)


def infer_family(preset_name: str, merged: dict) -> tuple[str, str]:
    """返回 (归族, 原始类型串)。"""
    raw = _first_str(merged.get("filament_type"))
    probe = f"{raw} {preset_name}".upper()
    for hint, fam in FAMILY_HINTS:
        if hint in probe:
            return fam, raw or hint
    # 再看 filament_id 前缀（GFA=PLA, GFB=PETG, GFC=ABS, GFS=SUPPORT, GFU=TPU, GFG=ASA…）
    fid = (_first_str(merged.get("filament_id")) or "").upper()
    idmap = {"GFA": "PLA", "GFB": "PETG", "GFC": "ABS", "GFG": "ASA",
             "GFU": "TPU", "GFP": "PA", "GFS": "PLA"}
    for pre, fam in idmap.items():
        if fid.startswith(pre):
            if fam == "PA":
                return "ABS", raw or fam
            return fam, raw or fam
    return "PLA", raw or "PLA"


def _to_preset(name: str, node: dict, index: dict[str, dict], source: str) -> FilamentPreset:
    merged, chain = resolve(name, index)
    family, raw_type = infer_family(name, merged)
    preset = FilamentPreset(
        name=name, path=node["path"], source=source,
        inherits=str(node["data"].get("inherits") or ""),
        family=family, raw_type=raw_type, chain=chain, merged=merged,
        is_base=name.endswith("@base") or node["data"].get("instantiation") == "false",
        filament_id=_first_str(merged.get("filament_id")),
    )
    if not chain:
        preset.resolvable = False
        preset.problems.append("找不到父预设（Bambu Studio 可能装在非默认位置）")

    preset.volumetric_speed = _num(merged.get("filament_max_volumetric_speed"))
    preset.fan_min = _num(merged.get("fan_min_speed"))
    preset.fan_max = _num(merged.get("fan_max_speed"))
    preset.flow_ratio = _num(merged.get("filament_flow_ratio"))
    preset.pressure_advance = _num(merged.get("pressure_advance"))
    preset.nozzle_temp = (_num(merged.get("nozzle_temperature"))
                          or _num(merged.get("nozzle_temperature_initial_layer")))
    preset.density = _num(merged.get("filament_density"))
    preset.cost = _num(merged.get("filament_cost"))
    return preset


def scan(roots: list[tuple[str, Path]] | None = None,
         system_dirs: list[Path] | None = None) -> list[FilamentPreset]:
    """扫描所有用户自定义耗材预设。失败不抛异常，返回空列表并在 stderr 说明。"""
    index = build_index(system_dirs)
    presets: list[FilamentPreset] = []
    seen_names: set[str] = set()

    for source, user_root in (roots if roots is not None else candidate_roots()):
        try:
            files = list(_iter_filament_files(user_root))
        except OSError:
            continue
        for f in files:
            data = _load_json(f)
            if not data:
                continue
            name = str(data.get("name") or f.stem)
            if data.get("type") not in (None, "filament"):
                continue
            if name in seen_names or name.endswith("@base"):
                continue          # 同名只取第一份；@base 是抽象基类，不是可选耗材
            seen_names.add(name)
            # 用户预设优先塞进索引，保证它自己的父链能解析
            index.setdefault(name, {"path": f, "data": data})
            presets.append(_to_preset(name, {"path": f, "data": data}, index, source))

    presets.sort(key=lambda p: (p.source, p.family, p.name.lower()))
    return presets


# ------------------------------------------------------------------ 转成规则覆盖层

def to_overlay(preset: FilamentPreset) -> dict:
    """把一支自定义耗材转成规则引擎能吃的覆盖层。

    只覆盖「耗材真的决定了」的参数：体积流量、风扇、流量比例、回抽、压力提前。
    层高/速度/加速度这类属于机型+策略范畴，不在这里写死。
    """
    baseline: dict = {}
    if preset.fan_min is not None:
        baseline["fan_min_speed"] = preset.fan_min
    if preset.fan_max is not None:
        baseline["fan_max_speed"] = preset.fan_max
        baseline["overhang_fan_speed"] = preset.fan_max
    if preset.flow_ratio is not None:
        baseline["filament_flow_ratio"] = preset.flow_ratio
    if preset.pressure_advance is not None:
        baseline["pressure_advance"] = preset.pressure_advance

    rl = _num(preset.merged.get("filament_retraction_length"))
    rs = _num(preset.merged.get("filament_retraction_speed"))
    ds = _num(preset.merged.get("filament_deretraction_speed"))
    if rl is not None:
        baseline["retraction_length"] = rl
    if rs is not None:
        baseline["retraction_speed"] = rs
    if ds is not None:
        baseline["deretraction_speed"] = ds

    limits: dict = {}
    if preset.volumetric_speed:
        limits["max_volumetric_speed"] = preset.volumetric_speed

    return {
        "label": preset.name,
        "family": preset.family,
        "raw_type": preset.raw_type,
        "source": preset.source,
        "path": str(preset.path),
        "chain": preset.chain,
        "limits": limits,
        "baseline": baseline,
        "nozzle_temperature": preset.nozzle_temp,
        "density": preset.density,
        "cost": preset.cost,
        "filament_id": preset.filament_id,
    }


def export_overlays(presets: list[FilamentPreset], path: str | Path) -> Path:
    """把扫到的耗材导出成 JSON，方便用户审阅或手工改。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_comment": "由 Bambu Smart Tuner 从 Bambu Studio 用户预设自动导出；"
                    "改这份文件不会影响 Bambu Studio，只影响本程序的自定义耗材表。",
        "presets": {pr.name: to_overlay(pr) for pr in presets},
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def describe(presets: list[FilamentPreset]) -> str:
    if not presets:
        return "没有扫描到自定义耗材预设。"
    by_src: dict[str, int] = {}
    for p in presets:
        by_src[p.source] = by_src.get(p.source, 0) + 1
    parts = [f"{k} {v} 支" for k, v in by_src.items()]
    bad = sum(1 for p in presets if not p.resolvable)
    tail = f"；其中 {bad} 支父链未解析（缺系统预设）" if bad else ""
    return f"共 {len(presets)} 支自定义耗材（{'，'.join(parts)}）{tail}"


if __name__ == "__main__":       # 直接跑可看本机扫到了什么
    ps = scan()
    print(describe(ps))
    for p in ps:
        print(f"  [{p.source}] {p.name}  ← {p.family}  {p.display_detail}")
        if p.problems:
            print("      !", "；".join(p.problems))
    if ps:
        out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("filament_overlays.json")
        print("已导出：", export_overlays(ps, out))
