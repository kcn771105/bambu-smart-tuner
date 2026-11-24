"""把 7 个「规则库从不主动调」的工艺键接进规则。

改哪些、为什么：
1. thin_wall / small_detail 原型 → wall_generator = arachne
   薄壁件用经典墙算法会漏掉窄于线宽的区域，Arachne 能变线宽填满，是薄壁件的标准解法。
2. quality 档 → infill_combination = true
   组合填充把同层相邻填充合并成一条长线，减少空走 → 少拉丝、表面更干净。
3. strength 档 → inner_wall_acceleration = 0（0 = 跟随默认加速度）
   内壁加速度原本被压到 70% 换表面，内壁看不见，强度档没必要为它付时间。
4. brim_width > 0 时 → brim_object_gap = 0.3（让裙边贴着模型但不粘连）
   原来这两项都 preserve，等于裙边相关一个都不调。

不动的三个：print_in_clockwise / smooth_coefficient / sparse_infill_acceleration
—— 前者是个人偏好，中者是平滑算法强度（对时间/强度都无明确最优），
后者在强度档提高会与体积流量上限打架，交给 8d 钳制反而更稳。
"""
import io
import json
import shutil

P = "rules/BambuRules.json"
shutil.copyfile(P, P + ".bak_cover7")
data = json.load(io.open(P, encoding="utf-8-sig"))

changed = []

# 1) 形状原型：薄壁/细小件走 Arachne
for proto in ("thin_wall", "small_detail"):
    node = data["shape_profiles"].get(proto, {})
    for mode, ops in node.items():
        if not isinstance(ops, dict):
            continue
        if "wall_generator" not in ops:
            ops["wall_generator"] = {"set": "arachne"}
            changed.append(f"shape_profiles.{proto}.{mode}.wall_generator=arachne")

# 2) 质量档开组合填充
q = data["modes"]["quality"]["ops"]
if "infill_combination" not in q:
    q["infill_combination"] = {"set": True}
    changed.append("modes.quality.ops.infill_combination=true")

# 3) 强度档内壁加速度跟随默认
st = data["modes"]["strength"]["ops"]
if "inner_wall_acceleration" not in st:
    st["inner_wall_acceleration"] = {"set": 0}
    changed.append("modes.strength.ops.inner_wall_acceleration=0")

# 4) 裙边贴合：交叉规则里加一条（只在工程本来就有裙边时才动）
inter = data.get("interactions") or []
name = "brim-gap-adhesion"
if not any(i.get("name") == name for i in inter):
    inter.append({
        "name": name,
        "when": {"key": "brim_width", "op": ">", "value": 0},
        "ops": {"brim_object_gap": {"set": 0.3}},
        "why": "有裙边时不贴死模型：留 0.3 mm 间隙，撕裙边不会带下底面首层。",
        "lock": False,
    })
    data["interactions"] = inter
    changed.append("interactions.brim-gap-adhesion")

json.dump(data, io.open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("改动的规则：")
for c in changed:
    print("  ", c)
