"""「其他」页里的特殊模式：一律由用户自己选，软件不替你开/关。

原则（对应反馈「其他里面的特殊模式让用户自行选择」）：

    * 每一项默认「跟随工程」，即一个字节都不改；
    * 只有你点了某个值，才把那一项写进去，并在结论卡/日志里说明；
    * 这里不做任何「我觉得你应该开」的推断 —— 特殊模式影响的是切片器的
      整体行为（逐件打印会改机器动作顺序、螺旋花瓶只适合单壁花瓶、
      磨砂皮肤是外观特效），猜错一次就是废件。

选项表在规则库 `special` 节点里，这里只负责读表、校验、生成 ops。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 兜底表：规则库缺 special 节点时也能用（与原厂默认一致）
_FALLBACK: list[dict] = [
    {"key": "print_sequence", "label": "打印顺序", "kind": "enum",
     "choices": [("by layer", "逐层打（默认）"), ("by object", "逐件打（一次打完一个）")],
     "help": "逐件打时喷嘴会跳动避让，一个件打坏不影响其他件；但件与件之间要留间隙。"},
    {"key": "spiral_mode", "label": "螺旋花瓶模式", "kind": "bool",
     "choices": [("1", "开启"), ("0", "关闭")],
     "help": "只适合单壁、无顶的容器（花瓶/灯罩）；开了以后壁厚只有一圈，不能有填充。"},
    {"key": "spiral_mode_smooth", "label": "螺旋平滑", "kind": "bool",
     "choices": [("1", "开启"), ("0", "关闭")],
     "help": "螺旋模式下把 Z 抬升抹匀，表面更顺；只在螺旋花瓶模式下有效。"},
    {"key": "enable_arc_fitting", "label": "圆弧拟合（G2/G3）", "kind": "bool",
     "choices": [("1", "开启"), ("0", "关闭")],
     "help": "把圆弧压成 G2/G3 指令，圆孔更圆、文件更小；老固件不认时关掉。"},
    {"key": "fuzzy_skin", "label": "磨砂皮肤", "kind": "enum",
     "choices": [("none", "不磨砂（默认）"), ("external", "只磨外表面"),
                 ("all", "磨所有表面"), ("all_shells", "磨所有外壳")],
     "help": "给外表面加粗糙质感，能遮住层纹；会让尺寸微微变大。"},
    {"key": "avoid_crossing_wall_includes_support", "label": "避墙时也避支撑", "kind": "bool",
     "choices": [("1", "开启"), ("0", "关闭")],
     "help": "空驶时不穿过支撑，支撑面更干净；会多一点空驶时间。"},
    {"key": "only_one_wall_top", "label": "顶面只打一圈墙", "kind": "bool",
     "choices": [("1", "开启"), ("0", "关闭")],
     "help": "顶面用填充直接盖住，省时间；顶面质量会差一点。"},
    {"key": "wall_sequence", "label": "墙打印顺序", "kind": "enum",
     "choices": [("inner wall/outer wall", "先内后外（表面好）"),
                 ("outer wall/inner wall", "先外后内"), ("inner-outer-inner wall", "内外内")],
     "help": "先内后外时外壁靠内壁支撑，表面更平整（默认）。"},
]

KEEP = "keep"


@dataclass
class SpecialPlan:
    ops: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    picked: int = 0


def options(rules: dict | None = None) -> list[dict]:
    node = (rules or {}).get("special")
    if isinstance(node, list) and node:
        out = []
        for item in node:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            choices = []
            for pair in item.get("choices") or []:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    choices.append((str(pair[0]), str(pair[1])))
            if not choices:
                continue
            out.append({"key": item["key"], "label": item.get("label", item["key"]),
                        "kind": item.get("kind", "enum"), "choices": choices,
                        "help": item.get("help", "")})
        if out:
            return out
    return [dict(x) for x in _FALLBACK]


def truthy(value) -> bool:
    """`1` / `"1"` / `"true"` / `"开"` / `True` 都算开。"""
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    return text in ("1", "true", "on", "yes", "开", "开启", "是")


def _norm(kind: str, value) -> tuple[bool, object]:
    """把界面上拿到的字符串转成要写进工程的值。返回 (是否合法, 值)。"""
    txt = str(value).strip()
    if kind == "bool":
        if txt in ("1", "true", "True", "开", "开启"):
            return True, True
        if txt in ("0", "false", "False", "关", "关闭"):
            return True, False
        return False, None
    return True, txt


def plan(selections: dict | None, rules: dict | None = None) -> SpecialPlan:
    """`selections` 是 {key: 值}，值等于 "keep"/空 表示这一项不动。"""
    out = SpecialPlan()
    if not selections:
        return out
    table = {item["key"]: item for item in options(rules)}
    for key, value in selections.items():
        item = table.get(key)
        if item is None:
            continue
        if value is None or str(value).strip() in ("", KEEP, "None"):
            continue
        ok, val = _norm(item["kind"], value)
        if not ok:
            out.notes.append(f"特殊模式「{item['label']}」的取值「{value}」认不出来，已跳过。")
            continue
        out.ops[key] = val
        out.picked += 1
        shown = dict(item["choices"]).get(str(value).strip(), str(val))
        out.rows.append({
            "metric": f"特殊模式 · {item['label']}", "measured": "你手动选择",
            "formula": f"{key} = {val}", "conclusion": shown,
        })
        out.notes.append(f"特殊模式「{item['label']}」按你的选择设为「{shown}」。")
    return out
