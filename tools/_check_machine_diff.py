"""临时工具：逐机型打印官方参照预设的差异项，确认预设名解析正确。"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import schema, scope

BBL = pathlib.Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL")


def find(name):
    for sub in ("process", "filament", "machine"):
        p = BBL / sub / f"{name}.json"
        if p.exists():
            return p
    return None


def resolve(name):
    path = find(name)
    if path is None:
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    out = resolve(d.get("inherits")) if d.get("inherits") else {}
    out.update({k: v for k, v in d.items() if k != "inherits"})
    return out


def proc(src):
    out = {}
    for k, v in src.items():
        if k in schema.PARAMS and scope.scope_of(k) == scope.PROCESS:
            out[k] = v
    return out


REF = "0.20mm Standard @BBL X1C"
ref = proc(resolve(REF) or {})
print(f"参照 {REF}: {len(ref)} 个工艺页键")

for name in ["0.20mm Standard @BBL X1C", "0.20mm Standard @BBL X1",
             "0.20mm Standard @BBL P1P", "0.20mm Standard @BBL P1S",
             "0.20mm Standard @BBL P2S", "0.20mm Standard @BBL P2P",
             "0.20mm Standard @BBL A1", "0.20mm Standard @BBL A1M",
             "0.20mm Standard @BBL H2D", "0.20mm Standard @BBL H2S"]:
    src = resolve(name)
    if src is None:
        print(f"!! 找不到预设 {name}")
        continue
    cur = proc(src)
    diff = {k: v for k, v in cur.items() if ref.get(k) != v}
    print(f"--- {name}: {len(cur)} 键, 与参照差异 {len(diff)}")
    for k, v in sorted(diff.items()):
        print(f"      {k}: 参照={ref.get(k)!r} → 本机={v!r}")
