"""临时工具：检查 rules/BambuRules.json 各层里的归属分布与可疑键。"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import schema, scope

ROOT = pathlib.Path(__file__).resolve().parents[1]
rules = json.loads((ROOT / "rules" / "BambuRules.json").read_text(encoding="utf-8"))


def report(title, mapping):
    by = {}
    for k in mapping:
        by.setdefault(scope.scope_of(k), []).append(k)
    print(f"--- {title}：{len(mapping)} 键")
    for sc, ks in sorted(by.items()):
        print(f"    {sc:9s} {len(ks):3d}")
    return by


d = report("defaults", rules["defaults"])
for sc, ks in sorted(d.items()):
    if sc != "process":
        print(f"    ! defaults 里的 {sc} 键: {ks}")

for pk, node in rules["printers"].items():
    b = node.get("baseline", {})
    by = {}
    for k in b:
        by.setdefault(scope.scope_of(k), []).append(k)
    odd = {sc: ks for sc, ks in by.items() if sc != "process"}
    print(f"--- printers.{pk}.baseline: {len(b)} 键  非工艺页: {odd}")

for fk, node in rules["filaments"].items():
    b = node.get("baseline", {})
    by = {}
    for k in b:
        by.setdefault(scope.scope_of(k), []).append(k)
    print(f"--- filaments.{fk}.baseline: {len(b)} 键  {[(sc, len(ks)) for sc, ks in sorted(by.items())]}")
    print(f"      limits: {node.get('limits')}")
    for k, v in b.items():
        if scope.scope_of(k) == "process":
            print(f"      (工艺页) {k} = {v!r}")

print()
print("modes 各档触及的归属:")
for mk, node in rules["modes"].items():
    by = {}
    for k in node.get("ops", {}):
        by.setdefault(scope.scope_of(k), []).append(k)
    print(f"  {mk}: {[(sc, len(ks)) for sc, ks in sorted(by.items())]}")
    for sc, ks in sorted(by.items()):
        if sc != "process":
            print(f"      ! {sc}: {ks}")

print()
print("interactions 里非工艺页的键:")
for it in rules["interactions"]:
    bad = [k for k in list((it.get("set") or {})) + list((it.get("ops") or {}))
           if scope.scope_of(k) != "process"]
    if bad:
        print(f"  {it.get('id')}: {bad}")
