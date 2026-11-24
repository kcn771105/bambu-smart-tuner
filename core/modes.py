"""优化模式注册表（新增模式只改这里 + 规则库，不用动主流程）

模式一共两处定义，这里是「代码侧」的那份：

    1. rules/BambuRules.json 的 modes 节点 —— 每个模式的标签、说明与参数动作
    2. 本模块 —— 模式之间的「族」关系与界面排序

为什么要族
----------
新增模式（快速草稿 / 精细 / 超精细）本质上还是从老三档演化来的：

    · 精细、超精细 ≈ 表面质量优先那一族（都追求外观与层间结合）
    · 快速草稿 ≈ 均衡模式那一族（不追求极限，只追求快）

有了「族」，规则库里的交叉规则（例如质量档的「悬垂全塌区降速」）
就能只写一次，新模式自动继承，不需要把同一条规则复制三遍。

命名口径（与文档、界面保持一致）
--------------------------------
    strength   强度优先
    quality    表面质量优先
    balanced   均衡模式
    draft      快速草稿
    fine       精细
    ultrafine  超精细
"""

from __future__ import annotations


# ------------------------------------------------------------------ 模式族

#: 模式 → 族。同族的模式在支撑策略、几何层上共享同一套取舍。
MODE_FAMILY: dict[str, str] = {
    "balanced": "balanced",
    "strength": "strength",
    "quality": "quality",
    "draft": "draft",
    "fine": "precision",
    "ultrafine": "precision",
}

#: 交叉规则里 when.mode 写某个「族名」时，实际命中的模式集合。
#: 例：when={"mode": "quality"} 命中 quality / fine / ultrafine 三档。
MODE_GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "quality": ("quality", "fine", "ultrafine"),
    "precision": ("fine", "ultrafine"),
    "balanced": ("balanced", "draft"),
    "draft": ("draft",),
    "strength": ("strength",),
}

#: 界面上的显示顺序（规则库里 modes 节点的书写顺序不决定这个）。
MODE_UI_ORDER: tuple[str, ...] = (
    "strength", "quality", "balanced", "draft", "fine", "ultrafine",
)

#: 界面提示文案（规则库 modes.*.desc 优先，这里是兜底）。
MODE_HINT: dict[str, str] = {
    "strength": "加厚墙体 / 提高填充密度与重叠 / 降低外壁速度，换力学强度，允许更慢。",
    "quality": "更小层高 / 降外壁速度 / 精细加速度与 Z 对齐，压振纹与层纹，外观优先。",
    "balanced": "强度与外观折中，填充与速度只做小幅调整，打印时长基本不变。",
    "draft": "层高放大到 0.24 mm、内壁与填充提速、支撑判定放宽到 35°，只求快出件。",
    "fine": "层高压到 0.12 mm、内壁与填充提速、悬垂降速、支撑判定收紧到 20°。",
    "ultrafine": "层高压到 0.08 mm、顶底壳层加厚、支撑判定收紧到 15°，外观拉满。",
}

#: 形状原型档的兜底：某个模式在 shape_profiles 里没有专属节点时用哪一档。
#: 精细/超精细继承质量档（都在意外观）；快速草稿继承均衡档（不折腾强度）。
MODE_BASE_FALLBACK: dict[str, str] = {
    "draft": "balanced",
    "fine": "quality",
    "ultrafine": "quality",
}

#: 快速草稿档要丢掉的形状建议：加厚墙层 / 提高密度 / 加壳层的项一律不适用
#:（草稿的目标是快，这些项只会让时间变长）。
DRAFT_DROP_KEYS: frozenset[str] = frozenset({
    "wall_loops", "top_shell_layers", "bottom_shell_layers",
    "sparse_infill_density", "skeleton_infill_density", "skin_infill_density",
    "infill_wall_overlap", "top_surface_density", "bottom_surface_density",
    "top_shell_thickness", "bottom_shell_thickness", "minimum_sparse_infill_area",
    "top_bottom_infill_wall_overlap",
})


def family(mode: str) -> str:
    """模式 → 族（未知模式按均衡处理）。"""
    return MODE_FAMILY.get(mode, "balanced")


def group_members(name: str) -> tuple[str, ...]:
    """when.mode 里写的名字 → 实际命中的模式集合。"""
    if name in MODE_GROUP_MEMBERS:
        return MODE_GROUP_MEMBERS[name]
    return (name,)


def ui_order(keys) -> list[str]:
    """按界面顺序排列模式键（规则库里没写的模式排最后，按字母）。"""
    keys = list(keys)
    known = [k for k in MODE_UI_ORDER if k in keys]
    rest = sorted(k for k in keys if k not in MODE_UI_ORDER)
    return known + rest


def hint(mode: str, fallback: str = "") -> str:
    return MODE_HINT.get(mode, fallback)
