"""「特殊模式」选择对话框：每一项都是「跟随工程 / 具体值」，默认什么都不改。

这些开关在 Bambu Studio 的「其他」页里，影响的是切片器的整体行为（逐件打印、
螺旋花瓶、圆弧拟合、磨砂皮肤……）。猜错一次就是废件，所以一律由用户自己勾。
"""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QScrollArea, QVBoxLayout, QWidget)


class SpecialDialog(QDialog):
    def __init__(self, options: list[dict], current: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("特殊模式（全部留空 = 一个都不改）")
        self.resize(720, 520)
        self._boxes: dict[str, QComboBox] = {}
        cur = current or {}

        outer = QVBoxLayout(self)
        tip = QLabel(
            "这些是 Bambu Studio「其他」页里的开关。**默认全部「跟随工程」**，"
            "这里只写你亲手选的项；软件不会替你开任何一项。")
        tip.setWordWrap(True)
        tip.setObjectName("muted")
        outer.addWidget(tip)

        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        for item in options:
            box = QComboBox()
            box.addItem("跟随工程（不改）", "keep")
            for value, label in item["choices"]:
                box.addItem(label, value)
            idx = box.findData(str(cur.get(item["key"], "keep")))
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if item.get("help"):
                box.setToolTip(item["help"])
            self._boxes[item["key"]] = box
            label = QLabel(item["label"])
            label.setToolTip(item.get("help", ""))
            form.addRow(label, box)
            if item.get("help"):
                hint = QLabel(item["help"])
                hint.setObjectName("muted")
                hint.setWordWrap(True)
                form.addRow("", hint)
        area.setWidget(inner)
        outer.addWidget(area, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def selections(self) -> dict[str, str]:
        """只返回用户真正选过的项（keep 的不返回）。"""
        out = {}
        for key, box in self._boxes.items():
            value = box.currentData()
            if value not in (None, "", "keep"):
                out[key] = value
        return out
