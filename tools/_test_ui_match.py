"""键名 ↔ Studio UI 条目名的模糊匹配率测试（英文条目名归一后比键名）。"""
import gettext
import io
import re
import sys

sys.path.insert(0, ".")
from core import schema, scope

MO = r"C:\Program Files\Bambu Studio\resources\i18n\zh_CN\BambuStudio.mo"
with io.open(MO, "rb") as f:
    cat = gettext.GNUTranslations(f)._catalog

pairs = [(k, v) for k, v in cat.items()
         if isinstance(k, str) and isinstance(v, str) and k and v and k != v]


def norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return re.sub(r"\s+", " ", s)


by_norm: dict[str, tuple[str, str]] = {}
for en, zh in pairs:
    by_norm.setdefault(norm(en), (en, zh))

keys = [k for k, s in schema.PARAMS.items() if scope.SCOPE.get(k) == "process"]
exact, partial, miss = [], [], []
for k in keys:
    nk = norm(k.replace("_", " "))
    if nk in by_norm:
        exact.append((k,) + by_norm[nk])
        continue
    # 允许「主词 + 修饰词」互换：用词集合找唯一的最短候选
    words = set(nk.split())
    cands = [(en, zh) for n, (en, zh) in by_norm.items()
             if words and words <= set(n.split()) and len(n.split()) <= len(words) + 2]
    if len(cands) == 1:
        partial.append((k,) + cands[0])
    else:
        miss.append(k)

print(f"工艺键 {len(keys)}：精确 {len(exact)}，词集唯一 {len(partial)}，未匹配 {len(miss)}")
print(f"合计命中 {len(exact) + len(partial)} = {(len(exact) + len(partial)) / len(keys):.0%}")
print("\n精确命中样例：")
for k, en, zh in exact[:12]:
    print(f"  {k:32} → {en:34} {zh}")
print("\n词集命中样例：")
for k, en, zh in partial[:12]:
    print(f"  {k:32} → {en:34} {zh}")
print("\n未匹配前 20：", miss[:20])
