import io

p = "core/rules_engine.py"
e = io.open(p, encoding="utf-8").read()

e = e.replace(
    "from . import estimator, hardware, nozzle_flow, modes as modes_registry, schema, scope",
    "from . import (estimator, hardware, hotend, nozzle_flow,\n"
    "               modes as modes_registry, schema, scope)", 1)

old = "                 nozzle_explicit: bool = False) -> OptResult:"
new = ("                 nozzle_explicit: bool = False,\n"
       "                 hotend_flow: str | None = None) -> OptResult:")
assert old in e
e = e.replace(old, new, 1)

old2 = '        self._plate_info = ""\n        self._project_for_plate = current'
assert old2 in e
new2 = '''        self._plate_info = ""
        self._project_for_plate = current
        # 热端流量类型：UI 传了就用传的，没传就按工程自动识别
        self._hotend = hotend.detect(current)
        picked = hotend.normalize(hotend_flow or "")
        if picked:
            self._hotend = hotend.HotendInfo(
                picked, source_key="用户选择", source_value=str(hotend_flow),
                nozzle_volume=self._hotend.nozzle_volume,
                variants=self._hotend.variants, detected=True)
        self._hotend_mul, self._hotend_note = hotend.factor(self.rules, self._hotend.key)
        notes.append(
            f"热端流量类型：{self._hotend.label}"
            + (f"（体积流量上限 ×{self._hotend_mul:g}）" if self._hotend_mul > 1.0
               else "（按官方标配流量）")
            + (f"；{self._hotend_note}" if self._hotend_note else ""))'''
e = e.replace(old2, new2, 1)

e = e.replace('        self._project_for_plate = None',
              '        self._project_for_plate = None\n'
              '        self._hotend = hotend.HotendInfo()\n'
              '        self._hotend_mul: float = 1.0\n'
              '        self._hotend_note: str = ""', 1)

io.open(p, "w", encoding="utf-8").write(e)
print("引擎：hotend_flow 形参 + 自动识别 + 倍率")
