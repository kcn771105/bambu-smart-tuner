import io

p = "core/report.py"
s = io.open(p, encoding="utf-8").read()

anchor = """    if result.blocked:
        add("## 只读参数（按要求原样保留）")"""

block = '''    derivs = getattr(result, "derivations", None) or []
    if derivs:
        add("## 按模型实测尺寸推导")
        add("")
        add("这一节是「凭什么这么调」的硬依据：每条都由模型自己的尺寸算出来，"
            "不是套模板。公式列可以直接手算复核。")
        add("")
        add("| 指标 | 实测 | 公式 | 结论 |")
        add("| --- | --- | --- | --- |")
        for d in derivs:
            add(f"| {d.get('metric', '')} | {d.get('measured', '')} | "
                f"{str(d.get('formula', '')).replace('|', '／')} | "
                f"{str(d.get('conclusion', '')).replace('|', '／')} |")
        add("")

'''

assert anchor in s, "blocked anchor not found"
s = s.replace(anchor, block + anchor, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("patched report")
