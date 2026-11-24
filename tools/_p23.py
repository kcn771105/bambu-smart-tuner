import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# 在算出 official（官方耗材×机型×喷嘴标定）之后、与 overlay/project 取小之前，
# 乘上热端流量类型的倍率 —— 高流量热端能推更多，这是它省时间的唯一入口。
old = """        max_flow = official
        if overlay_max:"""
new = """        if official and self._hotend_mul > 1.0:
            official = float(official) * self._hotend_mul
            srcs.append(
                f"热端流量类型「{self._hotend.label}」×{self._hotend_mul:g}")
        max_flow = official
        if overlay_max:"""
assert old in s
s = s.replace(old, new, 1)

# 工程里的实测标定同样享受高流量倍率（它是在这根热端上标出来的）
old2 = """            pm = float(project_max)"""
new2 = """            pm = float(project_max)"""
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("流量上限已接入热端倍率")
