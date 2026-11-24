"""写入范围层：把参数分成「切片工艺 / 耗材页 / 机器页 / 元数据」

为什么要这一层
--------------
Bambu Studio 的工程文件把三页设置全塞在同一个
``Metadata/project_settings.config`` 里。工程里 594 个键，
其中约 265 个属于切片工艺页，48 个属于耗材页（风扇 / 回抽 / 流量 /
AMS 槽位 / 收缩补偿），38 个属于机器页（硬件上限 / 喷嘴 / 板面 / G-code）。

如果一把梭全写，就会出现用户说的「把打印机耗材也改了」——
喷嘴、耗材槽位、机器上限被改掉之后，切片可能直接报错，
或者和 Bambu Studio 里选好的机器/耗材对不上。

所以本模块给出**明确的归属表**，引擎按归属过滤写入。

归属从哪来
----------
不是拍脑袋。``C:\Program Files\Bambu Studio\resources\profiles\BBL\``
下三个目录正好对应 Bambu Studio 的三个页面：

    process/   切片工艺页
    filament/  耗材页
    machine/   机器页

「某个键出现在哪个目录」就等价于「这个键属于哪一页」。
官方查不到的新键由 ``tools/derive_scope.py`` 里的人工表补齐，
最终结果固化在 ``core/scope_data.py``（纯静态表，运行时不依赖本机装没装 Bambu Studio）。

三档写法
--------
    process  切片工艺 —— 默认允许写（本程序的战场）
    filament 耗材页   —— 默认只读；它的「上限值」仍会被读取，用来约束工艺参数
    machine  机器页   —— 默认只读；它的「硬件上限」仍会被读取，用来约束工艺参数
    meta     元数据   —— 永不写

「只读」不是「不用」：耗材页的 ``filament_max_volumetric_speed`` 是用户
按热端标定出来的流量上限，机器页的 ``machine_max_speed_x`` 是这台机器
真实的速度上限——它们不写回，但会作为约束参与钳制。
"""

from __future__ import annotations

from .scope_data import SCOPE, SCOPE_LABEL, SCOPE_NOTE

__all__ = [
    "SCOPE", "SCOPE_LABEL", "SCOPE_NOTE",
    "PROCESS", "FILAMENT", "MACHINE", "META",
    "scope_of", "is_writable", "writable_keys", "readonly_keys",
    "group_by_scope", "scope_summary", "ScopePolicy",
]

PROCESS = "process"
FILAMENT = "filament"
MACHINE = "machine"
META = "meta"

#: 默认允许写入的归属。用户可在规则库 options.write_scopes 里改。
DEFAULT_WRITABLE = (PROCESS,)


def scope_of(key: str) -> str:
    """某个键属于哪一页。未登记的键按「工艺」处理（宁可多写也不漏）。"""
    return SCOPE.get(key, PROCESS)


def is_writable(key: str, allowed: tuple[str, ...] = DEFAULT_WRITABLE) -> bool:
    return scope_of(key) in allowed


def writable_keys(allowed: tuple[str, ...] = DEFAULT_WRITABLE) -> list[str]:
    return [k for k in SCOPE if scope_of(k) in allowed]


def readonly_keys(allowed: tuple[str, ...] = DEFAULT_WRITABLE) -> list[str]:
    return [k for k in SCOPE if scope_of(k) not in allowed]


def group_by_scope(keys) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {PROCESS: [], FILAMENT: [], MACHINE: [], META: []}
    for k in keys:
        out.setdefault(scope_of(k), []).append(k)
    return out


def scope_summary(allowed: tuple[str, ...] = DEFAULT_WRITABLE) -> list[tuple[str, int, str]]:
    """给 UI 用的统计：(归属, 数量, 说明)。"""
    counts = {PROCESS: 0, FILAMENT: 0, MACHINE: 0, META: 0}
    for k in SCOPE:
        counts[scope_of(k)] = counts.get(scope_of(k), 0) + 1
    out = []
    for sc in (PROCESS, FILAMENT, MACHINE, META):
        if sc == PROCESS:
            note = SCOPE_NOTE[PROCESS]
        elif sc in allowed:
            note = "本程序允许写入这一页。"
        else:
            note = SCOPE_NOTE.get(sc, "")
        out.append((SCOPE_LABEL.get(sc, sc), counts.get(sc, 0), note))
    return out


class ScopePolicy:
    """写入范围策略对象。

    引擎用它决定某个键能不能写、为什么不能写（UI 要显示原因）。
    """

    def __init__(self, allowed: tuple[str, ...] = DEFAULT_WRITABLE):
        self.allowed = tuple(allowed)
        self._by_scope = group_by_scope(SCOPE.keys())

    @classmethod
    def from_rules(cls, rules: dict) -> "ScopePolicy":
        raw = (rules.get("options") or {}).get("write_scopes")
        if not raw:
            return cls(DEFAULT_WRITABLE)
        if isinstance(raw, str):
            raw = [raw]
        allowed = tuple(str(x) for x in raw if str(x) in (PROCESS, FILAMENT, MACHINE, META))
        return cls(allowed or DEFAULT_WRITABLE)

    # -------------------------------------------------- 查询

    def scope(self, key: str) -> str:
        return scope_of(key)

    def allows(self, key: str) -> bool:
        return scope_of(key) in self.allowed

    def reason(self, key: str) -> str:
        """不能写时的原因（写进 UI 表格与报告）。"""
        sc = scope_of(key)
        if sc in self.allowed:
            return ""
        label = SCOPE_LABEL.get(sc, sc)
        return f"{label}参数：{SCOPE_NOTE.get(sc, '按要求不改。')}"

    def keys(self) -> list[str]:
        return list(SCOPE.keys())

    def summary(self) -> list[tuple[str, int, str]]:
        return scope_summary(self.allowed)

    @property
    def blocked_count(self) -> int:
        return sum(1 for k in SCOPE if not self.allows(k))
