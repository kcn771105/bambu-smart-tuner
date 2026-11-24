import io

p = "core/plate.py"
s = io.open(p, encoding="utf-8").read()

old = '''    # ---- 3. 模型放得下吗
    if profile is not None and plate.bed_w and plate.bed_d:
        objs = getattr(profile, "objects", None) or []
        for i, obj in enumerate(objs, 1):
            sx, sy = float(getattr(obj, "size_x", 0)), float(getattr(obj, "size_y", 0))
            if sx <= 0 or sy <= 0:
                continue
            fits_a = sx <= plate.bed_w + 1e-6 and sy <= plate.bed_d + 1e-6
            fits_b = sx <= plate.bed_d + 1e-6 and sy <= plate.bed_w + 1e-6
            if not (fits_a or fits_b):
                warns.append(
                    f"模型放不下：第 {i} 件 {sx:g} × {sy:g} mm，超过板面 "
                    f"{plate.bed_w:g} × {plate.bed_d:g} mm。请先在 Bambu Studio 里旋转/缩放，"
                    f"本程序不改模型几何。")'''

new = '''    # ---- 3. 模型放得下吗
    # 用「你选的那台机器」的官方板面判断（选错机型时这里也会暴露出来）；
    # 规则库里没有该机型板面时才退回工程 printable_area。
    fit_w = plate.expect_w or plate.bed_w
    fit_d = plate.expect_d or plate.bed_d
    if profile is not None and fit_w and fit_d:
        objs = getattr(profile, "objects", None) or []
        for i, obj in enumerate(objs, 1):
            sx, sy = float(getattr(obj, "size_x", 0)), float(getattr(obj, "size_y", 0))
            if sx <= 0 or sy <= 0:
                continue
            fits_a = sx <= fit_w + 1e-6 and sy <= fit_d + 1e-6
            fits_b = sx <= fit_d + 1e-6 and sy <= fit_w + 1e-6   # 旋转 90° 能不能放下
            if not (fits_a or fits_b):
                warns.append(
                    f"模型放不下：第 {i} 件 {sx:g} × {sy:g} mm，超过板面 "
                    f"{fit_w:g} × {fit_d:g} mm。请先在 Bambu Studio 里旋转/缩放，"
                    f"本程序不改模型几何。")'''

assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("模型放得下改用机型官方板面")
