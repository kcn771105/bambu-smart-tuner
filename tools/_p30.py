import io

p = "core/safety.py"
s = io.open(p, encoding="utf-8").read()

old = '''    for key, want in expected.items():
        got = data.get(key)
        if got is None:
            problems.append(f"{key}: 文件里没有这个键（期望 {want!r}）")
            continue
        # 数组按槽位比，字符串去空格
        if isinstance(got, list) or isinstance(want, list):'''
new = '''    for key, want in expected.items():
        got = data.get(key)
        if got is None:
            problems.append(f"{key}: 文件里没有这个键（期望 {want!r}）")
            continue
        # 引擎里数组型参数的期望值是一段 JSON 文本（'["179","500","500"]'），
        # 而文件里是真正的数组 —— 先统一形态，否则每条数组参数都会被误报。
        want = _as_value(want)
        # 数组按槽位比，字符串去空格
        if isinstance(got, list) or isinstance(want, list):'''
assert old in s
s = s.replace(old, new, 1)

helper = '''def _as_value(raw):
    """把引擎里的字符串形态还原成与文件同构的形态。

    ARRAY_* 类参数在引擎里是 JSON 文本（'["179", "500", "500"]'），
    文件里是数组。比对前必须统一，否则整片误报。
    """
    import json

    if not isinstance(raw, str):
        return raw
    txt = raw.strip()
    if txt[:1] in ("[", "{") and txt[-1:] in ("]", "}"):
        try:
            return json.loads(txt)
        except ValueError:
            return raw
    return raw


def fingerprint('''
s = s.replace("def fingerprint(", helper, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("self_check 支持 JSON 文本期望值")
