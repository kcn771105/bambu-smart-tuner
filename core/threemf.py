"""3mf 读写层

Bambu Studio 保存的「工程 3mf」本质是一个 zip 包：

    3D/3dmodel.model               几何（本程序完全不碰）
    Metadata/model_settings.config 每个对象的个性化设置（本程序不碰）
    Metadata/project_settings.config  **全部切片参数，JSON 字典，值都是字符串**
    Metadata/slice_info.config     切片结果信息（切片过才有）
    Metadata/plate_1.json / .png   盘面布局与缩略图
    _rels/.rels / [Content_Types].xml

本模块只做三件事：
1. 打开 zip，找到 project_settings.config，解析成有序 dict；
2. 把改动写回，并保证「不覆盖原文件」；
3. 顺手清掉过期的切片结果（slice_info.config / *.gcode），避免 Bambu Studio
   打开时显示旧的切片结果和旧时长。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_SETTINGS = "Metadata/project_settings.config"
MODEL_SETTINGS = "Metadata/model_settings.config"
SLICE_INFO = "Metadata/slice_info.config"


class ThreeMfError(Exception):
    """3mf 文件结构不符合预期时抛出，消息直接可展示给用户。"""


#: 这些键在 project_settings.config 里必须是数组（不是字符串）。
#: 原工程缺这几行、我们要补写时，得先把类型登记成数组。
_ARRAY_KEYS = frozenset({
    "different_settings_to_system", "printable_area", "wrapping_exclude_area",
    "nozzle_diameter", "extruder_type", "extruder_variant",
    "filament_settings_id", "default_filament_profile",
})


def _norm(name: str) -> str:
    return name.replace("\\", "/").lower()


@dataclass
class ThreeMfProject:
    path: Path
    entries: dict[str, bytes] = field(default_factory=dict)   # 原始条目，保留顺序
    settings_name: str = ""
    settings: dict[str, str] = field(default_factory=dict)
    meta: dict[str, str] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)        # 每个键在原 JSON 里的类型
    elem_kinds: dict[str, str] = field(default_factory=dict)   # 数组键的元素类型
    list_lens: dict[str, int] = field(default_factory=dict)    # 数组键在原工程里的长度
    originals: dict[str, str] = field(default_factory=dict)   # 原始值（写回时保留未优化的槽位）

    # ------------------------------------------------------------ 载入

    @classmethod
    def load(cls, path: str | os.PathLike) -> "ThreeMfProject":
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise ThreeMfError(f"文件不存在：{p}")
        if p.suffix.lower() not in (".3mf", ".bambu"):
            raise ThreeMfError(f"只支持 .3mf / .bambu 工程文件，当前是 {p.suffix}")
        try:
            zf = zipfile.ZipFile(p)
        except zipfile.BadZipFile as exc:
            raise ThreeMfError(
                "这个文件不是有效的 3mf（zip）包。\n"
                "常见原因：从 Bambu Studio 导出的是「导出 G-code」而不是「保存工程」。"
            ) from exc

        proj = cls(path=p)
        with zf:
            for info in zf.infolist():
                proj.entries[info.filename] = zf.read(info.filename)

        name = proj._find_settings_name()
        if not name:
            raise ThreeMfError(
                "包里没有 Metadata/project_settings.config，说明它不是 Bambu Studio 的工程文件。\n"
                "请用 Bambu Studio：文件 → 保存工程（或 另存为 .3mf），不要用「导出 G-code」。"
            )
        proj.settings_name = name
        raw = proj.entries[name]
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ThreeMfError(f"{name} 不是合法 JSON：{exc}") from exc
        if not isinstance(data, dict):
            raise ThreeMfError(f"{name} 顶层结构不是对象（dict），无法解析。")
        proj.kinds = {str(k): _kind_of(v) for k, v in data.items()}
        proj.elem_kinds = {str(k): _elem_kind_of(v) for k, v in data.items()
                           if isinstance(v, list) and v}
        proj.list_lens = {str(k): len(v) for k, v in data.items()
                          if isinstance(v, list)}
        proj.settings = {str(k): _stringify(v) for k, v in data.items()}
        proj.originals = dict(proj.settings)
        proj.meta = proj._read_slice_meta()
        return proj

    def _find_settings_name(self) -> str:
        for n in self.entries:
            if _norm(n) == _norm(PROJECT_SETTINGS):
                return n
        # 少数第三方实现把文件放在别的目录，这里放宽到「名字对得上」即可
        for n in self.entries:
            base = os.path.basename(_norm(n))
            if base == "project_settings.config":
                return n
        return ""

    def _read_slice_meta(self) -> dict[str, str]:
        meta: dict[str, str] = {}
        raw = None
        for n, b in self.entries.items():
            if _norm(n) == _norm(SLICE_INFO):
                raw = b
                break
        if not raw:
            return meta
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return meta
        for md in root.iter("metadata"):
            k = md.get("key") or md.get("name")
            v = md.get("value")
            if k and v is not None:
                meta[k] = v
        return meta

    # ------------------------------------------------------------ 查询

    @property
    def is_sliced(self) -> bool:
        return any(_norm(n) == _norm(SLICE_INFO) for n in self.entries)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.settings.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.settings

    #: 这几类键在 project_settings.config 里必须是**数组**。原工程没有这个键时
    #: 我们补写它，必须先登记成数组类型，否则会写成 JSON 文本，Studio 认不出。
    ARRAY_KEYS = frozenset({"different_settings_to_system"})

    def ensure_array_key(self, key: str, length: int = 3) -> None:
        """把某个键登记为「数组型」，补写新键前先调一下。"""
        self.kinds[key] = "list"
        self.elem_kinds.setdefault(key, "str")
        self.list_lens[key] = length

    # ------------------------------------------------------------ 写回

    def apply(self, new_values: dict[str, str], *, skip_missing: bool = True,
              allow_missing: set[str] | frozenset[str] | None = None) -> tuple[dict[str, str], list[str]]:
        """把 {键: 已格式化字符串} 写进内存中的 settings。

        返回 (实际写入的键值, 被跳过的键)。skip_missing=True 时，
        工程里原本不存在的键不新增（Bambu Studio 对未知键容忍度不一，
        宁可不写也不要引入脏键）。

        allow_missing 里列出的键是例外：它们是 Studio 工程文件的标准键
        （热床温度 *_plate_temp、风扇 fan_* 等），老工程里可能没存这一行，
        但补进去 Studio 认；不补就等于「热床和风扇怎么设都不生效」。
        """
        written: dict[str, str] = {}
        skipped: list[str] = []
        exempt = allow_missing or frozenset()
        for k, v in new_values.items():
            if k not in self.settings and skip_missing and k not in exempt:
                skipped.append(k)
                continue
            if k not in self.settings and k in _ARRAY_KEYS:
                # 补写数组型键（printable_area 等）前先登记类型，否则会写成纯文本
                try:
                    n = len(json.loads(v)) if str(v).strip().startswith("[") else 1
                except (ValueError, TypeError):
                    n = 1
                self.ensure_array_key(k, n)
            if self.settings.get(k) == v:
                continue
            self.settings[k] = v
            written[k] = v
        return written, skipped

    # ------------------------------------------------------------ 序列化

    def _typed_settings(self) -> dict[str, object]:
        """把 settings 还原成「和原工程一样的 JSON 类型」。

        Bambu Studio 的 project_settings.config 里，同一个键的类型可能不一致：
        数字写成 0、布尔写成 1、数组写成 ["0"] 或 ["50","50","50"]。
        若一律写成字符串，Bambu Studio 打开后可能忽略该键或直接报错，
        所以这里按原文件里记录的类型逐键还原。

        数组型参数（如 outer_wall_speed: ["200","500","500"]）按喷嘴分槽：
        只有第 0 槽参与本次优化，第 1 槽起保留用户原来的设定，
        绝不因为优化第一个喷嘴而改掉其他喷嘴。
        """
        out: dict[str, object] = {}
        for k, raw in self.settings.items():
            kind = self.kinds.get(k, "str")
            elem = self.elem_kinds.get(k, "str")
            if kind == "list":
                out[k] = self._typed_list(k, raw, elem)
            else:
                out[k] = _coerce(raw, kind, elem)
        return out

    def _typed_list(self, key: str, raw: str, elem_kind: str) -> list:
        """数组型参数写回：第 0 槽用优化值，其余槽沿用原值。"""
        want = self.list_lens.get(key, 0)
        if isinstance(raw, (list, tuple)):
            # 兜底：调用方直接给了 list（例如新增的键没走 stringify）
            return [str(x) for x in raw]
        try:
            items = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            items = [x for x in raw.split(",")]
        if not isinstance(items, list):
            items = [items]
        items = [str(x) for x in items]

        if want and len(items) < want:
            # 引擎只给出一个标量 → 用原值补齐其余槽位
            orig = _split_orig_list(self.originals.get(key, ""), want)
            if len(items) == 1:
                items = [items[0]] + orig[1:want]
            else:
                items = items + orig[len(items):want]
        elif want and len(items) > want:
            items = items[:want]

        out = []
        for it in items:
            if elem_kind in ("int", "float", "bool"):
                out.append(_coerce(it, elem_kind))
            else:
                out.append(it)
        return out

    # ---------------------------------------------------------------- 写入形态
    def studio_settings(self) -> dict:
        """规范成 Bambu Studio 认识的形态。

        Bambu 的 project_settings.config 里，值一律是字符串，数组也是字符串数组
        （"0.2" / ["200","500","500"]）。引擎新增的键如果写成数字/浮点，Studio 的
        解析器可能整份拒绝 —— 表现出来就是「文件打开了但参数没变」。
        所以写盘前统一 stringify，避免这类静默失效。
        """
        out: dict = {}
        for key, val in self._typed_settings().items():
            if isinstance(val, list):
                out[key] = [self._stringify(x) for x in val]
            else:
                out[key] = self._stringify(val)
        return out

    @staticmethod
    def _stringify(val) -> str:
        if isinstance(val, str):
            return val
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, float):
            if val == int(val):
                return str(int(val))
            return f"{val:g}"
        return str(val)

    def mark_custom_process(self, suffix: str = " - Smart Tuner") -> str:
        """把工程标成「自定义工艺档」，让 Studio 必定采用文件里的参数。

        Studio 打开 3mf 时会按 print_settings_id 去盘上找同名预设；名字撞上系统预设时，
        容易变成「显示的是预设、看不见文件里的改动」。把名字改成一个盘上不存在的名字，
        Studio 就只能把文件里的值当成一份自定义档读进来。
        只改工艺档名，不动耗材/机型的 id（那两个决定喷头与 AMS 映射，改了会掉料）。
        """
        old = str(self.settings.get("print_settings_id") or "")
        if not old or old.endswith(suffix):
            return old
        new = old + suffix
        self.settings["print_settings_id"] = new
        if "default_print_profile" in self.settings:
            self.settings["default_print_profile"] = new
        return new

    def save_as(self, target: str | os.PathLike, *, strip_stale_slice: bool = True) -> Path:
        """另存为新 3mf。目标与原文件相同时自动改名，绝不覆盖原工程。"""
        src = self.path
        dst = Path(target).expanduser().resolve()
        if dst.suffix.lower() not in (".3mf", ".bambu"):
            dst = dst.with_suffix(".3mf")
        dst = _guard_not_source(dst, src)
        dst.parent.mkdir(parents=True, exist_ok=True)

        from . import safety
        safety.guard_target(dst)
        payload = json.dumps(self.studio_settings(), ensure_ascii=False,
                             indent=4).encode("utf-8")

        tmp_fd, tmp_name = tempfile.mkstemp(prefix="bst_", suffix=".3mf", dir=str(dst.parent))
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
                # [Content_Types].xml 放最前面更符合 OPC 习惯
                ordered = sorted(self.entries.keys(),
                                 key=lambda n: (0 if _norm(n) == "[content_types].xml" else 1,))
                for name in ordered:
                    lname = _norm(name)
                    if strip_stale_slice and _is_stale_artifact(lname):
                        continue
                    if lname == _norm(self.settings_name):
                        zout.writestr(name, payload)
                    else:
                        zout.writestr(name, self.entries[name])
                if self.settings_name not in self.entries:      # 理论上不会发生
                    zout.writestr(PROJECT_SETTINGS, payload)
            os.replace(tmp_path, dst)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return dst

    def save_copy(self, *, suffix: str = "_optimized", stamp: bool = True) -> Path:
        """就在原目录旁边生成副本，文件名加后缀（+时间戳）。"""
        src = self.path
        stem = src.stem
        if stamp:
            from datetime import datetime
            stem = f"{stem}{suffix}_{datetime.now():%Y%m%d_%H%M%S}"
        else:
            stem = f"{stem}{suffix}"
        return self.save_as(src.with_name(stem + src.suffix))


def _split_orig_list(raw: str, want: int) -> list[str]:
    """把原始数组值拆成 want 个元素，供数组型参数补齐槽位。"""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        items = [x for x in raw.split(",")]
    if not isinstance(items, list):
        items = [items]
    out = [str(x) for x in items]
    if want and len(out) < want:
        out = out + [out[-1] if out else "0"] * (want - len(out))
    return out[:want] if want else out


def _kind_of(v) -> str:
    """记录原 JSON 值的类型，供写回时还原。"""
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "str"


def _elem_kind_of(v) -> str:
    """记录数组里元素的类型（数组可能是 ["0"] 也可能是 [0]）。"""
    if isinstance(v, list) and v:
        return _kind_of(v[0])
    return "str"


def _coerce(raw: str, kind: str, elem_kind: str = "str", list_lens: int = 0):
    """把字符串还原成原工程里用过的类型。

    规则：
      - int/float：能转就转，转不了（"15%"、"auto"）就退回字符串
      - bool：0/1/true/false 互转
      - list：按原长度切分，逐元素按 elem_kind 还原
      - str/dict：原样
    """
    if kind == "bool":
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        return raw
    if kind in ("int", "float"):
        try:
            if kind == "int":
                return int(float(raw))
            f = float(raw)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return raw
    if kind == "list":
        try:
            items = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            items = [x for x in raw.split(",")]
        if not isinstance(items, list):
            items = [items]
        # 引擎对数组型参数只给出一个标量（如 "50"），这里按原工程的长度铺开：
        # 原来 3 个槽位就写回 3 个元素，不能缩成 1 个。
        want = list_lens or 0
        if want and len(items) == 1 and isinstance(items[0], str) and len(items[0]) == 1:
            items = items * want
        out = []
        for it in items:
            if elem_kind in ("int", "float", "bool"):
                out.append(_coerce(str(it), elem_kind))
            else:
                out.append(it if isinstance(it, str) else str(it))
        return out
    if kind == "dict":
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return raw
        return parsed if isinstance(parsed, dict) else raw
    return raw


def _stringify(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        if float(v).is_integer():
            return str(int(v))
        return repr(float(v))
    if isinstance(v, list):
        return json.dumps([_scalar(x) for x in v], ensure_ascii=False)
    return json.dumps(v, ensure_ascii=False)


def _scalar(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _is_stale_artifact(lname: str) -> bool:
    base = os.path.basename(lname)
    if lname == _norm(SLICE_INFO):
        return True
    if base.endswith(".gcode") or base.endswith(".gcode.md5"):
        return True
    return False


_TS = re.compile(r"_[0-9]{8}_[0-9]{6}$")


def _guard_not_source(dst: Path, src: Path) -> Path:
    try:
        if dst.exists() and dst.samefile(src):
            raise ThreeMfError("输出路径不能和原工程相同，本程序不会覆盖原始 3mf。")
    except OSError:
        pass
    if _TS.search(dst.stem):
        return dst
    if dst.resolve() == src.resolve():
        from datetime import datetime
        dst = dst.with_name(f"{dst.stem}_{datetime.now():%Y%m%d_%H%M%S}{dst.suffix}")
    return dst


def backup_file(path: str | os.PathLike) -> Path | None:
    """在写入前给原文件留一份 .bak（双保险，用户误操作也能找回）。"""
    p = Path(path)
    if not p.exists():
        return None
    bak = p.with_name(f"{p.stem}.bak{p.suffix}")
    if not bak.exists():
        shutil.copy2(p, bak)
    return bak
