import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# 在 optimize 开头（hotend 检测之后）告知 schema 本工程的分槽槽位数量
old = """        self._hotend_mul, self._hotend_note = hotend.factor(self.rules, self._hotend.key)"""
new = """        # 分槽参数（outer_wall_speed 等）是按热端变体分槽的：先告诉 schema 有几个槽位，
        # 写回时才会把每个槽位都写上新值，否则 Studio 切到高流量热端读第 1 槽会「看起来没改」
        schema.set_variant_slots(hotend.slot_count(current))
        self._hotend_mul, self._hotend_note = hotend.factor(self.rules, self._hotend.key)"""
assert old in s
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎：optimize 开头设置分槽槽位")
