import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# 1) 签名加 filament_key
s = s.replace('''                    nozzle: float | None = None,
                    project_nozzle: float | None = None) -> None:''',
'''                    nozzle: float | None = None,
                    project_nozzle: float | None = None,
                    filament_key: str = "") -> None:''', 1)

# 2) 查表用 filament_key 兜底（filament 节点里没有 key 字段，只有 label）
s = s.replace('''        noz_official, noz_src = nozzle_flow.limit(
            self.rules, group=group, filament_key=str(fnode.get("key") or ""),
            nozzle=nozzle)''',
'''        fkey = str(fnode.get("key") or filament_key or "")
        noz_official, noz_src = nozzle_flow.limit(
            self.rules, group=group, filament_key=fkey, nozzle=nozzle)''', 1)

s = s.replace('''            r, rsrc = nozzle_flow.ratio(
                self.rules, group=group, filament_key=str(fnode.get("key") or ""),
                from_nozzle=proj_noz, to_nozzle=pick_noz)''',
'''            r, rsrc = nozzle_flow.ratio(
                self.rules, group=group, filament_key=fkey,
                from_nozzle=proj_noz, to_nozzle=pick_noz)''', 1)

# 3) 两个调用点补 filament_key
s = s.replace('''                             printer_key=printer_key, nozzle=float(nozzle),
                             project_nozzle=(hw.nozzle_diameter if hw else None))''',
'''                             printer_key=printer_key, nozzle=float(nozzle),
                             project_nozzle=(hw.nozzle_diameter if hw else None),
                             filament_key=filament_key)''', 1)
s = s.replace('''                                 printer_key=printer_key, nozzle=float(nozzle),
                                 project_nozzle=(hw.nozzle_diameter if hw else None))''',
'''                                 printer_key=printer_key, nozzle=float(nozzle),
                                 project_nozzle=(hw.nozzle_diameter if hw else None),
                                 filament_key=filament_key)''', 1)

io.open(p, "w", encoding="utf-8").write(s)
print("done")
