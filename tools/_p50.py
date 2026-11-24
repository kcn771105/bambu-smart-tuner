import io

p = "tools/gen_studio_ui.py"
s = io.open(p, encoding="utf-8").read()
anchor = '    "support_type": ("支撑", "支撑样式", "类型", "Type"),'
extra = ('    "enable_support": ("支撑", "启用", "启用支撑", "Enable support"),\n'
         '    "bridge_angle": ("质量", "精度", "桥接方向", "Bridge direction"),\n')
assert anchor in s
if '"enable_support"' not in s:
    s = s.replace(anchor, extra + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("补两条 override")
