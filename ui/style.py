"""界面外观：一份 QSS + 少量字体设置。功能优先，不做花哨效果。"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"

QSS = """
QWidget {
    background: #f5f6f8;
    color: #1f2937;
    font-size: 13px;
}
QMainWindow, QDialog { background: #f5f6f8; }

QTabWidget::pane {
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    padding: 8px 20px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: #4b5563;
}
QTabBar::tab:selected {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-bottom-color: #ffffff;
    color: #111827;
    font-weight: 600;
}
QTabBar::tab:hover:!selected { color: #111827; }

QGroupBox {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    margin-top: 16px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #111827;
    background: #f5f6f8;
}

QLabel { background: transparent; }
QLabel#h1 { font-size: 17px; font-weight: 700; color: #111827; }
QLabel#muted { color: #6b7280; }
QLabel#warn {
    background: #fff8e6;
    border: 1px solid #ffd591;
    border-radius: 6px;
    color: #ad6800;
    padding: 6px 8px;
}
QLabel#ok {
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    border-radius: 6px;
    color: #047857;
    padding: 6px 8px;
}
QLabel#pill {
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 10px;
    color: #3730a3;
    padding: 2px 10px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #bfdbfe;
    selection-color: #111827;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #2563eb; }
QLineEdit:disabled, QComboBox:disabled { background: #f3f4f6; color: #9aa4b2; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    selection-background-color: #eff6ff;
    selection-color: #111827;
    outline: none;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    padding: 6px 14px;
    color: #1f2937;
}
QPushButton:hover { background: #f2f4f7; }
QPushButton:pressed { background: #e9edf2; }
QPushButton:disabled { color: #9aa4b2; background: #f7f8fa; border-color: #e4e7ec; }
QPushButton#primary {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 18px;
}
QPushButton#primary:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#primary:disabled { background: #c7d2fe; border-color: #c7d2fe; color: #ffffff; }
QPushButton#link {
    border: none;
    background: transparent;
    color: #2563eb;
    padding: 2px 4px;
}

QRadioButton { padding: 4px 2px; background: transparent; }
QCheckBox { background: transparent; }

QTreeWidget, QTableWidget, QListWidget {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    gridline-color: #f0f2f5;
    alternate-background-color: #fafbfc;
    selection-background-color: #eff6ff;
    selection-color: #111827;
    outline: none;
}
QTreeWidget::item, QTableWidget::item { padding: 3px 2px; }
QHeaderView::section {
    background: #f3f4f6;
    border: none;
    border-bottom: 1px solid #e4e7ec;
    border-right: 1px solid #eef1f4;
    padding: 6px 8px;
    color: #374151;
    font-weight: 600;
}
QTableCornerButton::section { background: #f3f4f6; border: none; }

QTextEdit, QPlainTextEdit, QTextBrowser {
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    padding: 6px;
}
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #d0d5dd; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #b6bec9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #d0d5dd; border-radius: 5px; min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 8px; }

QStatusBar { background: #f5f6f8; color: #6b7280; }
QStatusBar::item { border: none; }

QToolTip {
    background: #111827; color: #ffffff; border: none;
    padding: 4px 6px; border-radius: 4px;
}
"""


def apply_theme(app: QApplication) -> None:
    """统一字体 + 配色。字体按 Windows 常见顺序回退。"""
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Noto Sans CJK SC"):
        f = QFont(family, 9)
        if QFont(f).exactMatch() or family == "Microsoft YaHei UI":
            app.setFont(QFont(family, 9))
            break
    app.setStyleSheet(QSS)
