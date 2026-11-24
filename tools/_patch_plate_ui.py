import io

# ---- UI：真机同步面板追加「打印板」一行（优化后）
p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()
old = '''        if self.result is not None:
            fl = getattr(self.result, "flow_limit", None)
            if fl:
                extra.append(f"本次采用体积流量上限 {fl:g} mm³/s")'''
new = '''        if self.result is not None:
            fl = getattr(self.result, "flow_limit", None)
            if fl:
                extra.append(f"本次采用体积流量上限 {fl:g} mm³/s")
            pl = getattr(self.result, "plate", "")
            if pl:
                extra.append(pl)'''
assert old in s, "UI flow 行锚点没找到"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("UI 增打印板行")

# ---- 报告：头部增打印板
p2 = "core/report.py"
r = io.open(p2, encoding="utf-8").read()
old2 = '''    if result.flow_limit:'''
new2 = '''    if getattr(result, "plate", ""):
        add(f"- {result.plate}")
    if result.flow_limit:'''
assert old2 in r
r = r.replace(old2, new2, 1)
io.open(p2, "w", encoding="utf-8").write(r)
print("报告增打印板行")
