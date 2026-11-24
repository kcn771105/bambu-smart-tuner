import io

p = "core/schema.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1) 模块级：按热端变体分槽的参数有几个槽位
anchor = "# ---------------------------------------------------------------- 值解析 / 格式化"
add = '''# ---------------------------------------------------------------- 值解析 / 格式化

#: 工程里「按热端变体分槽」的数组长度（print_extruder_variant 的条目数）。
#: 例：P2S 工程是 ["Direct Drive Standard","Direct Drive High Flow","Direct Drive E3D High Flow"]
#:     → 3 个槽位，outer_wall_speed 就是 ["200","500","500"]。
#: 这类键 Studio 显示的是「当前所选热端」那一槽的值，只改第 0 槽会出现
#: 「表里写了 124，Studio 里还是 500」——因为它读的是第 1 槽。
_VARIANT_SLOTS = 0

#: 分槽参数是否把所有槽位写成同一个值（默认写全，保证任何热端下都生效）
_WRITE_ALL_VARIANT_SLOTS = True


def set_variant_slots(n: int, *, write_all: bool | None = None) -> None:
    """告诉 schema：本工程的分槽参数有几个槽位（0 = 不知道，按单槽处理）。"""
    global _VARIANT_SLOTS, _WRITE_ALL_VARIANT_SLOTS
    _VARIANT_SLOTS = max(0, int(n or 0))
    if write_all is not None:
        _WRITE_ALL_VARIANT_SLOTS = bool(write_all)


def variant_slots() -> int:
    return _VARIANT_SLOTS

'''
assert anchor in s
s = s.replace(anchor, add, 1)

# ---- 2) format_value：分槽参数写满所有槽位
old = """    if as_array:
        out = [item]
        out.extend(slots[1:n])
        return json.dumps(out, separators=(", ", ": "))
    return item"""
new = """    if as_array:
        fill_all = (
            _WRITE_ALL_VARIANT_SLOTS
            and _VARIANT_SLOTS > 1
            and n == _VARIANT_SLOTS
            and s.kind in (ARRAY_FLOAT, ARRAY_PCT)
        )
        if fill_all:
            # 按热端变体分槽：把同一个值写进每一槽，否则 Studio 里切到高流量热端
            # 会读第 1 槽、看起来「参数没变」
            out = [item] * n
        else:
            out = [item]
            out.extend(slots[1:n])
        return json.dumps(out, separators=(", ", ": "))
    return item"""
assert old in s
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("schema：分槽参数支持整槽写入")
