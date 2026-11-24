import io

p = "core/plate.py"
s = io.open(p, encoding="utf-8").read()

old = '''    # ---- 4. 板型相关的工艺微调（规则库 plates.items.<key>.process）
    items = ((rules or {}).get("plates") or {}).get("items") or {}
    node = items.get(plate.key) or {}
    for key, op in (node.get("process") or {}).items():
        ops[key] = dict(op)

    return warns, notes, ops'''

new = '''    # ---- 4. 板型相关的工艺微调（规则库 plates.items.<key>.process）
    # 只放「非 preserve」的键：preserve 的键（如 brim_width）是用户自己的值，
    # 引擎会静默跳过，写了也不生效，所以这类建议走文字 advice。
    items = ((rules or {}).get("plates") or {}).get("items") or {}
    node = items.get(plate.key) or {}
    for key, op in (node.get("process") or {}).items():
        ops[key] = dict(op)
    advice = str(node.get("advice") or "")
    if advice:
        notes.append(f"打印板建议（{plate.label}）：{advice}")

    return warns, notes, ops'''

assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("plate.check 增 advice")
