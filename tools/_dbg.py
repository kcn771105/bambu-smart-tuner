import io

p = "tools/gen_studio_ui.py"
s = io.open(p, encoding="utf-8").read()
for needle in ('"enable_support": (', '"bridge_angle": ('):
    i = s.find(needle)
    print(needle, "→", i)
print("总长度", len(s))
i = s.find("seam_position")
print("seam_position 上下文:", repr(s[max(0, i - 120):i + 60]))
