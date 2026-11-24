import io

# ---- 1. plate.read 支持 dict（引擎手里只有 settings 字典，没有 project 对象）
p = "core/plate.py"
s = io.open(p, encoding="utf-8").read()
old = '''def read(project, rules: dict | None = None) -> PlateInfo:
    """从工程里读出板型与板面。读不到就留空，由上层决定回退。"""
    s = project.settings'''
new = '''def read(project, rules: dict | None = None) -> PlateInfo:
    """从工程（或直接给 settings 字典）读出板型与板面。"""
    s = getattr(project, "settings", None)
    if s is None:
        s = project or {}'''
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("plate.read 兼容 dict")

# ---- 2. 引擎：把 current 存起来给 7.8 层用
p2 = "core/rules_engine.py"
e = io.open(p2, encoding="utf-8").read()
old2 = '''            pinfo = plate_mod.read(self._project_for_plate, self.rules) \\
                if self._project_for_plate is not None else None'''
new2 = '''            pinfo = plate_mod.read(self._project_for_plate or {}, self.rules)'''
assert old2 in e
e = e.replace(old2, new2, 1)

old3 = '''        self._derivations = []
        self._plate_info = ""'''
new3 = '''        self._derivations = []
        self._plate_info = ""
        self._project_for_plate = current'''
assert old3 in e
e = e.replace(old3, new3, 1)
io.open(p2, "w", encoding="utf-8").write(e)
print("引擎存 current 给板层")
