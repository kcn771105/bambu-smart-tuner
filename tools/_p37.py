import io

# ---------- support_model：几何量兜底 ----------
p = "core/support_model.py"
s = io.open(p, encoding="utf-8").read()
old = '''    overhang_area = _total(profile, "overhang_area")
    height = float(getattr(profile, "size_z", 0) or getattr(profile, "height", 0) or 0)
    slender = float(getattr(profile, "slender", 0) or 0)
    foot = _total(profile, "footprint")
'''
new = '''    overhang_area = _total(profile, "overhang_area")
    height, foot, slender = _geom(profile)
'''
assert old in s
s = s.replace(old, new, 1)

helper = '''def _geom(profile) -> tuple[float, float, float]:
    """(高, 底面积, 细高比)。聚合类上的派生属性在手工构造的场景里可能是 0，逐件兜底。"""
    height = 0.0
    for name in ("size_z", "height"):
        try:
            height = max(height, float(getattr(profile, name, 0) or 0))
        except (TypeError, ValueError):
            pass
    foot = _total(profile, "footprint")
    for o in (getattr(profile, "objects", None) or []):
        try:
            height = max(height, float(getattr(o, "max_z", 0) or getattr(o, "size_z", 0) or 0))
        except (TypeError, ValueError):
            pass
    slender = 0.0
    if foot > 1e-9 and height > 0:
        slender = height / (foot ** 0.5)
    try:
        slender = max(slender, float(getattr(profile, "slender", 0) or 0))
    except (TypeError, ValueError):
        pass
    return height, foot, slender


def _total(profile, name: str) -> float:'''
s = s.replace("def _total(profile, name: str) -> float:", helper, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("support_model 几何量兜底")

# ---------- adhesion：同一套兜底 ----------
q = "core/adhesion.py"
a = io.open(q, encoding="utf-8").read()
old2 = '''    height = float(getattr(profile, "size_z", 0) or 0)
    foot = float(getattr(profile, "footprint", 0) or 0)
'''
new2 = '''    height, foot = _h_f(profile)
'''
assert old2 in a
a = a.replace(old2, new2, 1)

old3 = '''def risk_of(p) -> tuple[float, float, bool]:'''
new3 = '''def _h_f(p) -> tuple[float, float]:
    """(高, 底面积)。聚合对象上这两个派生属性可能为 0 → 逐件兜底。"""
    height = 0.0
    for name in ("size_z", "height"):
        try:
            height = max(height, float(getattr(p, name, 0) or 0))
        except (TypeError, ValueError):
            pass
    foot = 0.0
    objs = getattr(p, "objects", None) or []
    if objs:
        for o in objs:
            try:
                foot += float(getattr(o, "footprint", 0) or 0)
                height = max(height, float(getattr(o, "max_z", 0) or 0))
            except (TypeError, ValueError):
                continue
    if foot <= 1e-9:
        try:
            foot = float(getattr(p, "footprint", 0) or 0)
        except (TypeError, ValueError):
            foot = 0.0
    return height, foot


def _vol(p) -> float:
    try:
        v = float(getattr(p, "volume", 0) or 0)
    except (TypeError, ValueError):
        v = 0.0
    if v > 0:
        return v
    total = 0.0
    for o in (getattr(p, "objects", None) or []):
        try:
            total += float(getattr(o, "volume", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def risk_of(p) -> tuple[float, float, bool]:'''
a = a.replace(old3, new3, 1)

# risk_of 内部也用兜底
a = a.replace('''    height = float(getattr(p, "size_z", 0) or 0)
    foot = float(getattr(p, "footprint", 0) or 0)
    if height <= 0 or foot <= 0:
        return 0.0, 0.0, False''',
'''    height, foot = _h_f(p)
    if height <= 0 or foot <= 0:
        return 0.0, 0.0, False''', 1)
a = a.replace('''    vol = float(getattr(p, "volume", 0) or 0)''',
              '''    vol = _vol(p)''', 1)
io.open(q, "w", encoding="utf-8").write(a)
print("adhesion 几何量兜底")
