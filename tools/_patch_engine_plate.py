"""引擎接入打印板同步（第 7.8 层）+ OptResult.plate。"""
import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1. 插 7.8 层（在 7.7 结束之后、8a 钳制之前）
anchor = """        # ---- 8a：参数自身合法区间
        self._clamp_schema(values, reasons, warnings)"""

block = '''        # ---- 7.8：打印板同步（板型兼容性 / 板面尺寸 / 模型放得下吗）
        # 板型与板面都在机器页、耗材页 —— 只读不写。这一层做三件事：
        #   ① 用官方温度判断「这条料能不能在这块板上打」（温度 0 = 不支持）
        #   ② 板面尺寸与机型官方值对不上就报警（机型识别错 / 工程来自别的机器）
        #   ③ 按板型给几条工艺微调（写在 rules 的 plates 段，可自己改）
        try:
            from . import plate as plate_mod
            pinfo = plate_mod.read(self._project_for_plate, self.rules) \\
                if self._project_for_plate is not None else None
            if pinfo is not None:
                pw, pn, pops = plate_mod.check(
                    pinfo, rules=self.rules, printer_key=printer_key,
                    filament_key=filament_key, profile=model_profile)
                warnings.extend(pw)
                notes.extend(pn)
                if pops:
                    self._apply_ops(values, reasons, pops,
                                    "打印板（板型）适配", warnings,
                                    respect_locked=True)
                self._plate_info = pinfo.summary_line()
        except Exception as exc:            # 板层出错不能影响主流程
            warnings.append(f"打印板适配计算失败（已跳过该项）：{exc}")

        # ---- 8a：参数自身合法区间
        self._clamp_schema(values, reasons, warnings)'''

assert anchor in s
s = s.replace(anchor, block, 1)

# ---- 2. __init__ / optimize 里重置 _plate_info
s = s.replace("        self._derivations: list[dict] = []",
              "        self._derivations: list[dict] = []\n        self._plate_info: str = \"\"\n"
              "        self._project_for_plate = None", 1)
s = s.replace("        self._derivations = []",
              "        self._derivations = []\n        self._plate_info = \"\"", 1)

# ---- 3. OptResult 增 plate 字段
s = s.replace("""    #: 工程喷嘴 vs 当前选择的喷嘴（不同就说明流量做过折算）
    project_nozzle: float | None = None""",
"""    #: 工程喷嘴 vs 当前选择的喷嘴（不同就说明流量做过折算）
    project_nozzle: float | None = None
    #: 打印板同步结果（板型 / 温度 / 板面 / 兼容性），给 UI 与报告展示
    plate: str = \"\"""", 1)

s = s.replace("""            flow_limit=self._flow_limit,
            project_nozzle=(hw.nozzle_diameter if hw else None),
        )""",
"""            flow_limit=self._flow_limit,
            project_nozzle=(hw.nozzle_diameter if hw else None),
            plate=self._plate_info,
        )""", 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎接入打印板层")
