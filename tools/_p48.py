import io

p = "core/report.py"
s = io.open(p, encoding="utf-8").read()

if "studio_ui" not in s.split("def build_markdown")[0]:
    s = s.replace("from . import schema, shape_rules",
                  "from . import schema, shape_rules, studio_ui", 1)

old = '''            add("| 参数 | 归属 | 原始 | 优化后 | 写入 | 原因 |")
            add("| --- | --- | --- | --- | --- | --- |")'''
new = '''            add("| 参数 | Studio 里在哪 | 归属 | 原始 | 优化后 | 写入 | 原因 |")
            add("| --- | --- | --- | --- | --- | --- | --- |")'''
if old in s:
    s = s.replace(old, new, 1)
    print("表头已改")

old2 = '''        add(f"| {row.label}{mark} | {SCOPE_LABEL.get(row.scope, row.scope)} | "
            f"{row.old_display} | {row.new_display} | {write} | {reason} |")'''
new2 = '''        spot = studio_ui.info(row.key, fallback_label=row.label, group=row.group)
        add(f"| {row.label}{mark} | {spot.path.replace('|', '／')} | "
            f"{SCOPE_LABEL.get(row.scope, row.scope)} | "
            f"{row.old_display} | {row.new_display} | {write} | {reason} |")'''
if old2 in s:
    s = s.replace(old2, new2, 1)
    print("数据行已改")

io.open(p, "w", encoding="utf-8").write(s)
print("done")
