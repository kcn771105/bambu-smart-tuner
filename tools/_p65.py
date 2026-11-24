import io

p = "build_exe.ps1"
s = io.open(p, encoding="utf-8-sig").read()
old = "if (Test-Path 'README.md') { Copy-Item 'README.md' 'dist\\README.md' -Force }"
new = ("if (Test-Path 'README.md') { Copy-Item 'README.md' 'dist\\README.md' -Force }\n"
       "# Studio 定位表：EXE 优先读同目录 data\\studio_ui.json，方便自己就地改\n"
       "if (Test-Path 'data\\studio_ui.json') {\n"
       "    New-Item -ItemType Directory -Force -Path 'dist\\data' | Out-Null\n"
       "    Copy-Item 'data\\studio_ui.json' 'dist\\data\\studio_ui.json' -Force\n"
       "}")
assert old in s, "锚点没找到"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8-sig").write(s)
print("build_exe.ps1 现在会把 data/studio_ui.json 一起放进 dist")
