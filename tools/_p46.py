import io

p = "BambuSmartTuner.spec"
s = io.open(p, encoding="utf-8").read()
old = '    (str(RULES / "BambuRules.json"), "rules"),'
new = ('    (str(RULES / "BambuRules.json"), "rules"),\n'
       '    # Studio 参数位置对照表（「改了我找不到」用）\n'
       '    (str(ROOT / "data" / "studio_ui.json"), "data"),')
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("spec 已加 data/studio_ui.json")
