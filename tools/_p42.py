import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

bad = """        root_top.addWidget(self.split, 1)
        return w
        root_bot.addWidget(self.split, 1)"""
good = """        root_bot.addWidget(self.split, 1)"""
assert bad in s
s = s.replace(bad, good, 1)

bad2 = """        root.addWidget(self.vsplit, 1)
        return w
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        bar = QHBoxLayout()
        self.rp_printer = QComboBox()"""
good2 = """        root.addWidget(self.vsplit, 1)
        return w

    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        bar = QHBoxLayout()
        self.rp_printer = QComboBox()"""
assert bad2 in s
s = s.replace(bad2, good2, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("修复拼接处的两行残留 + 补回 _build_rules_tab 签名")
