import io

# ---- 1. hotend.py 去掉 speed_factor
p = "core/hotend.py"
s = io.open(p, encoding="utf-8").read()
i = s.find("def speed_factor(")
j = s.find("def options(")
assert i > 0 and j > i
s = s[:i] + s[j:]
io.open(p, "w", encoding="utf-8").write(s)
print("hotend.py 去掉 speed_factor")

# ---- 2. 引擎：optimize 增加 hotend_flow 形参 + 自动识别 + 流量倍率
p2 = "core/rules_engine.py"
e = io.open(p2, encoding="utf-8").read()

# 2a. import
e = e.replace(
    "from . import estimator, hardware, nozzle_flow, modes as modes_registry, schema, scope",
    "from . import (estimator, hardware, hotend, nozzle_flow,\n"
    "               modes as modes_registry, schema, scope)", 1)

# 2b. optimize 形参
old_sig = "        nozzle_explicit: bool = False,"
assert old_sig in e
e = e.replace(old_sig,
              "        nozzle_explicit: bool = False,\n"
              "        hotend_flow: str | None = None,", 1)

# 2c. 开头重置 + 识别
old_reset = '        self._plate_info = ""\n        self._project_for_plate = current'
assert old_reset in e
e = e.replace(old_reset,
              '        self._plate_info = ""\n'
              '        self._project_for_plate = current\n'
              '        # 热端流量类型：UI 传了就用传的，没传就按工程自动识别\n'
              '        self._hotend = hotend.detect(current)\n'
              '        if hotend_flow and hotend.normalize(hotend_flow):\n'
              '            self._hotend = hotend.HotendInfo(\n'
              '                hotend.normalize(hotend_flow),\n'
              '                source_key="用户选择", source_value=str(hotend_flow),\n'
              '                nozzle_volume=self._hotend.nozzle_volume,\n'
              '                variants=self._hotend.variants, detected=True)\n'
              '        self._hotend_mul, _hotend_note = hotend.factor(\n'
              '            self.rules, self._hotend.key)\n'
              '        notes.append(f"热端流量类型：{self._hotend.label}"\n'
              '                     + ("（按 1.35 倍流量计）" if self._hotend.key == "high"\n'
              '                        else "（按 1.55 倍流量计）" if self._hotend.key == "e3d"\n'
              '                        else "（官方标配流量）"))', 1)

# 2d. __init__ 增字段
e = e.replace('        self._project_for_plate = None',
              '        self._project_for_plate = None\n'
              '        self._hotend = hotend.HotendInfo()\n'
              '        self._hotend_mul: float = 1.0', 1)

io.open(p2, "w", encoding="utf-8").write(e)
print("引擎：optimize 接 hotend_flow + 自动识别")
