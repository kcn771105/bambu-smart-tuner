import io

p = "core/adhesion.py"
s = io.open(p, encoding="utf-8").read()

# 1) 尊重「用户显式关了裙边」
old = '''    tip, off_ratio, small = risk_of(profile)'''
new = '''    cur = current or {}
    if str(cur.get("brim_type") or "") == "no_brim":
        out.reasons.append("工程里明确设了「不加裙边」，不动。")
        return out

    tip, off_ratio, small = risk_of(profile)'''
assert old in s
s = s.replace(old, new, 1)

# 2) 已经算出的宽度不再被上层形状层推高的值挡住：只认用户原始值
old2 = '''    cur = 0.0
    try:
        cur = float((current or {}).get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    # 已经有更宽的裙边就不往回压（用户可能是为了别的原因加的）
    if cur > width:'''
new2 = '''    cur = 0.0
    try:
        cur = float(cur.get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    # 用户原本就给了更宽的裙边 → 不往回压（他可能是为了别的原因加的）
    if cur > width:'''
assert old2 in s
s = s.replace(old2, new2, 1)

# 3) tune() 里也尊重 no_brim
old3 = '''    cur = 0.0
    try:
        cur = float((current or {}).get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    if cur > best.width:'''
new3 = '''    if str((current or {}).get("brim_type") or "") == "no_brim":
        notes.append("工程里明确设了「不加裙边」，不动。")
        return {}, notes, rows
    cur = 0.0
    try:
        cur = float((current or {}).get("brim_width") or 0)
    except (TypeError, ValueError):
        cur = 0.0
    if cur > best.width:'''
assert old3 in s
s = s.replace(old3, new3, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("adhesion 尊重 no_brim / 只认用户原始值")

# 4) 引擎传「用户原始值」而不是层层叠加后的 values
q = "core/rules_engine.py"
e = io.open(q, encoding="utf-8").read()
e = e.replace('''                    mode=mode_key,
                    current=dict(values))
                if ad_ops:''', '''                    mode=mode_key,
                    current={k: self._user_values.get(k, values.get(k))
                             for k in ("brim_width", "brim_type", "brim_object_gap")})
                if ad_ops:''', 1)
io.open(q, "w", encoding="utf-8").write(e)
print("引擎改为传用户原始裙边值")
