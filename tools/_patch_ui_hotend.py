import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1. 新建「热端流量类型」下拉（放在第 0 行末列，紧跟喷嘴直径）
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

# ---- 2. import
s = s.replace("from core import detector", "from core import detector, hotend", 1)
if "from core import detector, hotend" not in s:
    # 兜底：找到任意 core import 行追加
    import re
    m = re.search(r"from core import ([^\n]+)\n", s)
    if m and "hotend" not in m.group(1):
        s = s.replace(m.group(0), m.group(0).rstrip("\n") + ", hotend\n", 1)

# ---- 3. 识别工程后把下拉设成识别结果
old3 = '''        self.cmb_nozzle.setCurrentIndex(i if i >= 0 else 0)'''
new3 = '''        self.cmb_nozzle.setCurrentIndex(i if i >= 0 else 0)
        # 热端流量类型：识别出来的先占位，用户可改（改了就按新的算）
        self._hotend_info = hotend.detect({})'''
assert old3 in s
s = s.replace(old3, new3, 1)

# ---- 4. optimize 调用带上 hotend_flow
old4 = "            nozzle_explicit=True,"
if old4 in s:
    s = s.replace(old4, "            nozzle_explicit=True,\n"
                        "            hotend_flow=(self.cmb_hotend.currentData() or None),", 1)
else:
    raise SystemExit("找不到 optimize 调用点 nozzle_explicit")

io.open(p, "w", encoding="utf-8").write(s)
print("UI：加流量类型下拉 + optimize 传参")
