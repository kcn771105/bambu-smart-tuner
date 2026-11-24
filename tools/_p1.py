import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

old = 'self.lbl_mode_hint = QLabel(MODE_HINT.get("balanced", ""))'
new = 'self.lbl_mode_hint = QLabel(self._mode_hint_text("balanced"))'
assert old in s, "hint init not found"
s = s.replace(old, new)

io.open(p, "w", encoding="utf-8").write(s)
print("patched hint init")
