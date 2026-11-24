"""识别层：从工程文件里推断机型、耗材、喷嘴直径

优先级：
  1. project_settings.config 的 printer_model / printer_settings_id / printer_variant
  2. slice_info.config 里的 metadata（切片过的工程更准）
  3. 规则库里的 aliases 做模糊匹配（大小写、空格、连字符都忽略）
  4. 兜底：GENERIC（保守通用），并在 UI 上给黄色警告
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .threemf import ThreeMfProject

SUPPORTED_NOZZLES = (0.2, 0.4, 0.6, 0.8)


@dataclass
class Detection:
    printer_key: str = "GENERIC"
    printer_label: str = "通用（保守）"
    printer_raw: str = ""
    printer_confident: bool = True

    filament_key: str = "GENERIC"
    filament_label: str = "通用（保守）"
    filament_raw: str = ""
    filament_confident: bool = True

    nozzle: float = 0.4
    nozzle_raw: str = ""
    nozzle_confident: bool = True

    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _first_of(raw: str | None) -> str:
    """project_settings 里多喷头/多耗材字段是 JSON 数组字符串，如 ["0.4"]。"""
    if not raw:
        return ""
    txt = str(raw).strip()
    if txt.startswith("["):
        import json
        try:
            arr = json.loads(txt)
            if arr:
                return str(arr[0])
        except (ValueError, TypeError):
            pass
        return txt.strip("[]\"' ")
    return txt


def _numeric(raw: str | None) -> float | None:
    if not raw:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


def _match_aliases(raw: str, table: dict) -> tuple[str, str] | None:
    """在规则库某一层（printers / filaments）里按 alias 长度从长到短匹配。"""
    flat = _flat(raw)
    if not flat:
        return None
    best: tuple[int, str] | None = None
    for key, node in table.items():
        for alias in node.get("aliases", []) + [key]:
            fa = _flat(alias)
            if not fa:
                continue
            if fa in flat or flat in fa:
                score = len(fa)
                if best is None or score > best[0]:
                    best = (score, key)
    if not best:
        return None
    key = best[1]
    return key, table[key].get("label", key)


def detect(project: ThreeMfProject, rules: dict) -> Detection:
    s = project.settings
    m = project.meta
    det = Detection()

    printer_raw = (s.get("printer_model")
                   or s.get("printer_settings_id")
                   or m.get("printer_model")
                   or m.get("printer_settings_id")
                   or "")
    filament_raw = (s.get("filament_type")
                    or s.get("filament_settings_id")
                    or m.get("filament_type")
                    or "")
    nozzle_raw = (s.get("nozzle_diameter")
                  or s.get("printer_variant")
                  or m.get("nozzle_diameter")
                  or "")

    det.printer_raw = str(printer_raw)
    det.filament_raw = _first_of(filament_raw)
    det.nozzle_raw = str(nozzle_raw)

    # ---------------- 机型 ----------------
    hit = _match_aliases(_first_of(printer_raw) + " " + str(s.get("printer_settings_id") or ""),
                         rules.get("printers", {}))
    if hit:
        det.printer_key, det.printer_label = hit
    else:
        det.printer_confident = False
        det.printer_key, det.printer_label = "GENERIC", "通用（保守）"
        det.warnings.append(
            f"未能识别机型（原始值：{det.printer_raw or '空'}），已切换到通用保守参数。"
            "请在「信息识别」里手动选择你的机型。"
        )

    # ---------------- 耗材 ----------------
    fhit = _match_aliases(det.filament_raw + " " + str(s.get("filament_settings_id") or ""),
                          rules.get("filaments", {}))
    if fhit:
        det.filament_key, det.filament_label = fhit
    else:
        det.filament_confident = False
        det.filament_key, det.filament_label = "GENERIC", "通用（保守）"
        det.warnings.append(
            f"未能识别耗材（原始值：{det.filament_raw or '空'}），已切换到通用保守参数。"
            "请手动选择耗材类型。"
        )

    # ---------------- 喷嘴 ----------------
    nz = _numeric(_first_of(nozzle_raw))
    if nz is None:
        det.nozzle_confident = False
        det.nozzle = 0.4
        det.warnings.append("工程里没有读到喷嘴直径，按 0.4 mm 处理，请手动确认。")
    else:
        det.nozzle = nz
        if not any(abs(nz - v) < 0.001 for v in SUPPORTED_NOZZLES):
            det.nozzle_confident = False
            det.warnings.append(
                f"喷嘴直径 {nz} mm 不在内置范围（0.2/0.4/0.6/0.8），已按最接近的规格计算。"
            )

    # ---------------- 补充信息 ----------------
    if project.is_sliced:
        det.notes.append("该工程此前已经切片过，输出时会丢弃旧的切片结果（slice_info / gcode），"
                         "避免 Bambu Studio 显示过期时长。")
    multi_nozzle = s.get("nozzle_diameter", "").count(",") > 0
    if multi_nozzle:
        det.notes.append("检测到多喷嘴工程，本版只按第一个喷嘴直径优化。")
    if s.get("filament_type", "").strip().startswith("[") and s["filament_type"].count(',') > 0:
        det.notes.append("检测到多耗材工程，参数按第一种耗材计算（擦料塔参数会一并优化）。")
    return det


def apply_overrides(det: Detection, rules: dict, *,
                    printer_key: str | None = None,
                    filament_key: str | None = None,
                    nozzle: float | None = None) -> Detection:
    """用户在 UI 上手动修正识别结果。"""
    out = Detection(
        printer_key=det.printer_key, printer_label=det.printer_label, printer_raw=det.printer_raw,
        printer_confident=det.printer_confident,
        filament_key=det.filament_key, filament_label=det.filament_label,
        filament_raw=det.filament_raw, filament_confident=det.filament_confident,
        nozzle=det.nozzle, nozzle_raw=det.nozzle_raw, nozzle_confident=det.nozzle_confident,
        warnings=list(det.warnings), notes=list(det.notes),
    )
    if printer_key:
        node = rules.get("printers", {}).get(printer_key)
        if node:
            out.printer_key = printer_key
            out.printer_label = node.get("label", printer_key)
            out.printer_confident = True
            out.warnings = [w for w in out.warnings if "机型" not in w]
    if filament_key:
        node = rules.get("filaments", {}).get(filament_key)
        if node:
            out.filament_key = filament_key
            out.filament_label = node.get("label", filament_key)
            out.filament_confident = True
            out.warnings = [w for w in out.warnings if "耗材" not in w]
    if nozzle:
        out.nozzle = float(nozzle)
        out.nozzle_confident = True
        out.warnings = [w for w in out.warnings if "喷嘴" not in w]
    return out
