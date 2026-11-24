"""这个参数在 Bambu Studio 工艺面板的哪个位置、叫什么 —— 用于「改了我找不到」的定位。

数据来自 data/studio_ui.json（由 tools/gen_studio_ui.py 生成）：
- 官方 zh_CN 词条自动匹配出来的 中文名/英文名；
- 手工对照表补的页签/分组/叫法；
- 明确标 hidden 的（Studio 界面上没有这个开关，只能改文件）。

用法：
    from core.studio_ui import where, search_hint
    where("wall_loops")        -> "强度 › 墙层数"
    search_hint("wall_loops")  -> "墙层数（Wall loops）"
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from functools import lru_cache

_DATA_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "studio_ui.json"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "studio_ui.json"),
    os.path.join("data", "studio_ui.json"),
)

# 静态兜底：JSON 丢了也要能给出页签（按 schema 分组猜），不至于整列空白
_GROUP_TAB = {
    "quality": "质量", "wall": "强度", "infill": "强度", "seam": "质量",
    "ironing": "质量", "speed": "速度", "accel": "速度", "support": "支撑",
    "tower": "多材料", "adhesion": "多材料", "z": "其他", "cooling": "其他",
}


@dataclass(frozen=True)
class UiSpot:
    key: str
    label: str          # 我们界面上的中文名
    tab: str            # Studio 页签：质量/强度/速度/支撑/多材料/其他
    group: str          # 页签里的分组
    studio_zh: str      # Studio 里的中文名（可能空）
    studio_en: str      # Studio 里的英文名（可能空）
    hidden: bool        # True = Studio 界面没有这个开关
    note: str

    @property
    def path(self) -> str:
        if self.hidden:
            return f"Studio 界面没有（含开发者模式）：{self.note or '只能改文件'}"
        if self.group:
            return f"{self.tab} › {self.group}"
        return self.tab

    @property
    def search_hint(self) -> str:
        """粘进 Studio 搜索框就能跳到这条设置的词。"""
        if self.hidden:
            return ""
        if self.studio_zh and self.studio_en:
            return f"{self.studio_zh}（{self.studio_en}）"
        if self.studio_zh:
            return self.studio_zh
        if self.studio_en:
            return self.studio_en
        return self.key.replace("_", " ")

    def line(self) -> str:
        """一行说明，给日志/报告用。"""
        if self.hidden:
            return f"{self.label}：{self.path}"
        return f"{self.label}：{self.path}" + (f"（Studio 里搜「{self.search_hint}」）" if self.search_hint else "")


def _load() -> dict:
    for p in _DATA_CANDIDATES:
        try:
            if os.path.exists(p):
                with io.open(p, encoding="utf-8-sig") as f:
                    return json.load(f).get("items", {})
        except Exception:
            continue
    return {}


_ITEMS = _load()


@lru_cache(maxsize=2048)
def info(key: str, *, fallback_label: str = "", group: str = "") -> UiSpot:
    rec = _ITEMS.get(key) or {}
    return UiSpot(
        key=key,
        label=rec.get("label") or fallback_label or key,
        tab=rec.get("tab") or _GROUP_TAB.get(group or "", "其他"),
        group=rec.get("group") or "",
        studio_zh=rec.get("studio_zh") or "",
        studio_en=rec.get("studio_en") or "",
        hidden=bool(rec.get("hidden")),
        note=rec.get("note") or "",
    )


def where(key: str, *, fallback_label: str = "", group: str = "") -> str:
    return info(key, fallback_label=fallback_label, group=group).path


def search_hint(key: str, *, fallback_label: str = "", group: str = "") -> str:
    return info(key, fallback_label=fallback_label, group=group).search_hint


def available() -> int:
    """有多少条有数据（自检/测试用）。"""
    return len(_ITEMS)
