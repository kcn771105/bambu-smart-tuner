"""打印/耗材预设名对机型是否兼容 —— 换机型时把预设名一起换掉。

为什么需要它
------------
把机器页改成「Bambu Lab P1S」之后，工程里的 `print_settings_id` 还是
`0.20mm Standard @BBL P2S`。Bambu Studio 切片的第一个动作就是校验
「工艺预设 / 耗材预设 的 compatible_printers 里有没有这台机器」，
不匹配就直接报：

    Slic3r::CLI::run 2746: process not compatible with printer.

命令行里一张图都不出 —— 用户看到的就是「换了机型，文件打不开/切不了」。

本模块做的事
------------
读本机 Studio 安装目录里的预设清单（`resources/profiles/BBL/process|filament/*.json`），
拿到每个预设的 `compatible_printers`（里面是 `Bambu Lab P1S 0.4 nozzle` 这种
机器预设名），于是可以回答两个问题：

    这个预设认不认这台机器？        → compatible()
    这台机器上「同层高/同耗材」的
    预设叫什么名字？                → remap()

注意 `compatible_printers` 匹配的是**机器预设名**（型号 + 喷嘴），不是型号本身，
所以调用方要传 `"Bambu Lab P1S 0.4 nozzle"`。这份清单不靠猜：读不到就直接返回
None，让上层的「机型同步」保持原样并给出提示。
"""

from __future__ import annotations

import json
import os
from typing import Any

__all__ = ["index", "compatible", "compat_of", "remap", "nozzle_of", "machine_settings_id"]

_CACHE_NAME = "preset_names.json"


def _root(extra: str = "") -> str:
    if extra:
        return extra
    try:
        from . import studio_env
        return studio_env.find_root()
    except Exception:
        return ""


def _cache_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "BambuSmartTuner")
    return os.path.join(folder, _CACHE_NAME)


def _stamp(root: str) -> float:
    newest = 0.0
    for kind in ("process", "filament"):
        folder = os.path.join(root, "resources", "profiles", "BBL", kind)
        if not os.path.isdir(folder):
            continue
        try:
            newest = max(newest, os.path.getmtime(folder))
        except OSError:
            pass
    return newest


def _scan(root: str, kind: str) -> list:
    folder = os.path.join(root, "resources", "profiles", "BBL", kind)
    out = []
    if not os.path.isdir(folder):
        return out
    for fname in os.listdir(folder):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(folder, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception:
            continue
        name = str(cfg.get("name") or fname[:-5]).strip()
        compat = cfg.get("compatible_printers") or []
        if isinstance(compat, str):
            compat = [compat]
        out.append({
            "name": name,
            "compat": [str(c).strip() for c in compat if str(c).strip()],
            "nozzle": str(cfg.get("nozzle_diameter") or ""),
        })
    return out


def index(root: str = "") -> dict:
    """{'process': [...], 'filament': [...]}，带磁盘缓存（目录 mtime 变才重扫）。"""
    inst = _root(root)
    if not inst:
        return {"process": [], "filament": []}
    stamp = _stamp(inst)
    cache = _cache_path()
    if cache:
        try:
            with open(cache, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if raw.get("root") == inst and abs(float(raw.get("stamp", 0)) - stamp) < 1e-6:
                return raw.get("data") or {"process": [], "filament": []}
        except Exception:
            pass

    data = {"process": _scan(inst, "process"), "filament": _scan(inst, "filament")}
    if cache:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump({"root": inst, "stamp": stamp, "data": data},
                          fh, ensure_ascii=False)
        except OSError:
            pass
    return data


def nozzle_of(printer_settings_id: str) -> str:
    """从 `Bambu Lab P1S 0.6 nozzle` 里取回 `0.6`。"""
    text = str(printer_settings_id or "").strip()
    if not text:
        return ""
    words = text.split()
    if len(words) >= 2 and words[-1] == "nozzle":
        return words[-2]
    return ""


def _mm(text: str) -> float | None:
    """`0.20mm` → 0.20。"""
    raw = str(text or "").strip().lower()
    if raw.endswith("mm"):
        raw = raw[:-2]
    try:
        return float(raw)
    except ValueError:
        return None


def _quality(name: str) -> str:
    """`0.20mm Standard @BBL P2S` → `Standard`。"""
    parts = _base_prefix(name).split()
    return parts[1] if len(parts) > 1 else ""


def _base_prefix(name: str) -> str:
    """`0.20mm Standard @BBL P2S` → `0.20mm Standard`；`多彩屋petg` → 原样。"""
    text = str(name or "").strip()
    if "@" in text:
        return text.split("@", 1)[0].strip()
    return text


def compatible(name: str, printer_settings_id: str, kind: str = "process",
               root: str = "") -> bool:
    """这个预设认不认这台机器。读不到清单时返回 True（不拦）。"""
    data = index(root)
    items = data.get(kind) or []
    if not items:
        return True
    want = str(printer_settings_id or "").strip()
    for item in items:
        if item["name"] == str(name or "").strip():
            if not item["compat"]:
                return False
            return any(c == want for c in item["compat"])
    return False


def compat_of(name: str, kind: str = "process", root: str = "") -> list:
    """这个预设自己声明的 compatible_printers（机器预设名列表）。"""
    want = str(name or "").strip()
    for item in (index(root).get(kind) or []):
        if item["name"] == want:
            return list(item["compat"])
    return []


def remap(name: str, printer_settings_id: str, kind: str = "process",
          root: str = "", strict: bool = False) -> str | None:
    """在目标机器上给「同一个预设」找一个能用的名字。

    先按「同前缀」（同层高/同质量/同耗材）找，找不到再退到同层高的 Standard，
    最后退到这台机器上任意一个兼容预设。都不行返回 None。
    """
    data = index(root)
    items = [i for i in (data.get(kind) or []) if i["compat"]]
    if not items:
        return None
    want = str(printer_settings_id or "").strip()
    usable = [i for i in items if any(c == want for c in i["compat"])]
    if not usable:
        return None
    prefix = _base_prefix(name)
    same = [i for i in usable if _base_prefix(i["name"]) == prefix]
    if same:
        return same[0]["name"]
    # 退一步：只保留层高段（`0.20mm`）相同
    head = prefix.split(" ", 1)[0]
    same_head = [i for i in usable if i["name"].startswith(head + " ")]
    if same_head:
        return same_head[0]["name"]
    # 再退一步：层高最接近的那个（换喷嘴时层的可选值会变，0.20mm 在 0.6 喷嘴上没有）
    target = _mm(head)
    if target is not None:
        scored = []
        for item in usable:
            val = _mm(item["name"].split(" ", 1)[0])
            if val is None:
                continue
            # 同一个质量档优先（Standard 找 Standard），再比层高差
            quality = 0 if _quality(prefix) and _quality(item["name"]) == _quality(prefix) else 1
            scored.append((quality, abs(val - target), item["name"]))
        if scored:
            scored.sort()
            return scored[0][2]
    # strict：宁可不错，也不要把 PLA 换成 ABS —— 型号不一致就交回调用方处理
    return None if strict else usable[0]["name"]


def machine_settings_id(label: str, nozzle: float | str = "0.4") -> str:
    """`Bambu Lab P1S` + 0.4 → `Bambu Lab P1S 0.4 nozzle`。"""
    text = f"{float(nozzle):g}" if str(nozzle).replace(".", "", 1).isdigit() else str(nozzle)
    return f"{label} {text} nozzle"


def names_by_model(kind: str = "process", root: str = "") -> dict:
    """给排错用：{机器预设名: [预设名...]}。"""
    out: dict[str, list] = {}
    for item in (index(root).get(kind) or []):
        for c in item["compat"]:
            out.setdefault(c, []).append(item["name"])
    return out
