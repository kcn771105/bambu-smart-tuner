# -*- coding: utf-8 -*-
"""tools 里公用的路径定位，避免把某台机器的绝对路径写进仓库。

取值顺序：
    1. 环境变量 BST_PROJECT —— 指向一个真实 .3mf 工程
    2. samples/shape_plate_flat.3mf —— 仓库自带的最小工程
输出目录：
    BST_OUT_DIR（默认 %TEMP%/bambu_tuner_tools）
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project() -> Path:
    """一个可用的 3mf 工程（不存在时返回路径本身，让调用方自己报错）。"""
    env = os.environ.get("BST_PROJECT")
    if env:
        return Path(env).expanduser()
    return ROOT / "samples" / "shape_plate_flat.3mf"


def out(name: str) -> Path:
    """输出文件路径；目录不存在会自动建。"""
    d = Path(os.environ.get("BST_OUT_DIR") or (Path(tempfile.gettempdir()) / "bambu_tuner_tools"))
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def profiles_dir() -> Path:
    """本机 Bambu Studio 的预设目录。"""
    for cand in (
        Path(r"C:\Program Files\Bambu Studio\resources\profiles\BBL"),
        Path("/Applications/BambuStudio.app/Contents/Resources/profiles/BBL"),
        Path("/usr/share/BambuStudio/resources/profiles/BBL"),
    ):
        if cand.exists():
            return cand
    return Path(os.environ.get("BST_PROFILES", ""))
