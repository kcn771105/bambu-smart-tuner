import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old = '''            if r is not None:
                scaled = float(project_max) * r
                notes_flow = (
                    f"喷嘴同步：工程里的流量 {float(project_max):g} mm³/s 是按 "
                    f"{proj_noz:g} 喷嘴标的（{rsrc}），已折算成 {scaled:.1f} mm³/s，"
                    f"再与 {pick_noz:g} 喷嘴的官方上限 {noz_official or 0:g} 取小。")
                warnings.append(notes_flow)
                project_max = scaled'''

new = '''            if r is not None:
                scaled = float(project_max) * r
                if noz_official:
                    # 折算值与新喷嘴的官方上限取小 —— 工程标定只对原喷嘴成立
                    final = min(scaled, float(noz_official))
                else:
                    final = scaled
                warnings.append(
                    f"喷嘴同步：工程里的流量 {float(project_max):g} mm³/s 是按 "
                    f"{proj_noz:g} 喷嘴标的（{rsrc}），折算到 {pick_noz:g} 喷嘴为 "
                    f"{scaled:.1f} mm³/s，与官方 {pick_noz:g} 喷嘴上限 "
                    f"{noz_official or 0:g} 取小后按 {final:.1f} mm³/s 计算。")
                project_max = final'''

assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("patched min()")
