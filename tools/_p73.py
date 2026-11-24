import io

p = "core/hotend.py"
s = io.open(p, encoding="utf-8").read()
anchor = "from __future__ import annotations"
assert anchor in s
if "\nimport json\n" not in s:
    s = s.replace(anchor, anchor + "\n\nimport json", 1)
io.open(p, "w", encoding="utf-8").write(s)
print("import json 已补：", "\nimport json\n" in s)
