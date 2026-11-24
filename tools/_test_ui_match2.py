"""键名 ↔ Studio UI 条目名匹配 v2（停用词 + 双向包含 + 唯一最优）。

目标：给每个工艺键找到 Bambu Studio 界面上的条目名（英文 msgid + 中文译名），
这样用户能在 Studio 的搜索框里直接搜到它。
"""
import gettext
import io
import re
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from core import schema, scope

MO = r"C:\Program Files\Bambu Studio\resources\i18n\zh_CN\BambuStudio.mo"
with io.open(MO, "rb") as f:
    cat = gettext.GNUTranslations(f)._catalog

STOP = {"of", "the", "for", "and", "a", "an", "to", "in", "on", "with", "by",
        "maximum", "max", "minimum", "min", "enable", "use", "using", "when",
        "layer", "layers", "settings", "setting", "value", "only", "all"}


def words(s: str) -> frozenset:
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return frozenset(w for w in s.split() if w and w not in STOP)


pairs = [(k, v) for k, v in cat.items()
         if isinstance(k, str) and isinstance(v, str) and k and v and k != v]

index: dict[frozenset, list[tuple[str, str]]] = defaultdict(list)
for en, zh in pairs:
    w = words(en)
    if w:
        index[w].append((en, zh))
print("条目（去停用词后）：", len(index))

keys = [k for k, s in schema.PARAMS.items() if scope.SCOPE.get(k) == "process"]


def best(k: str):
    kw = words(k)
    if not kw:
        return None
    if kw in index and len(index[kw]) == 1:
        return index[kw][0], "exact"
    cands = []
    for cw, items in index.items():
        if not cw:
            continue
        inter = kw & cw
        if not inter:
            continue
        union = kw | cw
        if len(inter) / len(union) < 0.6:
            continue
        cands.append((len(union), items))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    top = cands[0]
    if len(cands) > 1 and cands[1][0] == top[0]:
        return None                      # 并列最优 → 不猜
    if len(top[1]) != 1:
        return None
    return top[1][0], "fuzzy"


hit = miss = 0
rows = []
for k in keys:
    b = best(k)
    if b:
        hit += 1
        rows.append((k,) + b[0] + (b[1],))
    else:
        miss += 1
print(f"工艺键 {len(keys)}：命中 {hit}（{hit / len(keys):.0%}），未匹配 {miss}")
print("\n样例：")
for k, en, zh, how in rows[:14]:
    print(f"  [{how:5}] {k:32} → {en:36} {zh}")
missed = [k for k in keys if not best(k)]
print("\n未匹配前 30：", missed[:30])
