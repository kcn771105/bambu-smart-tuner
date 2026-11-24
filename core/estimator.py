"""打印时长估算（相对指数模型）

没有几何数据就无法算真实时长，这里用「相对时间指数」：同一套参数体系下
指数之比 ≈ 时长之比，所以只在「原参数 vs 新参数」之间比较，给出百分比变化。

模型结构（按 20×20×20 mm 参考件标定，只用于同体系内的相对比较）
----------------------------------------------------------------------
层数            N = 参考高度 / 层高
每层耗时        外墙路径 + 内墙路径 + 填充路径 + 空走 + 换层固定开销
顶底实心层      只在顶部和底部各几层，总路径与层高无关 → 单独算（不随层高缩放）
首层额外时间    第一层用首层速度挤出，比正常速度多花的那点时间（约等于一层，
                随层高线性缩放）
加速度修正      加速度越低、加减速越频繁，整体越慢（乘性修正）

关键点
------
1. 墙层/填充路径都乘以层数，所以「层高减半 → 层数翻倍 → 墙与空走时间翻倍」。
   实测敏感度（相对 20×20×20 参考件）：
       层高 0.2 → 0.1        ≈ +74%
       外墙圈数 +1           ≈ +19%
       外壁速度减半          ≈ +27%
       填充密度 15% → 30%    ≈ +6%
       顶底层 4 → 6 层       ≈ +5%
       默认加速度 10000→5000 ≈ +5%
       全部速度翻倍          ≈ −44%
   这些量级来自「路径量 / 速度 × 层数」的真实物理关系，不是拍脑袋。
2. 首层慢速只贡献大约一层的额外时间（占比 1~3%），不再像旧版那样用一个
   与层数无关的大常数把参数敏感度全部稀释掉。
3. PER_LAYER_OVERHEAD 与每层的墙/空走耗时同量级，不再大一个数量级。

常量来自 Bambu 社区常用经验值与官方预设的比例关系，属于经验标定，
不需要精确，只需要方向正确、量级合理。
"""

from __future__ import annotations

from dataclasses import dataclass

# ---- 参考件几何（20×20×20 mm 立方体），用于把「路径量」换算成时间 ----
REF_HEIGHT = 20.0          # mm
REF_AREA = 400.0           # mm²（底面积）
REF_PERIM = 80.0           # mm（底面周长）

# ---- 墙层 ----
WALL_SHARE_OUTER = 0.62    # 外墙占墙层路径的比例
WALL_SHARE_INNER = 0.38    # 内墙占墙层路径的比例

# ---- 顶底实心层 ----
# 每个实心层要铺满整个底面积，路径 = 面积 / 线宽
# （与层高无关：顶底就那么几层）

# ---- 每层固定开销 ----
TRAVEL_PER_LAYER = 250.0   # mm，每层的空走距离（多次往返的合计）
PER_LAYER_OVERHEAD = 0.15  # 秒/层，换层 + 回抽 + 加减速的固定开销

# ---- 加速度修正 ----
ACCEL_REF = 2500.0         # 参考加速度 mm/s²
ACCEL_WEIGHT = 0.20        # 加速度项权重（加速度减半 ≈ +5%）

DEFAULT_LINE_WIDTH = 0.42  # mm


@dataclass
class TimeEstimate:
    old_index: float
    new_index: float
    delta_pct: float
    text: str


def _f(p: dict, key: str, default: float) -> float:
    v = p.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def index(params: dict, *, flow_limit: float | None = None) -> float:
    """算出一组参数的相对时间指数（越大越慢）。

    flow_limit：热端体积流量上限（mm³/s）。给了就按「实际能跑多快」算：
    挤出速度受 流量 ÷ (层高 × 线宽) 限制，写 300 mm/s 但物理上只能跑 200 时，
    旧参数组和新参数组都按 200 算 —— 否则「原参数」里那个跑不到的速度
    会变成永不可能达到的基准，把所有优化都算成大幅变慢。
    """
    lh = max(_f(params, "layer_height", 0.2), 0.02)
    wall = max(_f(params, "wall_loops", 2), 0)
    dens = max(_f(params, "sparse_infill_density", 15), 0)
    shells = _f(params, "top_shell_layers", 4) + _f(params, "bottom_shell_layers", 3)

    v_out = max(_f(params, "outer_wall_speed", 200), 5)
    v_in = max(_f(params, "inner_wall_speed", 300), 5)
    v_inf = max(_f(params, "sparse_infill_speed", 270), 5)
    v_top = max(_f(params, "top_surface_speed", 200), 5)
    v_trv = max(_f(params, "travel_speed", 500), 10)
    v_init = max(_f(params, "initial_layer_speed", 50), 5)
    accel = max(_f(params, "default_acceleration", 10000), 300)
    lw = max(_f(params, "line_width", DEFAULT_LINE_WIDTH), 0.05)

    # ---- 体积流量约束下的「实际挤出速度上限」
    if flow_limit and flow_limit > 0:
        cei = flow_limit / max(lh * lw, 1e-9)      # 最高挤出线速度 mm/s
        v_out = min(v_out, max(cei * 0.55, 10))    # 外墙实际常低于上限（降速求表面）
        v_in = min(v_in, cei)
        v_inf = min(v_inf, cei)
        v_top = min(v_top, max(cei * 0.8, 10))
        v_init = min(v_init, max(cei * 0.7, 8))

    n_layers = REF_HEIGHT / lh

    # ---- 每层路径（mm / 层）
    wall_path = wall * REF_PERIM                    # 每圈一圈周长
    infill_path = dens / 100.0 * REF_AREA * lh / lw  # 每层填充的线总长

    # ---- 每层时间（秒）
    wall_time = wall_path * (WALL_SHARE_OUTER / v_out + WALL_SHARE_INNER / v_in)
    infill_time = infill_path / v_inf
    travel_time = TRAVEL_PER_LAYER / v_trv
    per_layer = wall_time + infill_time + travel_time + PER_LAYER_OVERHEAD

    # ---- 顶底实心层：总路径与层高无关（顶底就那么几层）
    solid_time = shells * REF_AREA / lw / v_top

    # ---- 首层：慢速多花的时间（约一层，随层高缩放）
    init_slow = (wall_path + infill_path) / v_init
    init_normal = wall_time + infill_time
    init_extra = max(init_slow - init_normal, 0.0)

    t = n_layers * per_layer + solid_time + init_extra
    t *= 1.0 + (ACCEL_REF / accel) * ACCEL_WEIGHT   # 加速度越低越慢
    return t


def compare(old: dict, new: dict, *, flow_limit: float | None = None) -> TimeEstimate:
    a = index(old, flow_limit=flow_limit)
    b = index(new, flow_limit=flow_limit)
    delta = (b - a) / a * 100.0 if a > 0 else 0.0
    if abs(delta) < 1.0:
        text = "基本持平（±1% 内）"
    elif delta > 0:
        text = f"约 +{delta:.0f}%（±5%，仅相对估算）"
    else:
        text = f"约 {delta:.0f}%（±5%，仅相对估算）"
    return TimeEstimate(old_index=a, new_index=b, delta_pct=delta, text=text)
