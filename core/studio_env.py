"""本机 Bambu Studio 的「环境探测」：它认识哪些板子、哪些机型、版本多新。

为什么需要这一层：

我们的规则库是从一份**较新**的官方配置导出的，里面包含 `Supertack Plate`（超粘板）这类
新板。但如果用户机器上装的 Studio 比较旧，它的板子清单里根本没有这块板——于是我们写进
3mf 的 `curr_bed_type = Supertack Plate` 到了 Studio 那边就成了一个不认识的板：

    * 板子下拉里选不上（Studio 会退回自己的默认板）；
    * 板温用的是 `supertack_plate_temp` 这个它不读的键，看起来就是「温度没生效」。

同一份工程还可能带着「比自己 Studio 更新」的版本号（`Metadata/project_settings.config`
里的 `version`），Studio 会按旧规则解释新键，行为也可能不对。

所以这里不猜，直接读本机安装目录：

    resources/profiles/BBL.json        → 配置包版本（≈ Studio 版本）、机型清单
    resources/profiles/BBL/machine/*   → 每个机型有哪些喷嘴预设
    resources/i18n/*/BambuStudio.mo    → 界面里真实存在的板子名字

探测结果缓存在 `%APPDATA%/BambuSmartTuner/studio_env.json`，配置包一改动就失效。
"""

from __future__ import annotations

import json
import os
import re
import struct
import sys
from dataclasses import dataclass, field, asdict

__all__ = [
    "PLATE_CANDIDATES", "StudioEnv", "detect", "supported_plates",
    "supports_plate", "supports_machine", "compare_versions", "compat_report",
    "find_root",
]

#: 我们规则库里可能出现的板子（英文名 = 写进 3mf 的 `curr_bed_type`）
PLATE_CANDIDATES = (
    "Supertack Plate",
    "Textured PEI Plate",
    "Smooth PEI Plate / High Temp Plate",
    "Engineering Plate",
    "Cool Plate",
)

#: 板子英文名 → 板温键
PLATE_KEYS = {
    "Supertack Plate": "supertack_plate_temp",
    "Textured PEI Plate": "textured_plate_temp",
    "Smooth PEI Plate / High Temp Plate": "hot_plate_temp",
    "High Temp Plate": "hot_plate_temp",
    "Engineering Plate": "eng_plate_temp",
    "Cool Plate": "cool_plate_temp",
}

#: 常见安装目录
_ROOTS = (
    r"C:\Program Files\Bambu Studio",
    r"C:\Program Files (x86)\Bambu Studio",
    r"D:\Program Files\Bambu Studio",
    r"E:\Program Files\Bambu Studio",
)

_CACHE_NAME = "studio_env.json"


# ---------------------------------------------------------------- 缓存位置


def _cache_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "BambuSmartTuner")
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return ""
    return os.path.join(folder, _CACHE_NAME)


def find_root(extra: str = "") -> str:
    """找到安装根目录（里面有 resources/profiles）。"""
    candidates = ([extra] if extra else []) + list(_ROOTS)
    for root in candidates:
        if root and os.path.isfile(os.path.join(root, "resources", "profiles", "BBL.json")):
            return root
    return ""


# ---------------------------------------------------------------- 数据结构


@dataclass
class StudioEnv:
    """本机 Studio 的能力快照。`found=False` 表示没装/没找到。"""

    found: bool = False
    root: str = ""
    version: str = ""                       # 配置包版本，如 02.03.00.02
    plates: list = field(default_factory=list)      # 它认识的板子英文名
    machines: list = field(default_factory=list)    # 它认识的 printer_model
    notes: list = field(default_factory=list)

    def supports_plate(self, name: str) -> bool:
        if not self.found:
            return True                      # 没装 Studio 就不拦
        key = _norm_plate(name)
        return any(_norm_plate(p) == key for p in self.plates)

    def supports_machine(self, model: str) -> bool:
        if not self.found:
            return True
        want = _norm_machine(model)
        return any(_norm_machine(m) == want for m in self.machines)


#: 中文板名 → 英文标准名。Studio 的 .mo 文件里是英文串，用户看到的是中文，
#: 两边比对前先归一到同一套英文名上。
_ZH_PLATES = {
    "超粘板": "Supertack Plate",
    "增稳低温打印板": "Cool Plate",
    "低温板": "Cool Plate",
    "工程材料打印板": "Engineering Plate",
    "工程板": "Engineering Plate",
    "纹理pei打印板": "Textured PEI Plate",
    "纹理pei板": "Textured PEI Plate",
    "光面pei打印板": "Smooth PEI Plate / High Temp Plate",
    "光面pei板": "Smooth PEI Plate / High Temp Plate",
    "高温打印板": "Smooth PEI Plate / High Temp Plate",
    "高温板": "Smooth PEI Plate / High Temp Plate",
}


def _norm_plate(name: str) -> str:
    s = str(name or "").strip()
    low = s.lower().replace(" ", "")
    for zh, en in _ZH_PLATES.items():
        if zh == low:
            s = en
            break
    s = s.strip().lower()
    s = s.replace("smooth pei plate", "high temp plate").replace("smooth pei", "high temp plate")
    return re.sub(r"\s+", " ", s)


# ---------------------------------------------------------------- 探测


def _read_bbl_json(root: str) -> dict:
    path = os.path.join(root, "resources", "profiles", "BBL.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _mo_plate_names(root: str) -> list:
    """从界面翻译表里把真实存在的板子名字捞出来（比猜枚举可靠）。"""
    i18n = os.path.join(root, "resources", "i18n")
    if not os.path.isdir(i18n):
        return []
    files = []
    for sub in os.listdir(i18n):
        folder = os.path.join(i18n, sub)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if name.lower().endswith(".mo"):
                files.append(os.path.join(folder, name))
        if len(files) >= 2:
            break
    blob = b""
    for path in files[:4]:
        try:
            with open(path, "rb") as fh:
                blob += fh.read()
        except OSError:
            continue
    if not blob:
        return []

    found = []
    for name in PLATE_CANDIDATES:
        if name.encode("utf-8") in blob:
            found.append(name)
    # 「Smooth PEI Plate / High Temp Plate」在翻译表里可能是拆开的两段
    if "Smooth PEI Plate" not in " ".join(found):
        if b"Smooth PEI Plate" in blob or b"High Temp Plate" in blob:
            if "Smooth PEI Plate / High Temp Plate" not in found:
                found.append("Smooth PEI Plate / High Temp Plate")
    if b"Engineering Plate" in blob and "Engineering Plate" not in found:
        found.append("Engineering Plate")
    if b"Cool Plate" in blob and "Cool Plate" not in found:
        found.append("Cool Plate")
    if b"Textured PEI Plate" in blob and "Textured PEI Plate" not in found:
        found.append("Textured PEI Plate")
    return found


def _machine_names(root: str) -> list:
    out = set()
    data = _read_bbl_json(root)
    for item in data.get("machine_model_list") or []:
        name = str(item.get("name", "")).strip()
        if name:
            out.add(name)
    folder = os.path.join(root, "resources", "profiles", "BBL", "machine")
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, name), "r", encoding="utf-8") as fh:
                    cfg = json.load(fh)
            except Exception:
                continue
            model = str(cfg.get("printer_model", "")).strip()
            if model:
                out.add(model)
    return sorted(out)


def _cache_stamp(root: str) -> float:
    path = os.path.join(root, "resources", "profiles", "BBL.json")
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def detect(force: bool = False, root: str = "") -> StudioEnv:
    """探测本机 Studio（带磁盘缓存）。"""
    inst = find_root(root)
    if not inst:
        return StudioEnv(found=False, notes=["没找到 Bambu Studio 安装目录，按「本机认识所有板子」处理。"])

    stamp = _cache_stamp(inst)
    cache = _cache_path()
    if cache and not force:
        try:
            with open(cache, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if raw.get("root") == inst and abs(float(raw.get("stamp", 0)) - stamp) < 1e-6:
                env = StudioEnv(**{k: v for k, v in raw.items()
                                   if k in StudioEnv.__dataclass_fields__})
                if env.found:
                    return env
        except Exception:
            pass

    data = _read_bbl_json(inst)
    env = StudioEnv(
        found=True,
        root=inst,
        version=str(data.get("version", "")).strip(),
        plates=_mo_plate_names(inst),
        machines=_machine_names(inst),
    )
    if not env.plates:
        env.plates = list(PLATE_CANDIDATES)
        env.notes.append("读不到界面翻译表，暂按「认识全部板子」处理。")

    if cache:
        try:
            payload = asdict(env)
            payload["stamp"] = stamp
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return env


# ---------------------------------------------------------------- 版本比较


def _norm_machine(model: str) -> str:
    """`Bambu Lab P2S` 和 `P2S` 认成同一个；大小写与空格不敏感。"""
    s = str(model or "").strip().lower()
    s = re.sub(r"^bambu\s*lab\s*", "", s)
    return re.sub(r"\s+", "", s)


def compare_versions(a: str, b: str) -> int:
    """把 `02.08.04.57` 这种串按数字段比较；返回 1/0/-1。"""
    def parts(text):
        return [int(x) for x in re.findall(r"\d+", str(text or ""))]

    pa, pb = parts(a), parts(b)
    if not pa or not pb:
        return 0
    width = max(len(pa), len(pb))
    pa += [0] * (width - len(pa))
    pb += [0] * (width - len(pb))
    return (pa > pb) - (pa < pb)


# ---------------------------------------------------------------- 对外小工具


def supported_plates(env: StudioEnv | None = None, allow: tuple = PLATE_CANDIDATES) -> list:
    """本机 Studio 认识的板子（保持 `allow` 的顺序）。"""
    env = env or detect()
    return [p for p in allow if env.supports_plate(p)]


def supports_plate(name: str, env: StudioEnv | None = None) -> bool:
    return (env or detect()).supports_plate(name)


def supports_machine(model: str, env: StudioEnv | None = None) -> bool:
    return (env or detect()).supports_machine(model)


def compat_report(project_settings: dict, env: StudioEnv | None = None,
                  chosen_plate: str = "") -> dict:
    """一份工程 + 本机 Studio 的兼容性小结（给界面/报告用）。"""
    env = env or detect()
    out = {
        "studio_found": env.found,
        "studio_root": env.root,
        "studio_version": env.version,
        "project_version": str(project_settings.get("version", "")),
        "project_newer": False,
        "plate": str(project_settings.get("curr_bed_type", "")),
        "plate_ok": True,
        "machine": str(project_settings.get("printer_model", "")),
        "machine_ok": True,
        "warnings": [],
    }
    if not env.found:
        out["warnings"].append("没找到本机 Bambu Studio，跳过兼容性检查。")
        return out

    pv, sv = out["project_version"], out["studio_version"]
    if pv and sv and compare_versions(pv, sv) > 0:
        out["project_newer"] = True
        out["warnings"].append(
            f"这份工程由更新的 Studio 保存（{pv}），本机是 {sv}："
            "老的 Studio 会按旧规则解释，个别参数可能显示不回来。")

    plate = chosen_plate or out["plate"]
    if plate and not env.supports_plate(plate):
        out["plate_ok"] = False
        out["warnings"].append(
            f"本机 Studio（{env.version or '未知版本'}）不认识「{plate}」这块板，"
            "导入后板子会退回它的默认板、板温也不会按这个键读。")

    if out["machine"] and not env.supports_machine(out["machine"]):
        out["machine_ok"] = False
        out["warnings"].append(
            f"本机 Studio 里没有机型「{out['machine']}」，导入后它可能按自己的机型预设重算。")
    return out
