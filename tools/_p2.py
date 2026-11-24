import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

old = """            profile = self.model_profile if (self.chk_shape.isChecked() and self.model_profile) else None
            # 时长上限：强度优先（本来就是慢的）与两个精细档（层高本来就压得很小、
            # 拉高层高会破坏这一档的意义）不受 25% 约束；其余档位受约束。
            no_cap_modes = {"strength", "fine", "ultrafine"}
            cap = 25.0 if (self.chk_timecap.isChecked() and mode not in no_cap_modes) else None"""

new = """            profile = self.model_profile if (self.chk_shape.isChecked() and self.model_profile) else None
            # 时长预算现在由规则库按档位给定（modes.<k>.time_budget_pct）：
            #   均衡 40% / 草稿 10% / 强度 200% / 质量 170% / 精细两档不限。
            # 勾选 = 交给引擎按这个预算自动回调；不勾 = 传一个极大的上限，
            # 等于完全不做时长回调（用户想自己控制时间时用）。
            cap = None if self.chk_timecap.isChecked() else 9999.0"""

assert old in s, "cap block not found"
s = s.replace(old, new)

io.open(p, "w", encoding="utf-8").write(s)
print("patched cap logic")
