import io

# ---- 1. hardware.BedInfo.summary：禁打区按矩形数（4 个角点 = 1 块）
p = "core/hardware.py"
s = io.open(p, encoding="utf-8").read()
old = '''        s = f"{self.width:.0f} × {self.depth:.0f} mm"
        if self.exclude:
            s += f"（前方禁打区 {len(self.exclude)} 块）"
        return s'''
new = '''        s = f"{self.width:.0f} × {self.depth:.0f} mm"
        if self.exclude:
            # 工程里存的是矩形角点，4 个点 = 1 块
            blocks = max(1, len(self.exclude) // 4)
            s += f"（前方禁打区 {blocks} 块）"
        return s'''
assert old in s
s = s.replace(old, new, 1)

# ---- 2. hardware.read 顺带读板型，summary_lines 里加一行
old2 = '''        out.append(f"板面：{self.bed.summary()}")'''
new2 = '''        if self.plate_type:
            out.append(f"打印板：{self.plate_type}")
        out.append(f"板面：{self.bed.summary()}")'''
assert old2 in s
s = s.replace(old2, new2, 1)

old3 = '''    # ---- 板面
    bed: BedInfo = field(default_factory=BedInfo)'''
new3 = '''    # ---- 板面
    bed: BedInfo = field(default_factory=BedInfo)
    #: 打印板类型（工程 curr_bed_type，只读）
    plate_type: str = ""'''
assert old3 in s
s = s.replace(old3, new3, 1)

import re
m = re.search(r'    hw\.bed = [^\n]*\n', s)
if m:
    ins = m.group(0) + '    hw.plate_type = str(s.get("curr_bed_type") or "").strip()\n'
    s = s.replace(m.group(0), ins, 1)
else:
    # 找不到赋值处就补在 return hw 之前
    s = s.replace("    return hw",
                  '    hw.plate_type = str(s.get("curr_bed_type") or "").strip()\n    return hw', 1)

io.open(p, "w", encoding="utf-8").write(s)
print("hardware 增打印板行")

# ---- 3. plate.check 去掉与 hardware 重复的两条说明
p2 = "core/plate.py"
t = io.open(p2, encoding="utf-8").read()
t = t.replace('''        else:
            notes.append(
                f"板面已同步：{plate.bed_w:g} × {plate.bed_d:g} mm"
                + (f" × 高 {plate.bed_h:g} mm" if plate.bed_h else "")
                + f"，与「{printer_key}」官方板面一致。")''',
'''        # 尺寸一致时不再重复 hardware 那条「板面已同步」''', 1)
t = t.replace('''    if plate.exclude_blocks and plate.area > 0:
        notes.append(
            f"前方禁打区 {plate.exclude_blocks} 块（机器页只读）：摆盘时避开这块区域，"
            f"本程序只调工艺参数，不动摆放。")''',
'''    # 禁打区已由 hardware 的「板面」行说明，这里不重复''', 1)
io.open(p2, "w", encoding="utf-8").write(t)
print("plate 去重")
