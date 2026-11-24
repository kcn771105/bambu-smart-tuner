import io

p = "core/rules_engine.py"
e = io.open(p, encoding="utf-8").read()

# 记住「工程里那根热端」是什么，用来判断用户是不是换了高流量热端
old = """        self._hotend = hotend.detect(current)
        picked = hotend.normalize(hotend_flow or "")"""
new = """        self._hotend_detected = hotend.detect(current)
        self._hotend = self._hotend_detected
        picked = hotend.normalize(hotend_flow or "")"""
assert old in e
e = e.replace(old, new, 1)

# 工程实测标定按「选中的热端 / 工程里的热端」比例折算
old2 = """        if official and self._hotend_mul > 1.0:
            official = float(official) * self._hotend_mul
            srcs.append(
                f"热端流量类型「{self._hotend.label}」×{self._hotend_mul:g}")"""
new2 = """        if official and self._hotend_mul > 1.0:
            official = float(official) * self._hotend_mul
            srcs.append(
                f"热端流量类型「{self._hotend.label}」×{self._hotend_mul:g}")
        # 工程里 filament_max_volumetric_speed 是「在工程那根热端上标出来的」：
        # 用户把下拉改成高流量 = 换了热端，标定值要按两根热端的比例折算。
        if project_max:
            base_mul, _ = hotend.factor(self.rules, self._hotend_detected.key)
            if abs(self._hotend_mul - base_mul) > 1e-9:
                ratio = self._hotend_mul / max(base_mul, 1e-9)
                scaled = float(project_max) * ratio
                warnings.append(
                    f"热端流量同步：工程里的 {float(project_max):g} mm³/s 是在"
                    f"「{self._hotend_detected.label}」热端上标的，按「{self._hotend.label}」"
                    f"折算 ×{ratio:g} 后为 {scaled:.1f} mm³/s。"
                    f"（换热端后请用 Bambu Studio 重新做一次流量标定，这个折算只是估计。）")
                project_max = scaled"""
assert old2 in e
e = e.replace(old2, new2, 1)

e = e.replace("        self._hotend = hotend.HotendInfo()",
              "        self._hotend = hotend.HotendInfo()\n"
              "        self._hotend_detected = hotend.HotendInfo()", 1)

io.open(p, "w", encoding="utf-8").write(e)
print("工程标定值按热端比例折算")
