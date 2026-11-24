import sys
sys.path.insert(0, r"F:\deep seek\bambu_smart_tuner")
from core import schema, scope
groups = sys.argv[1:] if len(sys.argv) > 1 else ["support", "seam", "ironing", "adhesion", "z", "wall", "quality", "infill"]
for k, s in schema.PARAMS.items():
    if s.group in groups:
        ch = s.choices if s.kind == "enum" else ""
        print("%-38s %-9s kind=%-10s [%.3g,%.3g] soft=%s pres=%s scope=%s %s" % (
            k, s.group, s.kind, s.vmin, s.vmax, s.soft, s.preserve, scope.scope_of(k), ch))
