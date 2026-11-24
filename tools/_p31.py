import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---- 1. 保存区加一个可选开关：把工艺档标为自定义（默认关）
old = '''        self.lbl_file_state = QLabel("尚未加载工程")'''
new = '''        # 只改工艺参数还是顺带改工艺档名：默认只改参数（用户要求「只更改工艺板块参数」）
        self.chk_custom_profile = QCheckBox(
            "把工艺档标为自定义（仅当 Studio 打开后没反映改动时才勾）")
        self.chk_custom_profile.setToolTip(
            "勾上后会把 3mf 里的 print_settings_id 改成「原名 - Smart Tuner」，"
            "Studio 就不会去盘上找同名系统预设、必定采用文件里的参数。\\n"
            "只改工程文件内部这一行元数据，不写 Bambu Studio 的任何预设。")
        self.chk_custom_profile.setChecked(False)
        g.addWidget(self.chk_custom_profile, 3, 0, 1, 4)

        self.lbl_file_state = QLabel("尚未加载工程")'''
assert old in s
s = s.replace(old, new, 1)

# ---- 2. 保存时按开关决定是否改名
old2 = """            # 标成自定义工艺档：Studio 就不会按同名系统预设去覆盖文件里的值
            renamed = self.project.mark_custom_process()"""
new2 = """            # 工艺档名默认不动（用户要求只改工艺参数）；
            # 只有在勾选「标为自定义」时才改这一行元数据
            renamed = ""
            if self.chk_custom_profile.isChecked():
                renamed = self.project.mark_custom_process()"""
assert old2 in s
s = s.replace(old2, new2, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("UI：自定义档名改为可选开关（默认关）")
