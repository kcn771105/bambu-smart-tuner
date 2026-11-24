"""把 assets/donate.jpg 接进 UI：右上角按钮 + 收款码弹窗。"""
import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

if "def _show_donate(" in s:
    print("已存在 _show_donate")
else:
    anchor = "    # ================================================================ 文件"
    method = '''    # ---------------------------------------------------------------- 投喂作者

    def _asset_path(self, name: str) -> Path | None:
        """在「EXE 同目录 → _MEIPASS → 源码目录」里找一张图。"""
        cands = []
        try:
            import sys
            base = Path(sys.executable).resolve().parent
            cands.append(base / "assets" / name)
            mp = getattr(sys, "_MEIPASS", None)
            if mp:
                cands.append(Path(mp) / "assets" / name)
        except Exception:
            pass
        cands.append(Path(__file__).resolve().parent.parent / "assets" / name)
        for c in cands:
            if c.exists():
                return c
        return None

    def _show_donate(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("投喂作者")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        title = QLabel("请作者喝杯咖啡 ☕")
        f = QFont()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        tip = QLabel("如果这个工具帮你省了几个小时调参，\\n可以扫码随意打赏，金额无所谓。")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)

        img = self._asset_path("donate.jpg")
        if img is None:
            warn = QLabel("没找到收款码图片（assets/donate.jpg）。")
            warn.setStyleSheet("color:#b45309;")
            lay.addWidget(warn)
        else:
            pix = QPixmap(str(img))
            if pix.isNull():
                lay.addWidget(QLabel("收款码图片读不出来。"))
            else:
                if pix.width() > 300:
                    pix = pix.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
                pic = QLabel()
                pic.setPixmap(pix)
                pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(pic)

        note = QLabel("微信扫码 · 感谢支持")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        row.addWidget(btn)
        row.addStretch(1)
        lay.addLayout(row)

        dlg.exec()
        self._log("谢谢支持：投喂面板已打开过。", "ok")

'''
    assert anchor in s
    s = s.replace(anchor, method + anchor, 1)
    io.open(p, "w", encoding="utf-8").write(s)
    print("已加 _show_donate")
