"""支撑策略：由模型几何决定支撑怎么打

用户的原话：「支撑根据模型调」。

为什么单独一个模块
------------------
支撑是**唯一一组真正依赖几何**的工艺参数。别的参数（速度、加速度、密度）
主要是「机器 + 耗材」决定，支撑则完全看模型长什么样：

    · 悬垂面占比多少 → 要不要支撑、支撑多少
    · 悬垂角度分布   → 支撑触发阈值定多少度
    · 模型有多高      → 支撑层数、树状分支要多少
    · 支撑面朝向      → 支撑接口（贴面）要贴多牢
    · 模型是否已经贴板 → 只在板上生成还是全程生成

所以这里从**几何量**出发推导支撑参数，而不是从「原型标签」硬编码。
每个原型也会带一点修饰（见 shape_rules.BUILTIN_PROFILES），
但主决策在这里。

输出的都是切片工艺页的键：
    enable_support                  要不要支撑
    support_type                    支撑类型（tree(auto) / normal(auto) …）
    support_style                   支撑样式
    support_threshold_angle         悬垂判定阈值（度）
    support_base_pattern_spacing    支撑底纹间距（越小越密）
    support_base_pattern            支撑底纹图案
    support_interface_pattern       支撑贴面图案
    support_interface_spacing       贴面间距（越小越贴牢）
    support_interface_top_layers    贴面顶层层数
    support_top_z_distance          支撑顶面与模型间隙
    support_bottom_z_distance       支撑底面与模型间隙
    support_object_xy_distance      支撑与模型水平间隙
    support_expansion               支撑膨胀（X/Y）
    support_critical_regions_only   只生成关键区域支撑
    support_remove_small_overhang   忽略小悬垂
    support_on_build_plate_only     只在打印平台生成支撑
    tree_support_branch_angle       树状支撑分支角度
    tree_support_branch_diameter    树状支撑分支直径
    tree_support_branch_distance    树状支撑分支间距
    tree_support_wall_count         树状支撑壁数
    support_critical_regions_only …
"""

from __future__ import annotations

from dataclasses import dataclass

from . import modes as mode_registry
from . import model_analysis


# ------------------------------------------------------------------ 阈值表

#: 内置兜底阈值（规则库 support_policy 节点可覆盖）
BUILTIN_POLICY: dict = {
    "overhang_ratio_enabled": 0.06,     # 悬垂面占比超过这个比例就开支撑
    "overhang_ratio_critical": 0.18,    # 超过这个比例算"大悬垂"，支撑要加密
    "overhang_ratio_dense": 0.35,      # 超过这个比例支撑要很密
    "height_tall_mm": 90.0,            # 高度超过这个值支撑要更结实
    "height_very_tall_mm": 160.0,      # 超过这个值用树状支撑
    "angle_loose_deg": 45.0,           # 松阈值：模型基本垂直也能支撑
    "angle_normal_deg": 40.0,
    "angle_tight_deg": 35.0,           # 紧阈值：只支撑真的挂不住的
    "angle_tiny_deg": 30.0,            # 极紧：几乎不支撑
    "angle_draft_deg": 35.0,           # 草稿档：比常规松，少支撑少时间
    "angle_precision_deg": 28.0,       # 精细档：更早触发支撑，支撑面更干净
    "angle_ultra_deg": 20.0,           # 超精细档：官方 0.08mm Extra Fine 的 15~20°
    "angle_overhang_critical_deg": 38.0,
    "spacing_normal": 2.5,
    "spacing_dense": 2.0,
    "spacing_very_dense": 1.8,
    "spacing_loose": 3.0,
    "interface_spacing_normal": 0.5,
    "interface_spacing_tight": 0.3,
    "interface_spacing_loose": 0.8,
    "interface_layers_normal": 3,
    "interface_layers_strong": 4,
    "top_z_normal": 0.2,
    "top_z_tight": 0.1,
    "top_z_loose": 0.3,
    "bottom_z_normal": 0.2,
    "xy_distance_normal": 0.35,
    "xy_distance_tight": 0.2,
    "xy_distance_loose": 0.5,
    "expansion_normal": 0.0,
    "expansion_wide": 0.2,
    "branch_angle_normal": 40.0,
    "branch_diameter_normal": 1.6,
    "branch_distance_normal": 6.0,
    "branch_wall_count_normal": 1,
}


def _policy(policy: dict | None) -> dict:
    merged = dict(BUILTIN_POLICY)
    if policy:
        merged.update(policy)
    return merged


def _as_float(value) -> float | None:
    """把工程里的原始值转成 float；转不了就当「没这个值」。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value) -> bool | None:
    """把工程里的原始值转成 bool；转不了就当「没这个值」。

    工程里的 enable_support 可能是 bool、0/1，也可能是字符串 "1"/"0"。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "enable", "enabled"):
        return True
    if text in ("", "0", "false", "no", "off", "disable", "disabled"):
        return False
    return None


def _calc_angle(p: dict, overhang_ratio: float, mode: str,
                mode_angle: float | None = None) -> tuple[float, str]:
    """按几何算出推荐的支撑触发角（度）与依据说明。

    mode_angle：模式档自己算出来的判定角（引擎在模式层算完传进来）。
        有它就以它为准 —— 官方档位（精细 20°、超精细 15°、草稿 35°）
        就是这么定的，几何层不该再自己改一档。
    """
    if mode_angle is not None:
        angle = float(mode_angle)
        why = f"按「{mode}」这一档的判定角 {angle:g}°（与官方档位一致）。"
    elif overhang_ratio >= float(p["overhang_ratio_critical"]):
        angle = float(p["angle_overhang_critical_deg"])
        why = f"悬垂面多，支撑触发角放宽到 {angle:g}°（更多面被支撑，更稳）。"
    elif mode_registry.family(mode) == "quality":
        angle = float(p["angle_tight_deg"])
        why = f"表面质量优先：支撑触发角收紧到 {angle:g}°，少支撑、少接痕。"
    elif mode_registry.family(mode) == "strength":
        angle = float(p["angle_normal_deg"])
        why = f"强度优先：支撑触发角 {angle:g}°。"
    elif mode_registry.family(mode) == "draft":
        angle = float(p["angle_draft_deg"])
        why = f"快速草稿：支撑判定放宽到 {angle:g}°，少生成支撑、缩短时间。"
    else:
        angle = float(p["angle_normal_deg"])
        why = f"支撑触发角 {angle:g}°。"
    return angle, why


# ------------------------------------------------------------------ op 合并

#: 支撑相关的键（用于从全局 ops 里挑出支撑部分做合并）
SUPPORT_PREFIXES = ("support_", "tree_support_")


def is_support_key(key: str) -> bool:
    """这个键是不是支撑相关的。"""
    return key == "enable_support" or key.startswith(SUPPORT_PREFIXES)


def _pick_set(a_val, b_val, direction: str, prefer: str):
    """set + set 时挑一个更保守的值。

    prefer="b"：直接取 b（几何算出的值更贴合本模型，形状原型让位）；
    prefer="a"：数值型取较小（direction="max" 的键取较大），
                 布尔与非数值型（枚举）保持先出现的那条。
    """
    if prefer == "b":
        return b_val
    if isinstance(a_val, bool) or isinstance(b_val, bool):
        return a_val
    try:
        av, bv = float(a_val), float(b_val)
    except (TypeError, ValueError):
        return a_val
    if direction == "max":
        return max(av, bv)
    return min(av, bv)


def merge_op(a: dict, b: dict, direction: str = "keep", prefer: str = "a") -> dict:
    """合并两条 op（引擎侧语义：set 绝对赋值、mul/add 相对当前值、min/max 夹上下限）。

    同型合并按「更保守」的一侧：

        mul + mul → 累乘
        min + min → 取大（更紧的下限）
        max + max → 取小（更紧的上限）
        add + add → 取大
        set + set → 数值型取较小（direction="max" 的键取较大），
                    非数值型保持先出现的那条；prefer="b" 时以 b 为准。

    异型合并（例如形状原型给的 {"max": 42} 与几何算出的 {"set": 38}）
    **两条约束都要保留**：结果里同时含两个键，绝不整条丢弃。
    引擎先按 set 赋值、再按 min/max 夹上下限，语义正好成立
    （set=38 + max=42 → 最终 38°，几何算出的角度不会被原型吃掉）。

    无论同型还是异型，a、b 里原本存在的 op 键一个都不许丢。
    """
    if not a:
        return dict(b)
    if not b:
        return dict(a)
    out = dict(a)
    for key in ("set", "mul", "min", "max", "add"):
        in_a, in_b = key in a, key in b
        if not in_a and not in_b:
            continue
        if not in_b:
            out[key] = a[key]            # a 独有：原样保留
            continue
        if not in_a:
            out[key] = b[key]            # b 独有：异型合并的关键，绝不丢
            continue
        # 同型：取更保守的一侧
        if key == "mul":
            out["mul"] = float(a["mul"]) * float(b["mul"])
        elif key == "min":
            out["min"] = max(float(a["min"]), float(b["min"]))
        elif key == "max":
            out["max"] = min(float(a["max"]), float(b["max"]))
        elif key == "add":
            out["add"] = max(float(a["add"]), float(b["add"]))
        else:                            # set
            out["set"] = _pick_set(a["set"], b["set"], direction, prefer)
    return out


@dataclass
class SupportDecision:
    """一次支撑决策的结论与依据。"""
    enable: bool
    ops: dict
    reasons: list[str]

    def summary(self) -> str:
        return "；".join(self.reasons)


def decide(profile: model_analysis.ModelProfile, *,
           mode: str = "balanced",
           policy: dict | None = None,
           user_threshold_angle: float | None = None,
           user_enable_support: bool | None = None,
           has_model: bool = True,
           mode_angle: float | None = None) -> SupportDecision:
    """根据模型几何决定支撑方案。

    参数
    ----
    profile：模型形状画像（几何量来源）。
    mode：模式档（balanced / strength / quality），影响角度与密度的取舍。
    policy：支撑策略阈值表（规则库 support_policy 节点），缺省用内置。
    user_threshold_angle：用户在工程里自己设的「悬垂判定角」（度）。
        用户在 Bambu Studio 里手动改过这个角，这里必须尊重它：
        用户角比几何建议更小 → 用用户角（更早触发支撑，更安全）；
        用户角比几何建议更大 → 用几何角（更贴合本模型），并写明取舍。
    user_enable_support：用户在工程里自己设的「启用支撑」开关。
        用户开着 → 几何上不需要支撑时也不关掉，只在 reasons 里说明。
    has_model：有没有模型画像。为 False 时无法做几何判断，
        不产出任何会改动 enable_support 的 op（避免外层用规则库默认值
        把支撑无声关闭），保留工程里的设置。
    mode_angle：模式档自己算出来的判定角（度）。官方档位对判定角有明确
        取值（精细 20°、超精细 15°、草稿 35°），有这个值时以它为准，
        几何层不再自行改一档。
    """
    p = _policy(policy)
    reasons: list[str] = []
    ops: dict = {}

    user_angle = _as_float(user_threshold_angle)
    user_enable = _as_bool(user_enable_support)

    # ---- 0）没有模型几何：不做任何判断，也不碰支撑开关
    if not has_model:
        reasons.append("没有模型几何信息，未对支撑做任何判断，保留工程里的设置。")
        return SupportDecision(False, {}, reasons)

    if not profile.objects:
        return SupportDecision(False, {}, ["工程里没有可分析的模型对象，未改动支撑设置。"])

    # ---- 汇总几何量
    overhang_ratio = max(profile.support_ratio, 0.0)
    # 用逐件的悬垂比例取加权平均（按体积加权，薄的件权重也够）
    weights = [max(o.volume, 1.0) for o in profile.objects]
    rsum = sum(o.overhang_ratio * w for o, w in zip(profile.objects, weights))
    wsum = sum(weights)
    overhang_ratio = rsum / wsum if wsum else overhang_ratio
    height = profile.height
    min_z = min(o.min_z for o in profile.objects)
    max_z = max(o.max_z for o in profile.objects)
    on_plate = min_z < 0.6          # 有对象基本贴在平台上

    # ---- 1）要不要支撑
    # 判定角只影响「要不要开支撑」这一步的敏感度；
    # 最终写进工程的 support_threshold_angle 在第 4 步单独取舍。
    geo_angle, angle_why = _calc_angle(p, overhang_ratio, mode, mode_angle)
    judge_angle = geo_angle
    if user_angle is not None and abs(user_angle - geo_angle) > 1e-6:
        # 取更小的那个：判定用哪个角，取决于谁更敏感。
        #   用户角更小 → 用户更敏感 → 按用户角判定（更早触发支撑，更安全）
        #   几何/模式角更小 → 按更敏感的角判定
        judge_angle = min(user_angle, geo_angle)
        if user_angle < geo_angle:
            reasons.append(f"你把悬垂判定角设成了 {user_angle:g}°（比几何建议 {geo_angle:g}° 更敏感），"
                           "判定是否需要支撑时按更早触发处理。")
        else:
            reasons.append(f"按几何/模式建议的 {geo_angle:g}° 判定"
                           "（比你工程里设的更敏感，更容易触发支撑）。")

    # 判定角越敏感 → 触发门槛越低（更容易开支撑）；
    # 越宽松 → 门槛越高（更倾向于不开支撑）。
    base_ratio = float(p["overhang_ratio_enabled"])
    ratio_enabled = (base_ratio * (judge_angle / geo_angle)
                     if geo_angle > 1e-6 else base_ratio)
    ratio_enabled = max(0.0, min(ratio_enabled, 1.0))
    if abs(judge_angle - geo_angle) > 1e-6:
        reasons.append(f"按 {judge_angle:g}° 判定，悬垂面占比门槛为 {ratio_enabled*100:.0f}%"
                       f"（几何基准 {base_ratio*100:.0f}%）。")

    enable = overhang_ratio >= ratio_enabled
    if enable:
        reasons.append(
            f"模型悬垂面占 {overhang_ratio*100:.0f}%"
            f"（阈值 {ratio_enabled*100:.0f}%），需要支撑。")
    else:
        reasons.append(
            f"模型悬垂面仅 {overhang_ratio*100:.0f}%，"
            f"低于 {ratio_enabled*100:.0f}%，不建议加支撑。")
        # 明确不支撑：只把 enable_support 关掉，其余保持工程原值
        # 但用户自己在工程里开着支撑 → 不静默翻掉，只说明。
        if user_enable is True:
            reasons.append("几何上悬垂很少，不需要支撑，"
                           "但你工程里开着，已保留原设置。")
            return SupportDecision(False, {}, reasons)
        ops["enable_support"] = {"set": False}
        return SupportDecision(False, ops, reasons)

    # ---- 2）支撑类型
    if height >= float(p["height_very_tall_mm"]):
        ops["support_type"] = {"set": "tree(auto)"}
        ops["support_style"] = {"set": "tree_hybrid"}
        reasons.append(f"模型高 {height:.0f} mm（≥{float(p['height_very_tall_mm']):.0f} mm），用树状支撑（tree_hybrid）省料、好拆。")
    else:
        ops["support_type"] = {"set": "tree(auto)"}
        reasons.append("默认使用自动树状支撑。")

    # ---- 3）支撑密度（底纹间距，越小越密）
    if overhang_ratio >= float(p["overhang_ratio_dense"]):
        spacing = float(p["spacing_very_dense"])
        reasons.append(f"悬垂面占比高（{overhang_ratio*100:.0f}%），支撑加密到底纹间距 {spacing:g} mm。")
    elif overhang_ratio >= float(p["overhang_ratio_critical"]):
        spacing = float(p["spacing_dense"])
        reasons.append(f"悬垂面占 {overhang_ratio*100:.0f}%，支撑密度提到间距 {spacing:g} mm。")
    else:
        spacing = float(p["spacing_normal"])
        reasons.append(f"支撑底纹间距 {spacing:g} mm（常规密度）。")
    fam = mode_registry.family(mode)
    if fam == "strength":
        spacing = max(float(p["spacing_very_dense"]), spacing - 0.3)
    elif fam == "quality":
        spacing = min(float(p["spacing_loose"]), spacing + 0.5)
    elif fam == "draft":
        spacing = max(float(p["spacing_loose"]), spacing + 0.5)
    ops["support_base_pattern_spacing"] = {"set": spacing}

    # ---- 4）悬垂判定阈值（度）
    # geo_angle / angle_why 已在第 1 步算好（判定敏感度时用的是同一个角）
    angle = geo_angle
    reasons.append(angle_why)
    if user_angle is not None and abs(user_angle - angle) > 1e-6:
        # 取舍：算出的角不能比用户设的更激进
        #   用户角更小（更敏感）→ 用用户角（更早触发支撑，更安全）
        #   用户角更大 → 用几何角（更贴合本模型），并写明取舍
        if user_angle < angle:
            reasons.append(f"你把判定角设为 {user_angle:g}°，几何建议 {angle:g}°，"
                           f"取 {user_angle:g}°（你更敏感，更早触发支撑，更安全）。")
            angle = user_angle
        else:
            reasons.append(f"你把判定角设为 {user_angle:g}°，几何建议 {angle:g}°，"
                           f"取 {angle:g}°（更贴合本模型）。")
    ops["support_threshold_angle"] = {"set": angle}

    # ---- 5）贴面（接口）设置：越紧越贴牢，但也越难拆
    if fam == "quality":
        isp = float(p["interface_spacing_tight"])
        ilayers = int(p["interface_layers_normal"])
        reasons.append(f"表面质量优先：支撑贴面收紧到间距 {isp:g} mm，支撑面更干净。")
    elif fam == "strength":
        isp = float(p["interface_spacing_normal"])
        ilayers = int(p["interface_layers_strong"])
        reasons.append(f"强度优先：支撑贴面 {ilayers} 层、间距 {isp:g} mm，贴面更牢。")
    elif fam == "draft":
        isp = float(p["interface_spacing_loose"])
        ilayers = int(p["interface_layers_normal"])
        reasons.append(f"快速草稿：支撑贴面放松到间距 {isp:g} mm，好拆、节省时间。")
    else:
        isp = float(p["interface_spacing_normal"])
        ilayers = int(p["interface_layers_normal"])
    ops["support_interface_spacing"] = {"set": isp}
    ops["support_interface_top_layers"] = {"set": ilayers}

    # ---- 6）间隙（间隙大 = 好拆，但支撑面离模型远、看着有缝）
    if fam == "quality":
        tz = float(p["top_z_tight"]); xy = float(p["xy_distance_tight"])
        reasons.append(f"表面质量优先：支撑与模型贴紧（顶面 {tz:g} mm、水平 {xy:g} mm），表面痕迹最小。")
    elif fam == "strength":
        tz = float(p["top_z_normal"]); xy = float(p["xy_distance_normal"])
    elif fam == "draft":
        tz = float(p["top_z_loose"]); xy = float(p["xy_distance_loose"])
        reasons.append(f"快速草稿：支撑与模型留开（顶面 {tz:g} mm、水平 {xy:g} mm），好拆。")
    else:
        tz = float(p["top_z_normal"]); xy = float(p["xy_distance_normal"])
    ops["support_top_z_distance"] = {"set": tz}
    ops["support_bottom_z_distance"] = {"set": float(p["bottom_z_normal"])}
    ops["support_object_xy_distance"] = {"set": xy}

    # ---- 7）只生成关键区域：支撑多的时候省料省时间
    if overhang_ratio >= float(p["overhang_ratio_critical"]):
        ops["support_critical_regions_only"] = {"set": True}
        reasons.append("只生成关键区域支撑：省料省时间，强度不受影响。")
    else:
        ops["support_critical_regions_only"] = {"set": False}

    # ---- 8）小悬垂忽略
    if overhang_ratio < float(p["overhang_ratio_critical"]):
        ops["support_remove_small_overhang"] = {"set": True}
        reasons.append("忽略小悬垂面：不值得为它单独长支撑。")

    # ---- 9）树状支撑细节（模型很高才生效）
    if height >= float(p["height_tall_mm"]):
        ops["tree_support_branch_angle"] = {"set": float(p["branch_angle_normal"])}
        ops["tree_support_branch_diameter"] = {"set": float(p["branch_diameter_normal"])}
        ops["tree_support_branch_distance"] = {"set": float(p["branch_distance_normal"])}
        ops["tree_support_wall_count"] = {"set": int(p["branch_wall_count_normal"])}
        reasons.append(f"模型高 {height:.0f} mm，树状支撑分支按 {float(p['branch_angle_normal']):g}° / "
                       f"直径 {float(p['branch_diameter_normal']):g} mm 设置，保证支撑自身够结实。")

    # ---- 10）只在板上生成支撑：模型整体抬高（多件一起打）时用
    if not on_plate and min_z > 2.0:
        ops["support_on_build_plate_only"] = {"set": True}
        reasons.append(f"模型最低面在 Z={min_z:.1f} mm（悬空摆放），支撑只在平台生成。")

    # 定量参数（密度/间隙/形态/接触面/速度）统一由 core/support_model.py 决定，
    # 这里只交出「要不要支撑」和「悬垂判定角」两件事，避免三方抢写。
    ops = {k: v for k, v in ops.items()
           if k in ("enable_support", "support_threshold_angle")}
    return SupportDecision(True, ops, reasons)


def merge_ops(proto_ops: dict | None, geo_ops: dict | None) -> dict:
    """把形状原型的支撑建议（proto_ops）与几何算出的支撑建议（geo_ops）合并。

    合并语义（与 core/shape_rules._merge_op 一致）：

        · 异型（一个 set、一个 max/min/mul/add）→ **两条都保留**。
          例如原型给 {"max": 42}、几何给 {"set": 38} → 结果 {"set": 38, "max": 42}，
          引擎先 set 再夹上限，最终是 38°，几何算出的角度不会被原型吃掉。
        · 同型 set + set → **几何值优先**（几何更贴合本模型）；
          其余同型按「更保守」合并（mul 累乘、min 取大、max 取小、add 取大）。

    只处理支撑相关的键（enable_support / support_* / tree_support_*）；
    proto_ops 里的非支撑键原样带出，不会被这里改掉。
    """
    proto_ops = proto_ops or {}
    geo_ops = geo_ops or {}
    out: dict = {k: dict(v) for k, v in proto_ops.items() if not is_support_key(k)}
    for key, op in proto_ops.items():
        if is_support_key(key):
            out[key] = dict(op)
    for key, op in geo_ops.items():
        if key not in out:
            out[key] = dict(op)
            continue
        out[key] = merge_op(out[key], dict(op), prefer="b")
    return out


def plan(profile: model_analysis.ModelProfile, *,
         mode: str = "balanced",
         policy: dict | None = None,
         proto_ops: dict | None = None,
         user_threshold_angle: float | None = None,
         user_enable_support: bool | None = None,
         has_model: bool = True,
         mode_angle: float | None = None) -> tuple[dict, list[str]]:
    """给引擎用：返回 (支撑相关 ops, 说明列表)。

    proto_ops：形状原型层已经算好的全局 ops（其中支撑相关的部分要与几何结论合并）。
    user_threshold_angle / user_enable_support：工程里用户自己设的判定角与支撑开关。
    has_model：有没有模型画像；为 False 时返回空 ops（保留工程里的设置）。
    mode_angle：模式档自己算出来的判定角（度），透传给 decide()。
    """
    dec = decide(profile, mode=mode, policy=policy,
                 user_threshold_angle=user_threshold_angle,
                 user_enable_support=user_enable_support,
                 has_model=has_model,
                 mode_angle=mode_angle)
    notes = ["支撑策略（按模型几何判定）：" + dec.summary() + "。"]
    if not has_model:
        # 没有几何信息 → 不产出任何 op，避免外层用规则库默认值覆盖工程设置
        return {}, notes
    geo_ops = dec.ops
    if proto_ops:
        merged = merge_ops(proto_ops, geo_ops)
        # 定量参数由 core/support_model.py 唯一决定：把 proto 带进来的支撑定量键剔掉，
        # 只留「要不要支撑 / 判定角」两个决策
        merged = {k: v for k, v in merged.items()
                  if not is_support_key(k)
                  or k in ("enable_support", "support_threshold_angle")}
        touched = sorted(k for k in geo_ops if k in (proto_ops or {}))
        if touched:
            notes.append("支撑参数已与形状原型的建议合并（几何值优先）：" + "、".join(touched) + "。")
        return merged, notes
    return geo_ops, notes