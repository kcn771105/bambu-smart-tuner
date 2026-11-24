import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# 顶部包一层滚动区：窗口不高时不会把「推导表」挤出可见范围
old = """        self.vsplit.addWidget(top)
        self.vsplit.addWidget(bottom)"""
new = """        self.top_scroll = QScrollArea()
        self.top_scroll.setWidgetResizable(True)
        self.top_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.top_scroll.setWidget(top)
        self.top_scroll.setMinimumHeight(220)
        self.vsplit.addWidget(self.top_scroll)
        self.vsplit.addWidget(bottom)"""
assert old in s
s = s.replace(old, new, 1)

s = s.replace("self.vsplit.setSizes([520, 640])", "self.vsplit.setSizes([430, 720])", 1)

# 补 import
s = s.replace("    QMenu, QPushButton, QRadioButton, QSplitter, QTableWidget, QTableWidgetItem,",
              "    QFrame, QMenu, QPushButton, QRadioButton, QScrollArea, QSplitter,\n"
              "    QTableWidget, QTableWidgetItem,", 1)
io.open(p, "w", encoding="utf-8").write(s)
print("顶部改滚动区，默认尺寸 430/720")
