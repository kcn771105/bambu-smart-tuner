import io
import re

p = "tools/_patch_flow_nozzle.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace('old_imp = "from . import modes as mode_registry"',
              'old_imp = "from . import estimator, hardware, modes as modes_registry, schema, scope"')
s = s.replace('s = s.replace(old_imp, old_imp + "\\nfrom . import nozzle_flow", 1)',
              's = s.replace(old_imp,\n                      old_imp.replace("estimator, hardware", "estimator, hardware, nozzle_flow"), 1)')
io.open(p, "w", encoding="utf-8").write(s)
print("fixed anchor")
