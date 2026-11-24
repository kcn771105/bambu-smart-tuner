import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# 1) OptResult 增 flow_limit
s = s.replace('''    #: 按模型实测尺寸的定量推导明细（指标 / 实测 / 公式 / 结论），UI 与报告直接展示
    derivations: list[dict] = field(default_factory=list)''',
'''    #: 按模型实测尺寸的定量推导明细（指标 / 实测 / 公式 / 结论），UI 与报告直接展示
    derivations: list[dict] = field(default_factory=list)
    #: 本次实际采用的体积流量上限 mm³/s（已按喷嘴折算过）
    flow_limit: float | None = None
    #: 工程喷嘴 vs 当前选择的喷嘴（不同就说明流量做过折算）
    project_nozzle: float | None = None''', 1)

io.open(p, "w", encoding="utf-8").write(s)
print("OptResult 扩字段")
