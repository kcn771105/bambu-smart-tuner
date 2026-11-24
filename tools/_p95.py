import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

# 1) 在 7.76 之前初始化白名单
old_head = """            # ---- 7.76：支撑按模型尺寸定量（密度/间隙/安全距/形态）
            if model_profile is not None:"""
new_head = """            # ---- 7.76：支撑按模型尺寸定量（密度/间隙/安全距/形态）
            # 白名单先给两个决策键；support_model 算出什么就允许什么
            self._support_allowed = {"enable_support", "support_threshold_angle"}
            if model_profile is not None:"""
assert old_head in s
s = s.replace(old_head, new_head, 1)

# 2) 把清理改成登记白名单（真正的清理放到块外无条件执行）
old_inner = """                allowed = set(su.ops) | {"enable_support", "support_threshold_angle"}
                for k in [k for k in list(values) if support_model.is_support_key(k)]:
                    if k not in allowed:
                        values.pop(k, None)
                        reasons.pop(k, None)
                if su.ops:"""
new_inner = """                self._support_allowed |= set(su.ops)
                if su.ops:"""
assert old_inner in s
s = s.replace(old_inner, new_inner, 1)

# 3) 块外无条件清理：support_model 没算到的 support_* 一律不写
old_tail = """                warnings.append(f"支撑按模型计算失败（已跳过）：{exc}")"""
new_tail = """                warnings.append(f"支撑按模型计算失败（已跳过）：{exc}")

            # 支撑键的单一来源兜底：不论有没有模型几何、不管上游哪一层写过，
            # 白名单之外的 support_* 全部撤回（避免「支撑没开却改了间隙」这类噪音）
            for k in [k for k in list(values) if support_model.is_support_key(k)]:
                if k not in getattr(self, "_support_allowed", set()):
                    values.pop(k, None)
                    reasons.pop(k, None)"""
assert old_tail in s
s = s.replace(old_tail, new_tail, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎：支撑白名单兜底已加（无条件执行）")
