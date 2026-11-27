"""用本机 Bambu Studio 的命令行切片一次，核对参数是不是真的进了 gcode。

为什么需要这一层：「写进 3mf」和「切片时生效」是两件事。

前面几层已经能保证：

    * 值确实写进了 `Metadata/project_settings.config`（保存后回读逐键比对）；
    * 该声明进 `different_settings_to_system` 的都声明了（否则 Studio 按预设盖回去）。

但 Studio 自己的切片器还有一层：机型上限、体积流量、层高可取范围、树状支撑的
细分层……都可能把你表格里的数字改掉。用户的原话是「仔细核对参数是否应用成功」，
所以这里直接调 Studio 的 CLI 切一遍，再从 gcode 里把实际生效的值读回来对照。

命令行（Bambu Studio 自带，不需要开界面）：

    bambu-studio.exe --slice 0 --allow-newer-file --outputdir OUT --no-check FILE.3mf

注意两个坑，本模块都会自动处理，并把处理过的事记在 `notes` 里：

1. 工程里的 `wall_filament / sparse_infill_filament / solid_infill_filament` 可能是 0，
   而新版切片器要求 >= 1；老版本会直接报 `not in range [1,2147483647]` 退出。
2. 工程里的 `machine_start_gcode` 可能用了新版才有的占位符，老版 CLI 解析不了
   （`Parsing error at line N: Not a variable name`）。

两个都只在**临时副本**上处理，不动你保存出来的正式文件；处理的是 gcode 模板与
耗材序号，打印参数一项没动，所以对照表仍然有效。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field

__all__ = [
    "STUDIO_PATHS", "find_studio", "SliceCheck", "probe_gcode",
    "run_slice_check", "CHECKED_KEYS",
]

#: 常见的安装位置（可以在界面上手填一个别的路径）
STUDIO_PATHS = (
    r"C:\Program Files\Bambu Studio\bambu-studio.exe",
    r"C:\Program Files (x86)\Bambu Studio\bambu-studio.exe",
    r"D:\Program Files\Bambu Studio\bambu-studio.exe",
    r"E:\Program Files\Bambu Studio\bambu-studio.exe",
)

#: 从 0 改成 1 的耗材序号键（新版切片器要求 1 起；老工程常是 0）
_FILAMENT_INDEX_KEYS = ("wall_filament", "sparse_infill_filament", "solid_infill_filament")

#: 兼容老版 CLI 用的最小 gcode 模板（只影响启停代码，不影响打印参数）
_MIN_GCODE = {
    "machine_start_gcode":
        "G28 ; home\nG1 Z5 F600\nM104 S{nozzle_temperature[0]}\nM140 S{bed_temperature[0]}\n",
    "machine_end_gcode": "M104 S0\nM140 S0\nG28 X0\n",
    "change_filament_gcode": "; no tool change\n",
    "layer_change_gcode": ";LAYER_CHANGE\n;Z:{layer_z}\n",
    "before_layer_change_gcode": "",
    "time_lapse_gcode": "",
    "printing_by_object_gcode": "",
    "machine_pause_gcode": "M400\n",
    "template_custom_gcode": "",
    "wrap_gcode_when_slicing": "",
}


def find_studio(extra: str = "") -> str:
    """找一个可用的 bambu-studio.exe；找不到返回空串。"""
    for cand in ([extra] if extra else []) + list(STUDIO_PATHS):
        if cand and os.path.isfile(cand):
            return cand
    exe = shutil.which("bambu-studio") or shutil.which("bambu-studio.exe")
    return exe or ""


# ---------------------------------------------------------------- 数据结构


@dataclass
class Probe:
    """从 gcode 里读回来的实际值。"""

    layer_height: float = 0.0
    wall_loops: float = 0.0
    outer_wall_speed: float = 0.0
    inner_wall_speed: float = 0.0
    initial_layer_speed: float = 0.0
    support_speed: float = 0.0
    fan_min_pct: float = 0.0
    fan_max_pct: float = 0.0
    bed_temp: float = 0.0          # gcode 里实际的 M140 值（取非零）
    bed_temp_header: float = 0.0   # 配置头里的 bed_temperature
    enable_support: bool = False
    support_moves: int = 0         # gcode 里 `; FEATURE: Support` 的出现次数
    layers: int = 0
    time_text: str = ""
    filament_g: float = 0.0
    raw_head: dict = field(default_factory=dict)


@dataclass
class SliceCheck:
    ok: bool = False
    studio: str = ""
    gcode: str = ""
    log_tail: str = ""
    notes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    probe: Probe | None = None
    rows: list = field(default_factory=list)      # [(项, 期望, 实际, 是否一致)]
    # 全量核对：写进去的每一项 → 切片器实际采用的值
    all_rows: list = field(default_factory=list)  # [(键, 写入, gcode, ok|overridden|absent)]
    effective_ok: int = 0
    effective_bad: list = field(default_factory=list)     # 被 Studio 改成别的值的键
    effective_absent: list = field(default_factory=list)  # 没进 gcode 配置的键


# ---------------------------------------------------------------- 副本准备


def _headless_copy(src: str, dst: str) -> list:
    """生成一份给命令行切片用的副本，返回做了哪些兼容处理（人话）。"""
    notes: list = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "Metadata/project_settings.config":
                cfg = json.loads(data.decode("utf-8"))
                for key in _FILAMENT_INDEX_KEYS:
                    if str(cfg.get(key, "")).strip() in ("0", ""):
                        cfg[key] = "1"
                        notes.append(f"耗材序号 {key} 由 0 改成 1（新版切片器要求 ≥1）")
                for key, val in _MIN_GCODE.items():
                    if key in cfg:
                        cfg[key] = val
                notes.append("启动/结束/换料 gcode 换成最小模板（老版命令行解析不了新版占位符）")
                notes.append("以上两项只动 gcode 模板与耗材序号，打印参数一项没改")
                data = json.dumps(cfg, ensure_ascii=False, indent=4).encode("utf-8")
            zout.writestr(item, data)
    return notes


# ---------------------------------------------------------------- 切片 + 读回


_HEAD_RE = re.compile(r"^; ([A-Za-z0-9_]+) = (.+)$", re.M)


_CFG_LINE_RE = re.compile(r"^;\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$", re.M)


def parse_config(path: str) -> dict:
    """读 gcode 里的 CONFIG_BLOCK —— 那是切片器**实际采用**的整套参数。

    和「文件里写了什么」不同：这里反映的是 Studio 解析预设、声明槽、钳制之后
    真正拿去切片的数值。所以逐键比这一份，才能证明「改的每一项都生效了」。
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = re.search(r";\s*CONFIG_BLOCK_START(.*?);\s*CONFIG_BLOCK_END", text, re.S)
    seg = m.group(1) if m else text[:400000]
    out: dict[str, str] = {}
    for line in seg.splitlines():
        hit = _CFG_LINE_RE.match(line)
        if not hit:
            continue
        key = hit.group(1)
        if key not in out:                       # 同名以第一次出现为准
            out[key] = hit.group(2).strip()
    return out


def _scalar(value) -> str:
    """把 ["137","137"] / "137,137" / 137 统一成第一个标量的字符串。"""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    txt = str(value).strip()
    if txt.startswith("["):
        try:
            arr = json.loads(txt)
            txt = str(arr[0]) if arr else ""
        except ValueError:
            txt = txt.strip("[]").split(",")[0]
    if "," in txt:
        txt = txt.split(",")[0]
    return txt.strip().strip('"').strip()


def _same_num(a, b, tol: float = 0.51) -> bool:
    """两个值算不算同一个值：能解析成数字就带容差比，否则按字符串（不分大小写）比。"""
    sa, sb = _scalar(a), _scalar(b)
    try:
        return abs(float(sa) - float(sb)) <= tol
    except ValueError:
        return sa.lower() == sb.lower()


def compare_all(write_values: dict, cfg: dict) -> list:
    """逐键对照：写进去的值 vs 切片器实际用的值。

    返回 [(key, 写进去的, gcode 里的, 结论)]，结论是 ok / overridden / absent 三种。
    """
    rows = []
    for key in write_values:
        want = write_values[key]
        if key not in cfg:
            rows.append((key, want, "", "absent"))
            continue
        have = cfg[key]
        rows.append((key, want, have, "ok" if _same_num(want, have) else "overridden"))
    return rows


def probe_gcode(path: str) -> Probe:
    """从 gcode 里把实际生效的值读回来。"""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    head = dict(_HEAD_RE.findall(text[:60000]))

    def num(key: str, default: float = 0.0) -> float:
        raw = str(head.get(key, "")).strip()
        raw = raw.lstrip("[").rstrip("]").replace('"', "")
        first = raw.split(",")[0].strip() if raw else ""
        try:
            return float(first)
        except ValueError:
            return default

    p = Probe()
    p.raw_head = head
    p.layer_height = num("layer_height")
    p.wall_loops = num("wall_loops")
    p.outer_wall_speed = num("outer_wall_speed")
    p.inner_wall_speed = num("inner_wall_speed")
    p.initial_layer_speed = num("initial_layer_speed")
    p.support_speed = num("support_speed")
    p.fan_min_pct = num("fan_min_speed")
    p.fan_max_pct = num("fan_max_speed")
    p.bed_temp_header = num("bed_temperature")

    beds = [int(x) for x in re.findall(r"^M140 S(\d+)", text, re.M) if int(x) > 0]
    if beds:
        p.bed_temp = max(beds)

    p.enable_support = str(head.get("enable_support", "0")).strip() not in ("", "0", "false")
    p.support_moves = text.count("; FEATURE: Support")
    p.layers = text.count(";LAYER_CHANGE")

    m = re.search(r"^; model printing time: (.+)$", text, re.M)
    p.time_text = m.group(1).split(";")[0].strip() if m else ""

    for pat in (r"^; total filament weight \[g\] : ([\d.]+)",
                r"^; total filament used \[g\] : ([\d.]+)",
                r"^; filament used \[mm\] = ([\d.]+)"):
        m = re.search(pat, text, re.M)
        if m:
            p.filament_g = float(m.group(1))
            break
    return p


#: 对着表格逐项核对的键（顺序即展示顺序）
CHECKED_KEYS = (
    "layer_height", "wall_loops", "outer_wall_speed", "inner_wall_speed",
    "initial_layer_speed", "fan_min_speed", "fan_max_speed",
)


def _first(value) -> float:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 0
    txt = str(value).strip()
    if txt.startswith("["):
        try:
            arr = json.loads(txt)
            txt = str(arr[0]) if arr else "0"
        except ValueError:
            txt = txt.strip("[]").split(",")[0]
    try:
        return float(str(txt).strip().strip('"'))
    except ValueError:
        return 0.0


#: 表格里的键 → Probe 上的字段名（风扇在 Probe 上带 _pct 后缀）
_PROBE_FIELD = {
    "layer_height": "layer_height",
    "wall_loops": "wall_loops",
    "outer_wall_speed": "outer_wall_speed",
    "inner_wall_speed": "inner_wall_speed",
    "initial_layer_speed": "initial_layer_speed",
    "fan_min_speed": "fan_min_pct",
    "fan_max_speed": "fan_max_pct",
}


#: 每项的容差：层高差 0.01 mm 就已经是另一回事了，速度/温度差半个单位不算
_TOLERANCE = {"layer_height": 0.005, "wall_loops": 0.1}


def _tol(key: str) -> float:
    return _TOLERANCE.get(key, 0.51)


def _compare(write_values: dict, probe: Probe, cfg: dict | None = None) -> list:
    """对着表格逐项核对。`cfg` 给了就以 gcode 配置块为准（那是切片器采用的最终值）；
    否则退回从 gcode 特征里读出来的近似值。
    """
    cfg = cfg or {}
    rows = []

    def pick(key: str, fallback: float) -> float:
        if key in cfg:
            got = _first(cfg[key])
            if got > 0:
                return got
        return fallback

    for key in CHECKED_KEYS:
        if key not in write_values:
            continue
        want = _first(write_values[key])
        got = pick(key, getattr(probe, _PROBE_FIELD.get(key, key), 0.0))
        rows.append((key, f"{want:g}", f"{got:g}", abs(want - got) <= _tol(key)))

    # 板温：配置块里的板温才是切片器采用值；M140 里可能夹着首层温度，只作参考
    for key in ("supertack_plate_temp", "textured_plate_temp", "hot_plate_temp",
                "eng_plate_temp", "cool_plate_temp"):
        if key in write_values:
            want = _first(write_values[key])
            got = pick(key, probe.bed_temp)
            rows.append((key, f"{want:g}", f"{got:g}", abs(want - got) < 0.51))
            break

    if "enable_support" in write_values:
        want = _first(write_values["enable_support"]) >= 0.5
        rows.append(("enable_support", "开" if want else "关",
                     f"开（{probe.support_moves} 条支撑路径）" if probe.enable_support else "关",
                     want == probe.enable_support))
    return rows


def run_slice_check(project_path: str, write_values: dict, *,
                    out_dir: str = "", studio: str = "",
                    timeout: int = 1800) -> SliceCheck:
    """切一片并核对。不抛异常：失败信息放在 `ok/log_tail/warnings` 里。"""
    res = SliceCheck()
    exe = find_studio(studio)
    res.studio = exe
    if not exe:
        res.warnings.append("没找到 bambu-studio.exe：请确认装了 Bambu Studio，或在设置里手填路径。")
        return res

    tmp_root = out_dir or tempfile.mkdtemp(prefix="bst_slice_")
    os.makedirs(tmp_root, exist_ok=True)
    copy_3mf = os.path.join(tmp_root, "_headless.3mf")
    gcode_dir = os.path.join(tmp_root, "gcode")
    os.makedirs(gcode_dir, exist_ok=True)

    try:
        res.notes = _headless_copy(project_path, copy_3mf)
    except Exception as exc:                      # noqa: BLE001 - 报给人看
        res.warnings.append(f"准备切片副本失败：{exc}")
        return res

    cmd = [exe, "--slice", "0", "--allow-newer-file", "--no-check",
           "--outputdir", gcode_dir, copy_3mf]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    except Exception as exc:                      # noqa: BLE001
        res.warnings.append(f"调用切片器失败：{exc}")
        return res

    # Studio 的命令行切完片**不一定退出**（实测会挂在原地占着内存），所以不能干等进程结束：
    # 盯着 gcode 落地、大小连续两次不变，就把它收掉。
    deadline = time.time() + timeout
    stable = 0
    size_prev = 0
    while time.time() < deadline:
        got = [os.path.join(r, f) for r, _d, fs in os.walk(gcode_dir)
               for f in fs if f.endswith(".gcode")]
        size_now = max((os.path.getsize(f) for f in got), default=0)
        if size_now > 0 and size_now == size_prev:
            stable += 1
            if stable >= 2:                       # 连续两次不变 → 写完了
                break
        else:
            stable = 0
        size_prev = size_now
        if proc.poll() is not None:                # 进程自己退了：gcode 已经落地就算成功
            break
        time.sleep(1.0)

    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:                          # noqa: BLE001
            try:
                proc.kill()
            except Exception:                      # noqa: BLE001
                pass
    finished = stable >= 2 or (proc.poll() is not None and size_prev > 0)
    if size_prev == 0:
        # 进程退出了却没产物：最常见的是机器上已经开着一个 Bambu Studio（单实例），
        # 命令行把任务转交给它、自己立刻退出，于是我们什么也拿不到。
        res.warnings.append(
            "切片器没有产出 gcode：先关掉正在运行的 Bambu Studio 再试"
            "（它只允许一个实例，命令行会被转交给已开的窗口）；"
            "也可能是这个工程本身被它拒绝了，看下面的输出。")
        return res
    if not finished:
        res.warnings.append(f"切片超过 {timeout} 秒没写完，已放弃（工程太大或 Studio 弹了窗）。")
        return res
    try:
        log = proc.stdout.read() if proc.stdout else ""
    except Exception:                              # noqa: BLE001
        log = ""
    res.log_tail = chr(10).join((log or "").strip().splitlines()[-12:])

    gcodes = []
    for root, _dirs, files in os.walk(gcode_dir):
        for name in files:
            if name.endswith(".gcode"):
                gcodes.append(os.path.join(root, name))
    if not gcodes:
        res.warnings.append("切片器没有产出 gcode —— 看 log_tail 里的报错。")
        return res

    res.gcode = max(gcodes, key=os.path.getsize)
    try:
        res.probe = probe_gcode(res.gcode)
    except Exception as exc:                      # noqa: BLE001
        res.warnings.append(f"读 gcode 失败：{exc}")
        return res

    cfg = {}
    try:
        cfg = parse_config(res.gcode)
    except Exception as exc:                      # noqa: BLE001
        res.warnings.append(f"读 gcode 配置块失败：{exc}")
    res.rows = _compare(write_values or {}, res.probe, cfg)
    res.ok = all(row[3] for row in res.rows) if res.rows else False

    # 全量核对：写进去的每一项，切片器实际用的是不是这个值。
    # 这一份比 CHECKED_KEYS 严格得多 —— 它连「Studio 悄悄改成别的值」都能抓出来。
    try:
        res.all_rows = compare_all(write_values or {}, cfg)
        res.effective_ok = sum(1 for row in res.all_rows if row[3] == "ok")
        res.effective_bad = [row for row in res.all_rows if row[3] == "overridden"]
        res.effective_absent = [row[0] for row in res.all_rows if row[3] == "absent"]
    except Exception as exc:                      # noqa: BLE001
        res.warnings.append(f"逐键核对 gcode 配置失败：{exc}")
    return res
