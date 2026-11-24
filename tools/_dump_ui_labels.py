"""从 Bambu Studio 的 zh_CN .mo 里抽出「英文 UI 名 → 中文 UI 名」，并核对我们的键中文名。

用法：
    python tools/_dump_ui_labels.py            # 输出统计 + 样例
"""
import gettext
import io
import json
import sys

sys.path.insert(0, ".")
from core import schema, scope

MO = r"C:\Program Files\Bambu Studio\resources\i18n\zh_CN\BambuStudio.mo"

with io.open(MO, "rb") as f:
    t = gettext.GNUTranslations(f)
catalog = t._catalog           # {msgid: msgstr}
print("mo 条目数：", len(catalog))

# 英文 UI 名 → 中文
en2zh = {k: v for k, v in catalog.items() if isinstance(k, str) and isinstance(v, str)
         and k and v and k != v}
print("可用英中对照：", len(en2zh))

zh2en: dict[str, str] = {}
for en, zh in en2zh.items():
    if len(zh) <= 30:
        zh2en.setdefault(zh, en)

print("中文 → 英文：", len(zh2en))

# 我们的键：中文名能不能在 mo 里找到对应英文条目
hit, miss = [], []
for k, s in schema.PARAMS.items():
    if scope.SCOPE.get(k) != "process":
        continue
    en = zh2en.get(s.label)
    (hit if en else miss).append((k, s.label, en or ""))

print(f"工艺键 {len(hit) + len(miss)}：mo 里能对上 {len(hit)}，对不上 {len(miss)}")
print("\n能对上的前 20 个：")
for k, zh, en in hit[:20]:
    print(f"  {k:34} {zh:16} ← {en}")
print("\n对不上的前 25 个：")
for k, zh, _ in miss[:25]:
    print(f"  {k:34} {zh}")
