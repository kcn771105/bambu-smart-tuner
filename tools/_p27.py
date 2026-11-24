import io

# ---------- 1. UI：真机同步面板加热端类型 ----------
p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()
old = """            pl = getattr(self.result, "plate", "")
            if pl:
                extra.append(pl)"""
new = """            hd = getattr(self.result, "hotend", "")
            if hd:
                extra.append(hd)
            pl = getattr(self.result, "plate", "")
            if pl:
                extra.append(pl)"""
assert old in s
s = s.replace(old, new, 1)

# 识别回填 + 日志
old2 = """        idx = self.cmb_nozzle.findData(float(det.nozzle))
        self.cmb_nozzle.setCurrentIndex(idx if idx >= 0 else 1)
        self._suppress = False"""
new2 = """        idx = self.cmb_nozzle.findData(float(det.nozzle))
        self.cmb_nozzle.setCurrentIndex(idx if idx >= 0 else 1)
        # 热端流量类型：把工程里识别到的填进下拉（用户可改，改了就按新的算）
        self.hotend_info = hotend.detect(self.original_settings or {})
        hidx = self.cmb_hotend.findData(self.hotend_info.key)
        self.cmb_hotend.setCurrentIndex(hidx if hidx >= 0 else 0)
        self._suppress = False
        if hasattr(self, "cmb_hotend") and self.original_settings:
            self._log("热端流量：" + self.hotend_info.summary_line(),
                      "info" if self.hotend_info.detected else "warn")"""
assert old2 in s
s = s.replace(old2, new2, 1)

# ---------- 2. 保存：标自定义工艺档 + 预设指纹 + 保存后自检 ----------
old3 = """            written, skipped = self.project.apply(self.result.write_values)
            out = self.project.save_as(target)"""
new3 = """            fp_before = safety.fingerprint()
            written, skipped = self.project.apply(self.result.write_values)
            # 标成自定义工艺档：Studio 就不会按同名系统预设去覆盖文件里的值
            renamed = self.project.mark_custom_process()
            out = self.project.save_as(target)
            # 保存后自检：重新打开新 3mf，核对写进去的值 == UI 里显示的值
            problems = safety.self_check(out, self.result.write_values)
            fp_changed = safety.diff_fingerprint(fp_before, safety.fingerprint())"""
assert old3 in s
s = s.replace(old3, new3, 1)

old4 = """        self._log(f"已写入 {len(written)} 项参数，跳过 {len(skipped)} 项（工程里无此键）。", "ok")
        self._log(f"输出：{out}", "ok")"""
new4 = """        self._log(f"已写入 {len(written)} 项参数，跳过 {len(skipped)} 项（工程里无此键）。", "ok")
        if renamed:
            self._log(f"工艺档已标为自定义：print_settings_id = {renamed}"
                      f"（Studio 会采用文件里的参数，不会再回退到同名系统预设）", "info")
        if problems:
            self._log("⚠ 保存自检发现写入不一致：" + "；".join(problems[:6]), "err")
        else:
            self._log("保存自检通过：新 3mf 里的参数与表格里显示的完全一致。", "ok")
        if fp_changed:
            self._log("⚠ 检测到 Bambu Studio 预设目录在一次保存期间发生变化（不该发生）："
                      + "；".join(fp_changed[:6]), "err")
        else:
            self._log("预设隔离检查通过：Bambu Studio 的耗材/工艺/机型预设一个都没动。", "ok")
        self._log(f"输出：{out}", "ok")"""
assert old4 in s
s = s.replace(old4, new4, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("UI：面板 + 识别回填 + 保存自检 + 预设隔离")
