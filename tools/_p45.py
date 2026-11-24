import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

# ---------- 1. 表头加一列「Studio 里在哪」
old = '''        self.table.setColumnCount(6)
        self.table.setHeaderLabels(["参数", "归属", "原始值", "优化后", "写入", "调整依据"])'''
new = '''        self.table.setColumnCount(7)
        self.table.setHeaderLabels(
            ["参数", "Studio 里在哪", "归属", "原始值", "优化后", "写入", "调整依据"])'''
assert old in s
s = s.replace(old, new, 1)

old = '''        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 78)
        self.table.setColumnWidth(2, 112)
        self.table.setColumnWidth(3, 112)
        self.table.setColumnWidth(4, 54)'''
new = '''        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 168)
        self.table.setColumnWidth(2, 66)
        self.table.setColumnWidth(3, 104)
        self.table.setColumnWidth(4, 104)
        self.table.setColumnWidth(5, 48)'''
assert old in s
s = s.replace(old, new, 1)

old = '''        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)'''
new = '''        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)'''
assert old in s
s = s.replace(old, new, 1)

# ---------- 2. 行填充：插入 Studio 位置单元格 + 四处列号后移
old = '''            item = QTreeWidgetItem([row.label, scope.SCOPE_LABEL.get(row.scope, row.scope),
                                     row.old_display, row.new_display, write, reason])
            item.setForeground(1, QColor(COLOR_MUTED if row.scope == scope.PROCESS else COLOR_WARN))
            if row.changed:
                item.setForeground(3, QColor(COLOR_OK))
                f = item.font(3)
                f.setBold(True)
                item.setFont(3, f)
                if not row.will_write:
                    item.setForeground(4, QColor(COLOR_WARN))
                    item.setToolTip(4, row.skip_reason or "工程文件里没有这个键，只给推荐值")
            else:
                item.setForeground(2, QColor(COLOR_MUTED))
                item.setForeground(3, QColor(COLOR_MUTED))
            item.setData(0, Qt.ItemDataRole.UserRole, row.key)
            item.setToolTip(0, row.key)
            if reason:
                item.setToolTip(5, reason)'''
new = '''            spot = studio_ui.info(row.key, fallback_label=row.label, group=row.group)
            item = QTreeWidgetItem([row.label, spot.path,
                                     scope.SCOPE_LABEL.get(row.scope, row.scope),
                                     row.old_display, row.new_display, write, reason])
            item.setForeground(2, QColor(COLOR_MUTED if row.scope == scope.PROCESS else COLOR_WARN))
            if row.changed:
                item.setForeground(4, QColor(COLOR_OK))
                f = item.font(4)
                f.setBold(True)
                item.setFont(4, f)
                if not row.will_write:
                    item.setForeground(5, QColor(COLOR_WARN))
                    item.setToolTip(5, row.skip_reason or "工程文件里没有这个键，只给推荐值")
            else:
                item.setForeground(3, QColor(COLOR_MUTED))
                item.setForeground(4, QColor(COLOR_MUTED))
            if spot.hidden:
                item.setForeground(1, QColor(COLOR_WARN))
            item.setData(0, Qt.ItemDataRole.UserRole, row.key)
            tip = [f"键名：{row.key}", f"Studio 位置：{spot.path}"]
            if spot.search_hint:
                tip.append(f"在 Studio 搜索框里输入：{spot.search_hint}")
            item.setToolTip(0, "\\n".join(tip))
            item.setToolTip(1, "\\n".join(tip))
            if reason:
                item.setToolTip(6, reason)'''
assert old in s
s = s.replace(old, new, 1)

# 分组表头行改成 7 个空列
old = '''                parent = QTreeWidgetItem([row.group_label, "", "", "", "", ""])'''
new = '''                parent = QTreeWidgetItem([row.group_label, "", "", "", "", "", ""])'''
assert old in s
s = s.replace(old, new, 1)

# ---------- 3. import
s = s.replace("from core import scope", "from core import scope, studio_ui", 1)

# ---------- 4. 右键菜单加「复制 Studio 搜索词」
old = '''        act_row = menu.addAction("复制这一行（制表符分隔，可直接粘进 Excel）")
        act_key = menu.addAction(f"复制键名：{key or '（无）'}")
        act_key.setEnabled(bool(key))'''
new = '''        spot = studio_ui.info(str(key or ""), fallback_label=cols[0]) if key else None
        act_row = menu.addAction("复制这一行（制表符分隔，可直接粘进 Excel）")
        act_key = menu.addAction(f"复制键名：{key or '（无）'}")
        act_key.setEnabled(bool(key))
        act_spot = menu.addAction(
            f"复制 Studio 搜索词：{spot.search_hint}" if (spot and spot.search_hint)
            else "这条在 Studio 界面上没有对应开关")
        act_spot.setEnabled(bool(spot and spot.search_hint))'''
assert old in s
s = s.replace(old, new, 1)

old = '''        elif act is act_key:
            QApplication.clipboard().setText(str(key))
            self._log(f"已复制键名：{key}")'''
new = '''        elif act is act_key:
            QApplication.clipboard().setText(str(key))
            self._log(f"已复制键名：{key}")
        elif act is act_spot:
            QApplication.clipboard().setText(spot.search_hint)
            self._log(f"已复制 Studio 搜索词「{spot.search_hint}」—— 到 Studio 工艺面板的搜索框里粘上就能跳过去。")'''
assert old in s
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("表格加「Studio 里在哪」列 + 右键复制搜索词")
