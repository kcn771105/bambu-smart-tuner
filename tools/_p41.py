import io
import re

p = "ui/main_window.py"
src = io.open(p, encoding="utf-8").read()
lines = src.split("\n")

# ---------- 1. 工作台改成「上下可拖」的垂直分割：上面工程/识别/模式，下面对比表+日志 ----------
assert lines[104].strip() == "root.setContentsMargins(10, 10, 10, 10)", lines[104]

head = lines[101:107]           # def 行 + w/root 三行
# 换掉 def 之后的两行建控件方式
new_head = [
    "    def _build_work_tab(self) -> QWidget:",
    "        w = QWidget()",
    "        root = QVBoxLayout(w)",
    "        root.setContentsMargins(10, 10, 10, 10)",
    "        root.setSpacing(8)",
    "",
    "        # 上下可拖：上半是「工程 / 识别 / 模式」，下半是「对比表 + 日志」。",
    "        # 以前全塞在一个纵向布局里，表格只能分到很矮的一条。",
    "        self.vsplit = QSplitter(Qt.Orientation.Vertical)",
    "        self.vsplit.setChildrenCollapsible(False)",
    "        top = QWidget()",
    "        root_top = QVBoxLayout(top)",
    "        root_top.setContentsMargins(0, 0, 0, 0)",
    "        root_top.setSpacing(8)",
    "        bottom = QWidget()",
    "        root_bot = QVBoxLayout(bottom)",
    "        root_bot.setContentsMargins(0, 0, 0, 0)",
    "        root_bot.setSpacing(6)",
]
body = lines[106:395]           # 到 return 之前
body = [l.replace("root.addWidget(", "root_top.addWidget(")
          .replace("root.addLayout(", "root_top.addLayout(") for l in body]
tail = [
    "        root_bot.addWidget(self.split, 1)",
    "        self.vsplit.addWidget(top)",
    "        self.vsplit.addWidget(bottom)",
    "        self.vsplit.setStretchFactor(0, 0)",
    "        self.vsplit.setStretchFactor(1, 1)",
    "        self.vsplit.setSizes([520, 640])",
    "        root.addWidget(self.vsplit, 1)",
    "        return w",
]
new_lines = lines[:101] + new_head + body + tail + lines[395 + 2:]  # 395 是 return 之前一行
src2 = "\n".join(new_lines)

# ---------- 2. 表格更好用：更高、列宽更合理、行高、可复制 ----------
src2 = src2.replace('''        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 84)
        self.table.setColumnWidth(2, 105)
        self.table.setColumnWidth(3, 105)
        self.table.setColumnWidth(4, 62)''',
'''        self.table.setMinimumHeight(300)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 78)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(3, 112)
        self.table.setColumnWidth(4, 54)
        self.table.setAnimated(False)
        self.table.setIndentation(12)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_menu)''', 1)

# 日志默认窄一点
src2 = src2.replace("self.split.setSizes([780, 480])", "self.split.setSizes([880, 460])", 1)

# ---------- 3. 顶部两块表降高，让位给对比表 ----------
src2 = src2.replace("self.obj_tree.setMinimumHeight(120)", "self.obj_tree.setMinimumHeight(96)\n        self.obj_tree.setMaximumHeight(150)", 1)
src2 = src2.replace("self.deriv_tree.setMinimumHeight(110)", "self.deriv_tree.setMinimumHeight(96)\n        self.deriv_tree.setMaximumHeight(170)", 1)

io.open(p, "w", encoding="utf-8").write(src2)
print("工作台改为上下可拖 + 表格加高")
