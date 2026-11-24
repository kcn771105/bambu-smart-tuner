import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old = """            policy=policy, hardware=hw,
            derivations=list(self._derivations),
        )"""
new = """            policy=policy, hardware=hw,
            derivations=list(self._derivations),
            flow_limit=self._flow_limit,
            project_nozzle=(hw.nozzle_diameter if hw else None),
        )"""
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("OptResult 填充 flow_limit")
