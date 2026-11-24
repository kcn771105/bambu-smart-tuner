import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old = """                su = support_model.tune(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    values=dict(values))"""
new = """                su = support_model.tune(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    values=dict(values),
                    judge_angle=values.get("support_threshold_angle"),
                    nozzle=float(nozzle or 0.4),
                    line_width=_opt_num(values.get("line_width"), None),
                    max_speed=(hw.max_speed if hw else None))"""
assert old in s
s = s.replace(old, new, 1)

# 支撑关掉时把任何 support_* 写入都丢掉（防止上游形状/几何层留下噪音）
old2 = """                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)"""
new2 = """                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)
                else:
                    # 支撑没开：把上游可能留下的 support_* 改动全部撤回，一个键都不写
                    for k in [k for k in values if support_model.is_support_key(k)]:
                        if k not in _PRESERVE_UNTOUCHED:
                            values.pop(k, None)
                            reasons.pop(k, None)"""
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎 7.76 形参补齐 + 支撑关闭清理")
