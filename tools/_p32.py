import io

r = "README.md"
t = io.open(r, encoding="utf-8").read()
anchor = "## 8"
i = t.find(anchor)
if i < 0:
    i = len(t)

section = """## 7.10 写入纪律：只写这一份 3mf，不碰拓竹的任何预设

这条是硬约束，不是承诺。四道闸口都在代码里：

| 闸口 | 位置 | 拦什么 |
| --- | --- | --- |
| 参数范围闸 | `core/scope.py` 的 `ScopePolicy.allows()` | 只放行切片工艺页的键；耗材页、机器页的键一律不写（只读参照，用来约束工艺页的上下限） |
| 路径闸 | `core/safety.py` 的 `guard_target()` | 目标路径若落在 `%APPDATA%\\BambuStudio\\user\\{filament,process,machine,printer}` 或安装目录 `resources\\profiles\\` 下（本机实测 42 个预设目录、2750 个 json），直接抛异常拒绝写；后缀不在 `.3mf/.bambu/.md/.txt/.json/.log` 内也拒绝 |
| 预设指纹闸 | `safety.fingerprint()` + `diff_fingerprint()` | 保存前后各拍一次全量指纹（mtime_ns + size 的 sha1），有变化就在日志里告警 |
| 写出自检闸 | `safety.self_check()` | 存完立刻把文件重新打开，把 `project_settings.config` 里每个写入项和内存里的结果逐条比，不一致就列出来 |

### 值一律写成字符串

Bambu 的 `project_settings.config` 里所有值都是字符串（`'["179", "500", "500"]'`、`'0.24'`）。
引擎内部为了算数会把它们变成数字，写回时必须还原成字符串：`core/threemf.py` 的
`studio_settings()` 统一做这件事。以前少了这一步，数字型值写进去可能被 Studio 的解析器
整份拒绝——表现出来的就是「文件能打开，参数没变」。

### 工艺档名默认不动

`print_settings_id` 默认保持原样（`0.20mm Standard @BBL P2S`）。Studio 打开工程时会按这个名字
去盘上找同名预设，如果你担心它用预设值盖掉文件里的值，可以勾保存区的
**「把工艺档标为自定义（仅当 Studio 打开后没反映改动时才勾）」**——它会把 3mf 里这一行改成
`0.20mm Standard @BBL P2S - Smart Tuner`，Studio 找不到同名预设，只能采用文件里的参数。

这个开关只改工程文件内部的一行元数据：
- 不写 Bambu Studio 的任何预设文件；
- 不动 `filament_settings_id` / `printer_settings_id`（那两个决定喷头与 AMS 映射，动了会出别的问题）；
- 幂等：已经带 ` - Smart Tuner` 后缀就不再叠加。

### 耗材参数为什么改不了

耗材页（风扇、回抽、流量比、压力提前、板温）属于「这一卷料」的属性，写进工程就等于改了
你的耗材配置，跟「只改工艺」冲突。所以这些键一律只读：引擎会读它们的值来约束工艺参数
（例如按风扇设定判断悬垂能不能堆料、按回抽设定判断拉丝风险），但一个字都不写回。

想改耗材参数，请在 Bambu Studio 里改，并确认它只作用于当前工程。

"""
t = t[:i] + section + t[i:]
io.open(r, "w", encoding="utf-8").write(t)
print("README 增 §7.10，长度", len(t))
