import io

p = "core/hotend.py"
s = io.open(p, encoding="utf-8").read()

if "import json" not in s:
    s = s.replace("from __future__ import annotations", "from __future__ import annotations\n\nimport json", 1)

anchor = "def factor("
add = '''def slot_count(settings: dict) -> int:
    """本工程「按热端变体分槽」的数组有几个槽位。

    依据 print_extruder_variant / printer_extruder_variant 的条目数：
        P2S: ["Direct Drive Standard", "Direct Drive High Flow",
              "Direct Drive E3D High Flow"] -> 3
    没有这两个键的工程返回 0（表示不分槽，按标量处理）。
    """
    for key in ("print_extruder_variant", "printer_extruder_variant",
                "extruder_variant_list"):
        raw = (settings or {}).get(key)
        if not raw:
            continue
        try:
            val = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            continue
        if isinstance(val, list) and len(val) > 1:
            return len(val)
    return 0


'''
if "def slot_count(" not in s:
    assert anchor in s
    s = s.replace(anchor, add + anchor, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("hotend.slot_count 已加")
