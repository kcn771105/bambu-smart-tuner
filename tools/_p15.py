import io

p = "tools/smoke_ui_nozzle.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("win.load_project(PROJ)", "win.load_file(PROJ)")
io.open(p, "w", encoding="utf-8").write(s)
print("use load_file")
