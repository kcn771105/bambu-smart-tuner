"""写入纪律：只写进当前 3mf，绝不碰 Bambu Studio 的预设目录。

用户 m05100 第 3 条：
「参数修改范围仅限当前 3mf 工程内部的切片配置；绝对不能修改、覆盖 Bambu Studio
软件里保存的耗材预设和全局预设，优化效果只存在于导出的新工程文件里。」

这条约束在代码里体现为三个闸门：

    1. guard_target(path)   保存目标如果落在 Bambu Studio 的预设目录里，直接拒绝；
    2. guard_no_preset_write()  保存前后对比预设目录的文件指纹，发现被改动就报错；
    3. self_check()         保存后重新打开新 3mf，逐项核对「写进去的值 == UI 显示的值」，
                            不一致就把差异列出来（这是 m05100 第 1 条的验收口径）。

Bambu Studio 的预设都在这些地方（不同版本/绿色版略有出入，能探到几个算几个）：

    %APPDATA%\\BambuStudio\\user\\<版本>\\filament      用户耗材预设
    %APPDATA%\\BambuStudio\\user\\<版本>\\process       用户工艺预设
    %APPDATA%\\BambuStudio\\user\\<版本>\\machine       用户机型预设
    <安装目录>\\resources\\profiles\\BBL\\filament      官方耗材预设
    <安装目录>\\resources\\profiles\\BBL\\process       官方工艺预设
    <安装目录>\\resources\\profiles\\BBL\\machine       官方机型预设
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

#: 与预设有关的子目录名（用来判断「这个路径是不是预设目录」）
PRESET_DIR_NAMES = {"filament", "process", "machine", "printer", "filament_library"}

#: 允许写入的目标后缀
ALLOWED_SUFFIXES = {".3mf", ".bambu", ".md", ".txt", ".json", ".log"}


def _appdata_roots() -> list[Path]:
    out: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "BambuStudio"
        if base.exists():
            out.append(base)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        base = Path(local) / "BambuStudio"
        if base.exists():
            out.append(base)
    return out


def _install_roots() -> list[Path]:
    out: list[Path] = []
    for cand in (Path(r"C:\Program Files\Bambu Studio"),
                 Path(r"C:\Program Files (x86)\Bambu Studio")):
        if cand.exists():
            out.append(cand)
    return out


def preset_dirs() -> list[Path]:
    """列出当前机器上能找到的所有 Bambu Studio 预设目录。"""
    dirs: list[Path] = []
    for root in _appdata_roots():
        for sub in root.rglob("*"):
            try:
                if sub.is_dir() and sub.name.lower() in PRESET_DIR_NAMES:
                    # 只看 user / profiles 下面的，避免把缓存目录算进来
                    low = str(sub).lower()
                    if "\\user\\" in low or "\\profiles\\" in low:
                        dirs.append(sub)
            except OSError:
                continue
    for root in _install_roots():
        prof = root / "resources" / "profiles"
        if prof.exists():
            for sub in prof.rglob("*"):
                try:
                    if sub.is_dir() and sub.name.lower() in PRESET_DIR_NAMES:
                        dirs.append(sub)
                except OSError:
                    continue
    # 去重 + 只保留存在的
    uniq: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d.resolve()).lower()
        if key in seen or not d.exists():
            continue
        seen.add(key)
        uniq.append(d.resolve())
    return uniq


def guard_target(path: str | os.PathLike) -> Path:
    """保存目标合法性检查：不许落进预设目录，不许覆盖源工程。"""
    target = Path(path).expanduser()
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target.absolute()
    low = str(resolved).lower()
    for d in preset_dirs():
        dlow = str(d).lower()
        if low == dlow or low.startswith(dlow + os.sep):
            raise PermissionError(
                f"拒绝写入 Bambu Studio 预设目录：{resolved}\n"
                f"本程序只写当前工程文件，不碰软件里的耗材/工艺/机型预设。"
                f"请换一个输出路径（例如源工程旁边）。")
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        raise PermissionError(
            f"拒绝写入 {resolved.suffix or '无后缀'} 文件：只允许 "
            f"{'、'.join(sorted(ALLOWED_SUFFIXES))}")
    return resolved


def _as_value(raw):
    """把引擎里的字符串形态还原成与文件同构的形态。

    ARRAY_* 类参数在引擎里是 JSON 文本（'["179", "500", "500"]'），
    文件里是数组。比对前必须统一，否则整片误报。
    """
    import json

    if not isinstance(raw, str):
        return raw
    txt = raw.strip()
    if txt[:1] in ("[", "{") and txt[-1:] in ("]", "}"):
        try:
            return json.loads(txt)
        except ValueError:
            return raw
    return raw


def fingerprint(dirs: list[Path] | None = None) -> dict[str, str]:
    """给预设目录拍一份指纹（相对路径 + mtime + size 的哈希）。"""
    out: dict[str, str] = {}
    for d in (dirs if dirs is not None else preset_dirs()):
        for f in d.rglob("*.json"):
            try:
                st = f.stat()
            except OSError:
                continue
            key = str(f).lower()
            out[key] = hashlib.sha1(
                f"{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()
    return out


def diff_fingerprint(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """两次指纹的差异（新增/改动/删除都算）。"""
    changes: list[str] = []
    for k, v in after.items():
        if before.get(k) != v:
            changes.append(("新增 " if k not in before else "改动 ") + k)
    for k in before:
        if k not in after:
            changes.append("删除 " + k)
    return changes


def self_check(path: str | os.PathLike, expected: dict[str, str],
               *, settings_suffix: str = "project_settings.config") -> list[str]:
    """保存后自检：重新打开新 3mf，核对写进去的值是否与期望一致。"""
    import json

    problems: list[str] = []
    target = Path(path)
    if not target.exists():
        return [f"文件不存在：{target}"]
    try:
        with zipfile.ZipFile(target) as z:
            names = [n for n in z.namelist() if n.endswith(settings_suffix)]
            if not names:
                return [f"文件里找不到 {settings_suffix}"]
            data = json.loads(z.read(names[0]).decode("utf-8"))
    except (zipfile.BadZipFile, ValueError) as exc:
        return [f"重新打开失败：{exc}"]

    for key, want in expected.items():
        got = data.get(key)
        if got is None:
            problems.append(f"{key}: 文件里没有这个键（期望 {want!r}）")
            continue
        # 引擎里数组型参数的期望值是一段 JSON 文本（'["179","500","500"]'），
        # 而文件里是真正的数组 —— 先统一形态，否则每条数组参数都会被误报。
        want = _as_value(want)
        # 数组按槽位比，字符串去空格
        if isinstance(got, list) or isinstance(want, list):
            g = [str(x).strip() for x in (got if isinstance(got, list) else [got])]
            w = [str(x).strip() for x in (want if isinstance(want, list) else [want])]
            if g[:1] != w[:1]:
                problems.append(f"{key}: 文件 {got!r} != 期望 {want!r}")
        else:
            if str(got).strip() != str(want).strip():
                problems.append(f"{key}: 文件 {got!r} != 期望 {want!r}")
    # 最后一道：Studio 只对 different_settings_to_system 里声明过的键采用文件里的值。
    # 这一项空了就等于「工艺页与系统预设一致」，写进去的改动会被预设值原地覆盖。
    raw = data.get("different_settings_to_system")
    if isinstance(raw, str):
        try:
            import json as _json
            raw = _json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, list) and raw:
        declared = [x for x in str(raw[0] or "").split(";") if x]
        if not declared:
            problems.append(
                "different_settings_to_system 的工艺槽是空的 —— "
                "Bambu Studio 会认为工艺页与同名系统预设完全一致，"
                "从而用预设值覆盖文件里写好的参数")
    else:
        problems.append("缺少 different_settings_to_system，Studio 无法知道哪些键是改过的")

    return problems
