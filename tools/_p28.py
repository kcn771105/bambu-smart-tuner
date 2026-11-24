import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# OptResult 加 hotend 字段
old = '    plate: str = ""'
assert old in s, "OptResult 里找不到 plate 字段"
s = s.replace(old, '    plate: str = ""\n    hotend: str = ""', 1)

# 构造时填
old2 = "            plate=self._plate_info,"
if old2 in s:
    s = s.replace(old2, "            plate=self._plate_info,\n"
                        "            hotend=self._hotend.summary_line(),", 1)
else:
    i = s.find("plate=self._plate_info")
    print("构造写法：", s[max(0, i-300):i+200])
    raise SystemExit(1)

io.open(p, "w", encoding="utf-8").write(s)
print("OptResult.hotend 已加")
