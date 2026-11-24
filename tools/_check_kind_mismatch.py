"""临时工具：比对真实工程里每个键的存储形态与 schema 声明的 kind 是否一致。

不一致的后果：
  - parse_value 返回 None → 引擎读不到用户当前值（用户值丢失、对比表显示「—」）
  - format_value 按标量格式化 → 写回形态与工程原形态不一致
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import schema, threemf  # noqa: E402

PROJ = pathlib.Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
SAMPLE = ROOT / "tools" / "_sample_check.3mf"


def audit(proj, tag):
    print(f"\n===== {tag} =====")
    proj = threemf.ThreeMfProject.load(proj)
    bad = []
    unparsed = []
    for key, raw in proj.settings.items():
        s = schema.spec(key)
        if s is None:
            continue
        is_list = isinstance(proj.kinds.get(key), str) and proj.kinds[key] == "list"
        declared_array = s.kind in schema.ARRAY_KINDS
        if is_list != declared_array:
            bad.append((key, s.kind, proj.kinds.get(key), str(raw)[:36]))
        if schema.parse_value(s, raw) is None and raw not in (None, "", "[]"):
            unparsed.append((key, s.kind, str(raw)[:36]))
    print(f"形态不一致 {len(bad)} 个：")
    for k, kind, real, raw in bad:
        print(f"   {k:38s} schema={kind:12s} 实际={real:6s} raw={raw}")
    print(f"解析失败（parse_value → None）{len(unparsed)} 个：")
    for k, kind, raw in unparsed:
        print(f"   {k:38s} schema={kind:12s} raw={raw}")
    return bad, unparsed


if __name__ == "__main__":
    audit(PROJ, "真实工程 P2S+PETG")
