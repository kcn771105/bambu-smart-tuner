import io

p = "tools/gen_studio_ui.py"
s = io.open(p, encoding="utf-8").read()
anchor = '    "seam_position": ("质量", "接缝", "接缝位置", "Seam position"),'
if anchor not in s:
    # 找出真正的 seam_position 行
    for line in s.split("\n"):
        if line.strip().startswith('"seam_position"') and "(" in line:
            anchor = line
            break
extra = ('    "enable_support": ("支撑", "启用", "启用支撑", "Enable support"),\n'
         '    "bridge_angle": ("质量", "精度", "桥接方向", "Bridge direction"),\n')
assert '"bridge_angle": ("质量"' not in s, "已经加过了"
s = s.replace(anchor, extra + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("已插入，锚点：", anchor.strip())
