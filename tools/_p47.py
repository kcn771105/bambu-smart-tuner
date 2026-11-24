import io

p = "core/report.py"
s = io.open(p, encoding="utf-8").read()

# import studio_ui
old = "from . import shape_rules"
if old in s:
    s = s.replace(old, "from . import shape_rules, studio_ui", 1)
else:
    raise SystemExit("没找到 from . import shape_rules")

# 表头加「Studio 里在哪」
old = '''            add("| 参数 | 归属 | 原始 | 优化后 | 写入 | 原因 |")
            add("| --- | --- | --- | --- | --- | --- |")'''
new = '''            add("| 参数 | Studio 里在哪 | 归属 | 原始 | 优化后 | 写入 | 原因 |")
            add("| --- | --- | --- | --- | --- | --- | --- |")'''
assert old in s
s = s.replace(old, new, 1)

old = '''        add(f"| {row.label}{mark} | {SCOPE_LABEL.get(row.scope, row.scope)} | "
            f"{row.old_display} | {row.new_display} | {write} | {reason} |")'''
new = '''        spot = studio_ui.info(row.key, fallback_label=row.label, group=row.group)
        add(f"| {row.label}{mark} | {spot.path.replace('|', '／')} | "
            f"{SCOPE_LABEL.get(row.scope, row.scope)} | "
            f"{row.old_display} | {row.new_display} | {write} | {reason} |")'''
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("报告表加 Studio 位置列")
