import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()

old = '''        self.chk_timecap = QCheckBox("时长上限 25%")
        self.chk_timecap.setToolTip(
            "勾选后，若均衡/快速草稿模式算出时长涨幅超过 25%，会自动把层高、填充、"
            "速度往回调，直到落在上限内。强度优先与两个精细档不受此限"
            "（精细档层高本来就压得很小，拉高层高会破坏这一档的意义）。")'''

new = '''        self.chk_timecap = QCheckBox("按时长预算自动回调")
        self.chk_timecap.setToolTip(
            "勾选后按规则库每个档位自带的时长预算执行回调：均衡 40%、草稿 10%、"
            "强度 200%、质量 170%，精细两档不限。超出预算时按「代价最小」的顺序"
            "自动回退（先降填充密度 → 顶底壳层 → 墙圈数 → 提速度 → 提加速度），"
            "强度档不动墙圈数、草稿档不动层高以上的墙数。"
            "不勾选 = 完全不做时长回调，参数全按规则给足。")'''

assert old in s, "checkbox block not found"
s = s.replace(old, new)

io.open(p, "w", encoding="utf-8").write(s)
print("patched checkbox")
