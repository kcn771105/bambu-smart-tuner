import io

p = "tests/test_hotend_safety.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("        from core import hardware", "        import io as _io\n        from core import hardware", 1)
s = s.replace('json.load(io.open("rules/BambuRules.json"', 'json.load(_io.open("rules/BambuRules.json"', 1)
io.open(p, "w", encoding="utf-8").write(s)
print("修好了 io 引用")
