import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old = """                su = support_model.tune(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    values=dict(values))"""
new = """                def _as_num(v, default=None):
                    try:
                        if isinstance(v, (list, tuple)):
                            v = v[0] if v else default
                        return float(str(v).strip().rstrip("%"))
                    except (TypeError, ValueError):
                        return default

                su = support_model.tune(
                    model_profile,
                    layer_height=_as_num(values.get("layer_height"), 0.2) or 0.2,
                    mode=mode_key,
                    values=dict(values),
                    judge_angle=_as_num(values.get("support_threshold_angle")),
                    nozzle=float(nozzle or 0.4),
                    line_width=_as_num(values.get("line_width")),
                    max_speed=(hw.max_speed if hw else None))"""
assert old in s
s = s.replace(old, new, 1)

old2 = """                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)"""
new2 = """                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)
                else:
                    # 支撑没开：把上游（形状层/几何层）可能留下的 support_* 改动撤回，
                    # 一个支撑键都不写 —— 否则会出现「没开支撑却改了支撑间隙」的噪音
                    for k in [k for k in list(values) if support_model.is_support_key(k)]:
                        values.pop(k, None)
                        reasons.pop(k, None)"""
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎 7.76 已补形参与清理")
