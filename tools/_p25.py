import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---- import 加 hotend / safety
old_imp = ("from core import (bambu_profiles, detector, hardware, model_analysis, modes as modes_reg,\n"
           "                  report, rules_engine, schema, scope, shape_rules, threemf)")
new_imp = ("from core import (bambu_profiles, detector, hardware, hotend, model_analysis,\n"
           "                  modes as modes_reg, report, rules_engine, safety, schema, scope,\n"
           "                  shape_rules, threemf)")
assert old_imp in s
s = s.replace(old_imp, new_imp, 1)

# ---- 下拉：第 0 行第 6/7 列
old = '''        d.addWidget(QLabel(""), 0, 6)'''
new = '''        # 热端流量类型（标准 / 高流量 / E3D 高流量）：工程里能读出来，也可以手改
        self.cmb_hotend = QComboBox()
        self.cmb_hotend.setMinimumWidth(150)
        for key, label in hotend.options(self.engine.rules):
            self.cmb_hotend.addItem(label, key)
        self.cmb_hotend.currentIndexChanged.connect(self._on_override_changed)
        d.addWidget(QLabel("热端流量"), 0, 6)
        d.addWidget(self.cmb_hotend, 0, 7)'''
assert old in s
s = s.replace(old, new, 1)

# ---- optimize 传 hotend_flow
old2 = "                hardware_info=self.hw, nozzle_explicit=nozzle_explicit)"
new2 = ("                hardware_info=self.hw, nozzle_explicit=nozzle_explicit,\n"
        "                hotend_flow=(self.cmb_hotend.currentData() or None))")
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("UI：import + 流量下拉 + optimize 传参")
