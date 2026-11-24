import io

p = "core/hardware.py"
s = io.open(p, encoding="utf-8").read()
old = '''        if self.plate_type:
            out.append(f"打印板：{self.plate_type}")
        out.append(f"板面：{self.bed.summary()}")'''
new = '''        # 打印板类型由 core/plate.py 出（带中文名与温度标定），这里不重复
        out.append(f"板面：{self.bed.summary()}")'''
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("hardware 去掉重复的打印板行")
