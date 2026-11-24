import io

p = "core/plate.py"
s = io.open(p, encoding="utf-8").read()

# 1) 补 _as_list（hardware 里那份是私有的，这里独立实现）
old = '''def _num(val, idx: int = 0) -> float | None:'''
new = '''def _as_list(val) -> list:
    """工程里的数组可能是 list，也可能是 JSON 字符串或逗号分隔串。"""
    import json

    if val is None:
        return []
    if isinstance(val, list):
        return list(val)
    txt = str(val).strip()
    if not txt:
        return []
    if txt.startswith("["):
        try:
            v = json.loads(txt)
            if isinstance(v, list):
                return v
        except (ValueError, TypeError):
            pass
    return [txt]


def _num(val, idx: int = 0) -> float | None:'''
assert old in s
s = s.replace(old, new, 1)

# 2) 去掉那行没用的残留
old2 = '''    # ---- 机型官方板面
    bed = (((rules or {}).get("printers") or {}).get("_") or {}).get("bed")
    return info'''
new2 = '''    return info'''
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("plate.py 修好")
