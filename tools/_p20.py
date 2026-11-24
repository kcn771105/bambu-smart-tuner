import io

# ---- 1. PlateInfo.summary_line 去掉与 hardware 重复的板面/禁打区
p = "core/plate.py"
s = io.open(p, encoding="utf-8").read()
old = '''    def summary_line(self) -> str:
        """给 UI「真机同步」用的一行。"""
        if not self.known:
            return "打印板：工程里没读到 curr_bed_type（按默认 Supertack 超粘板对待）"
        parts = [f"打印板：{self.label or self.name}"]
        if self.temp is not None and self.supported:
            t0 = f"{self.temp_initial:g}℃" if self.temp_initial else "未读到"
            parts.append(f"首层 {t0} / 其它层 {self.temp:g}℃")
        elif not self.supported:
            parts.append("⚠ 耗材页这块板的温度是 0，表示这条料在它上面不可用")
        if self.bed_w and self.bed_d:
            parts.append(f"板面 {self.bed_w:g} × {self.bed_d:g} mm"
                         + (f" × 高 {self.bed_h:g} mm" if self.bed_h else ""))
        if self.exclude_blocks:
            parts.append(f"前方禁打区 {self.exclude_blocks} 块")
        return " ｜ ".join(parts)'''

new = '''    def summary_line(self) -> str:
        """给 UI「真机同步」用的一行。

        只写板型与温度 —— 板面尺寸/禁打区由 hardware 的「板面」那一行负责，
        两边都写会在同一行里重复两遍。
        """
        if not self.known:
            return "打印板：工程里没读到 curr_bed_type（按出厂默认 Supertack 超粘板对待）"
        parts = [f"打印板：{self.label or self.name}"]
        if self.temp is not None and self.supported:
            t0 = f"{self.temp_initial:g}℃" if self.temp_initial else "未读到"
            parts.append(f"首层 {t0} / 其它层 {self.temp:g}℃")
        elif not self.supported:
            parts.append("⚠ 耗材页这块板的温度是 0，表示这条料在它上面不可用")
        return " ｜ ".join(parts)'''
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("plate.summary_line 去重")

# ---- 2. UI：extra 之间补分隔符
p2 = "ui/main_window.py"
t = io.open(p2, encoding="utf-8").read()
old2 = '''        text = " ｜ ".join(lines)
        if extra:
            text += " " + " ".join(extra)'''
new2 = '''        text = " ｜ ".join(lines)
        if extra:
            text += " ｜ " + " ｜ ".join(extra)'''
assert old2 in t
t = t.replace(old2, new2, 1)
io.open(p2, "w", encoding="utf-8").write(t)
print("UI extra 分隔符")
