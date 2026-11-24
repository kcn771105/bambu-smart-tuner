import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

a = """            self._clamp_flow(values, reasons, pnode, fnode, warnings,
                             overlay_max=overlay_max,
                             project_max=(hw.max_volumetric_speed if hw else None),
                             printer_key=printer_key)"""
b = """            self._clamp_flow(values, reasons, pnode, fnode, warnings,
                             overlay_max=overlay_max,
                             project_max=(hw.max_volumetric_speed if hw else None),
                             printer_key=printer_key, nozzle=float(nozzle),
                             project_nozzle=(hw.nozzle_diameter if hw else None))"""

c = """                self._clamp_flow(values, reasons, pnode, fnode, [],
                                 overlay_max=(filament_overlay or {}).get("limits", {}).get("max_volumetric_speed"),
                                 project_max=(hw.max_volumetric_speed if hw else None),
                                 printer_key=printer_key)"""
d = """                self._clamp_flow(values, reasons, pnode, fnode, [],
                                 overlay_max=(filament_overlay or {}).get("limits", {}).get("max_volumetric_speed"),
                                 project_max=(hw.max_volumetric_speed if hw else None),
                                 printer_key=printer_key, nozzle=float(nozzle),
                                 project_nozzle=(hw.nozzle_diameter if hw else None))"""

for old, new, tag in ((a, b, "call#1"), (c, d, "call#2")):
    if old in s:
        s = s.replace(old, new, 1)
        print("patched", tag)
    else:
        print("MISS", tag)

io.open(p, "w", encoding="utf-8").write(s)
