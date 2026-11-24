"""UI 打通「喷嘴流量同步」：
1. run_optimize 传 nozzle_explicit（用户手改过喷嘴时以 UI 为准，而不是被工程值顶回去）
2. _render_hw 改文案：不再说"以工程值为准"，而是说清楚"流量已按新喷嘴折算"
3. 优化完成后把实际采用的流量上限显示在真机同步面板
"""
import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1. 传 nozzle_explicit
old = """            res = self.engine.optimize(
                self.original_settings,
                printer_key=printer, filament_key=filament, nozzle=nozzle,
                mode_key=mode, detection_warnings=warns, detection_notes=notes,
                filament_overlay=overlay, model_profile=profile, time_cap_pct=cap,
                hardware_info=self.hw)"""
new = """            # 喷嘴：用户手动改过下拉就以 UI 为准（nozzle_explicit=True），
            # 否则交给引擎按工程 machine 页的值同步（那是这台机器真实装的喷嘴）。
            hw_noz = self.hw.nozzle_diameter if self.hw else None
            nozzle_explicit = bool(hw_noz) and abs(float(nozzle) - float(hw_noz)) > 1e-6

            res = self.engine.optimize(
                self.original_settings,
                printer_key=printer, filament_key=filament, nozzle=nozzle,
                mode_key=mode, detection_warnings=warns, detection_notes=notes,
                filament_overlay=overlay, model_profile=profile, time_cap_pct=cap,
                hardware_info=self.hw, nozzle_explicit=nozzle_explicit)"""
assert old in s, "run_optimize 调用锚点没找到"
s = s.replace(old, new, 1)

# ---- 2. _render_hw 文案与流量行
old2 = """        lines = hw.summary_lines()
        # 喷嘴读到的值与下拉不一致时提示（用户可手动改）
        extra: list[str] = []
        cur = self._current_nozzle()
        if hw.nozzle_diameter and abs(hw.nozzle_diameter - cur) > 1e-6:
            extra.append(f"（工程里的喷嘴是 {hw.nozzle_diameter:g} mm，与当前选择不同，"
                         f"将以工程值为准）")"""
new2 = """        lines = hw.summary_lines()
        # 喷嘴读到的值与下拉不一致时说明会怎么处理（流量要跟着换）
        extra: list[str] = []
        cur = self._current_nozzle()
        if hw.nozzle_diameter and abs(hw.nozzle_diameter - cur) > 1e-6:
            extra.append(
                f"（当前选 {cur:g} mm、工程里装的是 {hw.nozzle_diameter:g} mm —— "
                f"已按你的选择算，层高/线宽等比缩放，体积流量上限也按官方"
                f"「{cur:g} 喷嘴」标定重新折算，不再沿用工程那个喷嘴的值）")
        if getattr(self, "last_result", None) is not None:
            fl = getattr(self.last_result, "flow_limit", None)
            if fl:
                extra.append(f"本次采用体积流量上限 {fl:g} mm³/s")"""
assert old2 in s, "_render_hw 锚点没找到"
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("UI 已打通喷嘴同步")
