import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1. 识别结果回填到热端下拉，并在日志里说明依据
old = """        idx = self.cmb_nozzle.findData(float(det.nozzle))
        self.cmb_nozzle.setCurrentIndex(idx if idx >= 0 else 1)
        self._suppress = False"""
new = """        idx = self.cmb_nozzle.findData(float(det.nozzle))
        self.cmb_nozzle.setCurrentIndex(idx if idx >= 0 else 1)
        # 热端流量类型：把工程里识别到的填进下拉（用户可改，改了就按新的算）
        self.hotend_info = hotend.detect(self.original_settings)
        hidx = self.cmb_hotend.findData(self.hotend_info.key)
        self.cmb_hotend.setCurrentIndex(hidx if hidx >= 0 else 0)
        self._suppress = False
        self._log("热端流量：" + self.hotend_info.summary_line(),
                  "info" if self.hotend_info.detected else "warn")"""
assert old in s
s = s.replace(old, new, 1)

# ---- 2. 真机同步面板显示流量类型
old2 = """        extra = []
        if getattr(self.result, "plate", ""):"""
if old2 not in s:
    # 找真实写法
    i = s.find("extra = [")
    print("extra 写法：", s[i:i+400])
    raise SystemExit(1)

s = s.replace(old2, """        extra = []
        if getattr(self.result, "hotend", ""):
            extra.append(self.result.hotend)
        if getattr(self.result, "plate", ""):""", 1)

io.open(p, "w", encoding="utf-8").write(s)
print("UI：识别回填 + 面板显示热端")
