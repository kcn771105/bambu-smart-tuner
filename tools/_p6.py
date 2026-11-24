import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

old = """        self.chk_timecap.stateChanged.connect(lambda *_: self._reoptimize())
        row1.addWidget(self.chk_timecap)"""
new = """        self.chk_timecap.setChecked(True)   # 默认按时长预算回调，否则均衡档会算出 +78% 的时长
        self.chk_timecap.stateChanged.connect(lambda *_: self._reoptimize())
        row1.addWidget(self.chk_timecap)"""

assert old in s, "timecap connect not found"
s = s.replace(old, new)
io.open(p, "w", encoding="utf-8").write(s)
print("timecap 默认勾选")
