"""support_plan 只保留「要不要支撑 + 悬垂判定角」两个决策，定量参数交给 support_model。

原来它同时写 spacing / top_z / xy / interface / style / tree_*，
和 support_model 抢写，还会出现「支撑没开却改了间隙」的噪音。
"""
import io

p = "core/support_plan.py"
s = io.open(p, encoding="utf-8").read()

# 在 decide() 返回前统一过滤：只留 enable_support 与 support_threshold_angle
anchor = '    return SupportDecision(True, ops, reasons)'
addition = '''    # 定量参数（密度/间隙/形态/接触面/速度）统一由 core/support_model.py 决定，
    # 这里只交出「要不要支撑」和「悬垂判定角」两件事，避免三方抢写。
    ops = {k: v for k, v in ops.items()
           if k in ("enable_support", "support_threshold_angle")}
    return SupportDecision(True, ops, reasons)'''

assert anchor in s, "没找到 decide 的成功返回点"
if "定量参数（密度/间隙" not in s:
    s = s.replace(anchor, addition, 1)

# 关闭分支只保留 enable_support
s = s.replace('''    ops["enable_support"] = {"set": False}
    return SupportDecision(False, ops, reasons)''',
              '''    ops = {"enable_support": {"set": False}}
    return SupportDecision(False, ops, reasons)''', 1)

io.open(p, "w", encoding="utf-8").write(s)
print("support_plan 已收敛为决策层")
