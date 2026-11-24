import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old = """                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)
                else:
                    # 支撑没开：把上游（形状层/几何层）可能留下的 support_* 改动撤回，
                    # 一个支撑键都不写 —— 否则会出现「没开支撑却改了支撑间隙」的噪音
                    for k in [k for k in list(values) if support_model.is_support_key(k)]:
                        values.pop(k, None)
                        reasons.pop(k, None)"""

new = """                # 支撑参数的唯一决策者是 core/support_model.py：
                # 上游（形状层/几何层/support_plan）留下的 support_* 改动一律先清掉，
                # 只保留「要不要支撑」与「悬垂判定角」两个决策，再由本层重算定量值。
                allowed = set(su.ops) | {"enable_support", "support_threshold_angle"}
                for k in [k for k in list(values) if support_model.is_support_key(k)]:
                    if k not in allowed:
                        values.pop(k, None)
                        reasons.pop(k, None)
                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)"""

assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("引擎：支撑键单一来源已强制")
