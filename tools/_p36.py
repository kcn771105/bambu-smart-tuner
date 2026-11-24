import io

p = "core/support_model.py"
s = io.open(p, encoding="utf-8").read()

old = '''    overhang_area = float(getattr(profile, "overhang_area", 0) or 0)
    height = float(getattr(profile, "size_z", 0) or 0)
    slender = float(getattr(profile, "slender", 0) or 0)
    foot = float(getattr(profile, "footprint", 0) or 0)
'''
new = '''    overhang_area = _total(profile, "overhang_area")
    height = float(getattr(profile, "size_z", 0) or getattr(profile, "height", 0) or 0)
    slender = float(getattr(profile, "slender", 0) or 0)
    foot = _total(profile, "footprint")
'''
assert old in s
s = s.replace(old, new, 1)

helper = '''def _total(profile, name: str) -> float:
    """ModelProfile 是逐件聚合视图，不一定直接暴露逐件属性（如 overhang_area）。

    有就算自己的，没有就把每件的加起来 —— 支撑密度取决于全盘悬垂总量，
    不能因为聚合类没这个字段就退化成 0。
    """
    v = getattr(profile, name, None)
    try:
        if v is not None and float(v) > 0:
            return float(v)
    except (TypeError, ValueError):
        pass
    objs = getattr(profile, "objects", None) or []
    total = 0.0
    for o in objs:
        try:
            total += float(getattr(o, name, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def spacing_for('''
s = s.replace("def spacing_for(", helper, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("support_model 增加逐件聚合")
