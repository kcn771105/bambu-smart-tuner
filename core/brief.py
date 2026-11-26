"""结论卡：三句话说清「这次会变成什么样」。

用户反馈（第 1 条）：「那个说明能总结简洁点更好，太多参数值看不太懂，
最想知道这样调整后的结果」。

所以这里不列参数值，只回答四个问题：

    1. 会快还是会慢？—— 预估时长变化 + 主要靠什么换来的
    2. 打印出来会更好吗？—— 表面 / 强度 / 附着 各一句
    3. 热床和风扇给到多少？—— 一句话（含室温修正）
    4. 有什么风险要你亲自看一眼？—— 最多两条警告

调用方把 `build()` 的返回直接贴到界面的结论框与报告开头，
不需要再读一遍参数表。
"""

from __future__ import annotations

from typing import Any

__all__ = ["build", "hotspots", "source_split"]

#: 按「用户能感知到什么」分组，而不是按参数表分组
_IMPACT = {
    "quality": "外观（层纹/顶面/接缝）",
    "wall": "外观强度（墙与壳）",
    "infill": "用料与内强度",
    "speed": "打印速度",
    "accel": "打印速度（加速度）",
    "cooling": "散热与翘边",
    "seam": "接缝可见度",
    "support": "支撑好不好拆",
    "adhesion": "首层附着",
    "thermal": "热床温度",
    "ironing": "顶面平整",
    "z": "Z 轴与补偿",
    "retraction": "拉丝",
    "tower": "擦料塔",
    "flow": "流量标定",
}


def hotspots(result, limit: int = 4) -> list[tuple[str, int]]:
    """改动最集中的几个「用户能感知的方面」：(方面, 改动条数)。"""
    counts: dict[str, int] = {}
    for row in getattr(result, "rows", []) or []:
        if not (row.changed and row.will_write):
            continue
        label = _IMPACT.get(row.group, row.group_label)
        counts[label] = counts.get(label, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


#: 「这次改的值到底是谁定的」三类。用户第 3 条反馈在质疑「是按模型算的还是套预设」，
#: 这里如实给比例：实测层只决定「触发哪条规则 + 系数」，基准值仍来自规则表。
_MEASURED_HINTS = ("热床", "接缝", "支撑", "几何", "形状", "裙边", "实测", "推导", "时长上限",
                   "流量", "压强", "壁厚", "跨层")
_TABLE_HINTS = ("模式", "耗材基线", "交叉规则", "打印板", "机型", "熨烫", "回抽")
_CLAMP_HINTS = ("钳制", "夹到", "上限", "下限", "合法范围")


def source_split(result) -> dict[str, int]:
    """把本次写入按「依据」分成三桶，返回 {按模型实测, 预设基准表, 安全钳制, 保持原值}。"""
    out = {"按模型实测": 0, "预设基准表": 0, "安全钳制": 0, "保持原值": 0}
    for key in (getattr(result, "write_values", {}) or {}):
        why = str((getattr(result, "sources", {}) or {}).get(key, ""))
        if not why:
            out["保持原值"] += 1
        elif any(h in why for h in _CLAMP_HINTS):
            out["安全钳制"] += 1
        elif any(h in why for h in _MEASURED_HINTS):
            out["按模型实测"] += 1
        elif any(h in why for h in _TABLE_HINTS):
            out["预设基准表"] += 1
        elif "保持工程原值" in why:
            out["保持原值"] += 1
        else:
            out["预设基准表"] += 1
    return out


def _source_sentence(result) -> str:
    sp = source_split(result)
    total = sum(sp.values())
    if not total:
        return ""
    bits = [f"{k} {v}" for k, v in sp.items() if v]
    return (f"改动依据（共 {total} 项）：" + " / ".join(bits)
            + "（实测=逐层量出的悬垂、细高比、圆度、体积、板温室温；预设只给起点值）")


def _time_sentence(result) -> str:
    t = getattr(result, "time", None)
    d = float(getattr(t, "delta_pct", 0.0) or 0.0)
    if abs(d) < 1.0:
        return "打印时长基本不变"
    if d < 0:
        return f"打印时长约缩短 {-d:.0f}%（换来的是速度/层高上的取舍）"
    return f"打印时长约增加 {d:.0f}%（换来的是表面与强度）"


def _surface_sentence(result) -> str:
    mode = str(getattr(result, "mode_key", "") or "")
    changed = {r.key for r in (getattr(result, "rows", []) or []) if r.changed and r.will_write}
    bits: list[str] = []
    if "layer_height" in changed:
        vals = [r for r in result.rows if r.key == "layer_height"]
        if vals:
            bits.append(f"层高 {vals[0].old_display} → {vals[0].new_display}")
    if mode in ("quality", "fine", "ultrafine"):
        bits.append("表面优先：降速 + 小层高")
    elif mode == "draft":
        bits.append("草稿：以时间为主，表面会有台阶感")
    elif mode == "strength":
        bits.append("强度优先：加墙加壳，外观不是重点")
    else:
        bits.append("均衡：外观与时间折中")
    return "；".join(bits)


def _clip(text: str, limit: int) -> str:
    """结论卡只有一行的高度，长句截到句号/分号处，别把整段说明塞进去。"""
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    cut = max(text.rfind("；", 0, limit), text.rfind("，", 0, limit), text.rfind("。", 0, limit))
    if cut >= limit // 2:
        return text[:cut] + "…"
    return text[:limit].rstrip() + "…"


def _speed_sentence(result) -> str:
    """速度净变化：把「降了多少、为什么降」说清楚。

    用户反馈「打一个盒子降速严重」——降是有原因的（模式取舍 / 体积流量上限 /
    首层附着），但不能让人自己去参数表里猜，所以这里直接列三个关键速度。
    """
    wanted = ("outer_wall_speed", "inner_wall_speed", "sparse_infill_speed",
              "initial_layer_speed")
    labels = {"outer_wall_speed": "外壁", "inner_wall_speed": "内壁",
              "sparse_infill_speed": "填充", "initial_layer_speed": "首层"}
    bits: list[str] = []
    flow_hit = False
    for row in getattr(result, "rows", []) or []:
        if row.key not in wanted or not (row.changed and row.will_write):
            continue
        bits.append(f"{labels[row.key]} {row.old_display}→{row.new_display}")
        if "体积流量" in str(row.reason):
            flow_hit = True
    if not bits:
        return ""
    cap = getattr(result, "flow_limit", None)
    tail = ""
    if flow_hit and cap:
        tail = f"（内壁/填充被体积流量上限 {cap:.0f} mm³/s 压着，想更快就换高流量热端或降层高）"
    return "速度：" + "，".join(bits) + tail + "。"


def _adhesion_sentence(result) -> str:
    changed = {r.key: r for r in (getattr(result, "rows", []) or []) if r.changed and r.will_write}
    keys = [k for k in ("brim_width", "brim_type", "initial_layer_speed", "elefant_foot_compensation") if k in changed]
    if not keys:
        return ""
    labels = [changed[k].label for k in keys]
    return "附着加强：" + "、".join(labels)


def build(result, *, thermal_rows: list[dict] | None = None,
          machine_note: str = "", support_ease: str = "standard") -> list[str]:
    """返回 3~6 行结论（每行都是给人看的一句话，不含参数键名）。"""
    out: list[str] = []
    changed = getattr(result, "changed_count", 0)
    out.append(
        f"结论：{result.mode_label} · {_time_sentence(result)} · 共改动 {changed} 项参数。")

    # 「改得最多的方面」不再单独占一行：它和下面的「改动依据」说的是一件事，
    # 而结论卡只有固定高度，宁可把位置留给「为什么改」。
    hs = hotspots(result)
    src = _source_sentence(result)
    if src:
        out.append(src)
    out.append("表面：" + _surface_sentence(result))
    sp = _speed_sentence(result)
    if sp:
        out.append(sp)
    # 模型判定：让用户看到「为什么这次这么调」——同一套规则换个件就不一样
    for n in (getattr(result, "notes", []) or []):
        txt = str(n)
        if txt.startswith("形状识别："):
            out.append("模型判定：" + _clip(txt[len("形状识别："):], 44))
            break

    ad = _adhesion_sentence(result)
    if ad:
        out.append(ad)

    # 热床与风扇（用户第 2 条反馈最关心的就是这一句）
    if thermal_rows:
        by_metric = {str(r.get("metric", "")): r for r in thermal_rows}
        bed = [v for k, v in by_metric.items() if "温度" in k and "首层" not in k]
        fan = [v for k, v in by_metric.items() if "风扇" in k]
        bits = []
        if bed:
            bits.append("热床 " + "；".join(f"{r.get('conclusion', '')}" for r in bed))
        if fan:
            fan_txt = "；".join(f"{r.get('conclusion', '')}" for r in fan)
            # 室温那句单独给过了，行里不再重复一遍
            fan_txt = fan_txt.split("，室温")[0]
            bits.append(fan_txt if fan_txt.startswith("风扇") else "风扇 " + fan_txt)
        room = getattr(result, "room_note", "") or ""
        if bits:
            line = " · ".join(bits)
            if room:
                line += "（" + room.replace("（冷天容易翘边，这两项就是治它的）", "") + "）"
            out.append(_clip(line, 190) + "。")

    if support_ease and support_ease != "standard":
        out.append({
            "easy": "支撑：按「好拆」调过——分离间隙加大、接触面变薄，拆的时候更省力（接触面会有细微纹路）。",
            "max": "支撑：按「极好拆」调过——间隙最大、接触面最少，几乎一掰就掉（接触面痕迹会明显一点）。",
        }.get(support_ease, ""))

    if machine_note:
        out.append(machine_note)

    warns = [w for w in (getattr(result, "warnings", []) or []) if w]
    if warns:
        out.append("要你看一眼：" + _clip(warns[0], 120))
        # 第二条警告不再占一行：点开日志/报告都看得到，卡片高度优先留给结论
    return [line for line in out if line]
