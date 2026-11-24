import io

p = "README.md"
s = io.open(p, encoding="utf-8").read()
anchor = "\n## 8"
i = s.find(anchor)
if i < 0:
    i = len(s)

section = """
## 7.16 速度类参数为什么以前「改了没生效」——按热端变体分槽

Bambu 的这批键在工程里是**数组**，一个槽位对应一种热端：

| 键 | 工程里的值 | 含义 |
| --- | --- | --- |
| `outer_wall_speed` | `["200", "500", "500"]` | 标准流量 / 高流量 / E3D 高流量 |
| `inner_wall_speed` | `["300", "600", "600"]` | 同上 |
| `travel_speed` | `["1000", "1000", "1000"]` | 同上 |
| `default_acceleration` | `["10000", "10000", "10000"]` | 同上 |

槽位数来自工程里的 `print_extruder_variant`：

```
["Direct Drive Standard", "Direct Drive High Flow", "Direct Drive E3D High Flow"]   → 3 槽
```

**Bambu Studio 显示的是「当前所选热端」那一槽的值。** 以前本程序只改第 0 槽，
如果你的 Studio 里喷嘴那一栏选的是「高流量」，它读的是第 1 槽 = 500，
于是现象就是：表格里写着 `外壁速度 200 → 124`，Studio 里还是 500，看起来完全没改。

### 现在的做法

`core/schema.py` 的 `set_variant_slots(n)`：引擎在每次优化开头按
`hotend.slot_count(工程)` 告诉她本工程有几个变体槽位；写回时对
**槽位数 == 变体数** 的数组参数（速度、加速度、流量这类）**每一槽都写成同一个优化值**：

```
outer_wall_speed: ["200", "500", "500"]  →  ["162", "162", "162"]
```

为什么写同一个值而不是按比例放大：高流量热端「能跑更快」不等于「应该跑更快」。
本程序的优化目标是表面质量 / 强度 / 时间预算，与热端类型无关；写保守值最安全，
而且无论你在 Studio 里选哪种热端，看到的都是真正生效的那个数。

没有变体列表的工程（`print_extruder_variant` 只有 1 项或不存在）仍然只改第 0 槽，
不会把其它喷嘴/耗材的设定顺手改掉。

### 自查命令

```powershell
python tools/check_slot_write.py
```

输出会逐键打印「源 / 出」两个数组，确认三个槽位都被写成同一个值：

```
outer_wall_speed   源=['200', '500', '500']   出=['162', '162', '162']
inner_wall_speed   源=['300', '600', '600']   出=['200', '200', '200']
travel_speed       源=['1000', '1000', '1000'] 出=['600', '600', '600']
```

### 与「只动工艺页」的关系

这次改动仍然只碰工艺页的键（`outer_wall_speed` 等都是 process 页），
耗材页、机器页一个都没动；变的只是「同一个工艺键写几个槽位」。
"""

s = s[:i] + section + s[i:]
io.open(p, "w", encoding="utf-8").write(s)
print("README 增 §7.16，长度", len(s))
