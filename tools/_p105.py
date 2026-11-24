import io

# 1) spec 用裁剪后的 donate.png
p = "BambuSmartTuner.spec"
s = io.open(p, encoding="utf-8").read()
s = s.replace('(str(ASSETS / "donate.jpg"), "assets"),', '(str(ASSETS / "donate.png"), "assets"),')
io.open(p, "w", encoding="utf-8").write(s)
print("spec → donate.png")

# 2) UI 优先 donate.png，并且显示大一点（保证手机能扫到）
p2 = "ui/main_window.py"
t = io.open(p2, encoding="utf-8").read()
t = t.replace('img = self._asset_path("donate.jpg")',
              'img = self._asset_path("donate.png") or self._asset_path("donate.jpg")')
t = t.replace('if pix.width() > 300:\n                    pix = pix.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)',
              'if pix.width() > 340:\n                    pix = pix.scaledToWidth(340, Qt.TransformationMode.SmoothTransformation)')
io.open(p2, "w", encoding="utf-8").write(t)
print("UI → donate.png + 340px")
