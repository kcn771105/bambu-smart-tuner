import io

p = "tools/gen_studio_ui.py"
s = io.open(p, encoding="utf-8").read()
anchor = '    "seam_position": ("质量", "接缝", "接缝位置", "Seam position"),'
extra = ('    "enable_support": ("支撑", "启用", "启用支撑", "Enable support"),\n'
         '    "bridge_angle": ("质量", "精度", "桥接方向", "Bridge direction"),\n')
assert anchor in s, "锚点没找到"
assert '"bridge_angle": ("质量"' not in s, "已经加过了"
s = s.replace(anchor, extra + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("补两条 override（enable_support / bridge_angle）")
