"""均衡档对齐官方 0.20mm Standard：去掉「墙 +1」「密度 +35%」两处主动加厚。

理由（对着本机 2.03 的官方预设审出来的）：
- 官方 Standard 就是 Bambu Studio 自己的「均衡」档：wall_loops 2、density 15%、grid。
- 我们的均衡档额外加了一圈墙、把密度抬到 20.25%、图案换 gyroid，
  叠起来让时间从「几乎不变」变成 +40%，这不符合「均衡」这个档位的语义。
- 保留的改动都是有明确收益的：外壁 ×0.85（表面）、外壁加速度 ×0.8（振纹）、
  顶面单调（表面）、填充重叠 18%（层间结合）、gyroid（等强度更省料）。
"""
import io
import json
import shutil

P = "rules/BambuRules.json"
shutil.copyfile(P, P + ".bak_bal_align")
data = json.load(io.open(P, encoding="utf-8-sig"))

bal = data["modes"]["balanced"]
ops = bal["ops"]
removed = []
for key in ("wall_loops", "sparse_infill_density"):
    if key in ops:
        ops.pop(key)
        removed.append(key)

bal["desc"] = ("对齐官方 0.20mm Standard（层高、墙圈数、填充密度都不动），"
               "只做有明确收益的微调：外壁降 15%、外壁加速度 ×0.8、顶面单调、"
               "填充重叠 18%、gyroid 填充、开启减速系数。期望时间涨幅 0~20%。")

json.dump(data, io.open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已移除均衡档的主动加厚项：", removed)
print("剩余 ops：", sorted(ops))
