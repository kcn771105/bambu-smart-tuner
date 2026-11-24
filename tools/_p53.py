import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()
s = s.replace("1. **官方词条自动匹配**（141 条）", "1. **官方词条自动匹配**（141 条）")
s = s.replace("2. **手工对照**（88 条）", "2. **手工对照**（90 条）")
s = s.replace("3. **标明界面没有**（38 条）",
              "3. **标明界面没有**（38 条）——剩下 0 条未匹配，269 个工艺键全部有定位")
io.open(p, "w", encoding="utf-8").write(s)
print("README 数字对齐 90/141/38")
