import io

p = "core/schema.py"
s = io.open(p, encoding="utf-8").read()
old = """        fill_all = (
            _WRITE_ALL_VARIANT_SLOTS
            and _VARIANT_SLOTS > 1
            and n == _VARIANT_SLOTS
            and s.kind in (ARRAY_FLOAT, ARRAY_PCT)
        )"""
new = """        fill_all = (
            _WRITE_ALL_VARIANT_SLOTS
            and _VARIANT_SLOTS > 1
            and n == _VARIANT_SLOTS
            and s.kind != VEC_FLOAT      # 体积流量自适应系数是一整串数字，不按槽处理
        )"""
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("fill_all 条件改为按数组长度判断")
