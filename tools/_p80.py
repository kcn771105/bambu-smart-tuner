import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()
if "pack_release.ps1" not in s:
    s = s.rstrip() + """

## 16 打包与分发（发给别人怎么用）

### 生成发布包

```powershell
.\\build_exe.ps1 -SkipDeps     # 先打 EXE，产出 dist\\
.\\pack_release.ps1            # 再打包成 release\\BambuSmartTuner-v1.0-win64.zip
```

`pack_release.ps1` 产出的 zip 里就五个文件，解压即用：

| 文件 | 作用 |
| --- | --- |
| `BambuSmartTuner.exe` | 主程序（单文件，内置 Python + Qt） |
| `rules\\BambuRules.json` | 调参规则库，收件人可直接编辑 |
| `data\\studio_ui.json` | 「参数在 Studio 里在哪」对照表，可直接编辑 |
| `README.md` | 完整文档 |
| `收件人须知.txt` | 给非开发者看的五页说明（怎么用、改了啥、常见问题） |

### 收件人需要什么

- Windows 10 64 位 / Windows 11；**不需要** Python、.NET、VC++ 运行库、管理员权限
- **不需要**装 Bambu Studio：装了会读本机官方预设把差异声明算得更准；
  没装则退化为「把改过的键全部声明为差异」，出文件与切片都正常
- 不需要联网（程序无任何网络代码）

### 实测过的分发形态

| 场景 | 结果 |
| --- | --- |
| 只给一个 EXE（不带 rules/data） | 能启动、能优化（规则库与定位表用打包进 exe 的内置副本）；但收件人就改不了规则 |
| 给完整五个文件 | 启动、优化、保存、自检全通过 |
| 拷到 `F:\\_rel_test` 这类全新目录解压运行 | 正常，规则库就近加载 |
| 目标机没装 Bambu Studio（`STUDIO_DIRS` 不存在） | 正常出文件，自检通过，差异声明从 62 项降为 19 项（=全部改动键） |

### 两点要提前告知收件人

1. **首次启动 3~8 秒**：单文件程序要先解包，不是卡死。
2. **杀软可能误报**：PyInstaller 单文件是常见误报源；程序无联网、无安装、无注册表写入。
"""
    io.open(p, "w", encoding="utf-8").write(s)
    print("README 增 §16，长度", len(s))
else:
    print("README 已有分发章节")
