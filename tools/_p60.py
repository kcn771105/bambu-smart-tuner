import io

p = "core/schema.py"
s = io.open(p, encoding="utf-8").read()
old = '''P("ensure_vertical_shell_thickness", "确保垂直外壳厚度", "wall", ENUM,
  choices=("enabled", "disabled", "ensure_all"))'''
if old not in s:
    import re
    m = re.search(r'P\("ensure_vertical_shell_thickness".*?\)', s, re.S)
    print("实际写法：", m.group(0) if m else "没找到")
else:
    new = '''P("ensure_vertical_shell_thickness", "确保垂直外壳厚度", "wall", ENUM,
  choices=("enabled", "disabled", "partial"))'''
    s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print("ensure_vertical_shell_thickness 选项改为 enabled/disabled/partial")
