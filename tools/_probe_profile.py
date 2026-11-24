import io
import re

src = io.open("core/model_analysis.py", encoding="utf-8").read()
print("=== dataclass fields ===")
for m in re.finditer(r"^\s{4}(\w+):\s*([\w\[\]\., ]+)", src, re.M):
    print("  ", m.group(1), ":", m.group(2))
print("=== derived props ===")
for m in re.finditer(r"def (\w+)\(self\)", src):
    print("  ", m.group(1))
