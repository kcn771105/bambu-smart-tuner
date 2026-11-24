"""交替额外墙层（alternate_extra_wall）与「确保垂直外壳厚度」「墙层数」的一致性。

Bambu Studio 打开工程时会做这组检查，弹出：

    为使交替额外墙层正常工作，建议进行以下调整：
    - 将确保垂直外壳厚度设为「部分」（partial）
    - 将墙层数设为 2

也就是说，Studio 认为这三个键必须成套出现：
    alternate_extra_wall = 1
    ensure_vertical_shell_thickness = partial
    wall_loops = 2

我们自己把墙层数从 2 提到 4~6（强度档、细高件）时会撞上第一条，
在用户打开工程时被 Studio 拦一次。这个模块负责把这一对参数收干净：
"""

from __future__ import annotations

from typing import Any

TRUE_TOKENS = {"1", "true", "True", "yes", "on"}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip() in TRUE_TOKENS or str(v).strip().lower() == "true"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if isinstance(v, (list, tuple)):
            v = v[0] if v else default
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def check(values: dict[str, Any], *, project: dict[str, Any] | None = None) -> tuple[dict, list[str], list[str]]:
    """返回 (ops, warnings, notes)。

    规则来源是 Studio 自己的提示文案（2.x）：
    · 交替额外墙要求「墙层数 = 2」且「确保垂直外壳厚度 = 部分」；
    · 我们调高墙层数时，交替额外墙在多层墙下几乎没有增量，留着只会让 Studio 反复提示。
    """
    proj = project or {}
    ops: dict[str, Any] = {}
    warns: list[str] = []
    notes: list[str] = []

    ae_raw = proj.get("alternate_extra_wall", values.get("alternate_extra_wall"))
    if not _truthy(ae_raw):
        return ops, warns, notes

    # 以本次要写出的墙层数为准（模式层/几何层已经定好了），没有就用工程值
    wall_raw = values.get("wall_loops", proj.get("wall_loops"))
    wall = _num(wall_raw, 2.0)
    shell_raw = values.get("ensure_vertical_shell_thickness", proj.get("ensure_vertical_shell_thickness"))
    shell = str(shell_raw or "").strip().lower()

    if wall > 2.0:
        ops["alternate_extra_wall"] = {"set": False}
        warns.append(
            "交替额外墙层与墙层数冲突：工程里开着「交替额外墙层」，而本档把墙层数从 2 提到了 "
            f"{wall:g} 圈。Bambu Studio 对这对参数有一致性要求（交替额外墙要求墙层数 = 2、"
            "确保垂直外壳厚度 = 部分），保留它会在打开工程时弹提示。多层墙本身已经提供外壳强度，"
            "交替额外墙在 4 圈以上增量很小，所以这里把它关掉。"
            "想保留这个功能就改用均衡档（不动墙层数）。"
        )
        notes.append("交替额外墙层：已关闭（与墙层数冲突，见警告）。")
        return ops, warns, notes

    # 墙层数仍是 2，那就把 Studio 要求的另一半补齐，避免它弹窗
    if shell != "partial":
        ops["ensure_vertical_shell_thickness"] = {"set": "partial"}
        notes.append(
            "工程开着「交替额外墙层」且墙层数保持 2 圈，已把「确保垂直外壳厚度」设为「部分」——"
            "这是 Studio 对这对参数的要求，避免打开工程时弹一致性提示。"
        )
    else:
        notes.append("工程开着「交替额外墙层」，墙层数与垂直外壳厚度的组合已满足 Studio 的要求。")
    return ops, warns, notes
