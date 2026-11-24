import io

# 1) schema：支撑速度上限 500 太低（真机 600~1000），提到 1000
p = "core/schema.py"
s = io.open(p, encoding="utf-8").read()
old = 'P("support_speed", "支撑速度", "speed", FLOAT, 10, 500, 5, "mm/s", decimals=0),'
new = 'P("support_speed", "支撑速度", "speed", FLOAT, 10, 1000, 5, "mm/s", decimals=0),'
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("schema: support_speed 上限 500→1000")

p2 = "core/schema_extra.py"
s2 = io.open(p2, encoding="utf-8").read()
old2 = '("support_interface_speed", "支撑接触面速度", "support", "array_float", 5, 300, 5, "mm/s", (), 0, True),'
new2 = '("support_interface_speed", "支撑接触面速度", "support", "array_float", 5, 1000, 5, "mm/s", (), 0, True),'
assert old2 in s2
s2 = s2.replace(old2, new2, 1)
io.open(p2, "w", encoding="utf-8").write(s2)
print("schema_extra: support_interface_speed 上限 300→1000")

# 2) 引擎：支撑速度也要受体积流量约束（0.24×0.42×700 = 70 mm³/s 物理上打不出来）
p3 = "core/rules_engine.py"
s3 = io.open(p3, encoding="utf-8").read()
old3 = '''            "gap_infill_speed": "line_width",
        }'''
new3 = '''            "gap_infill_speed": "line_width",
            "support_speed": "support_line_width",
            "support_interface_speed": "support_line_width",
        }'''
assert old3 in s3
s3 = s3.replace(old3, new3, 1)
io.open(p3, "w", encoding="utf-8").write(s3)
print("engine: flow_keys 加支撑速度")
