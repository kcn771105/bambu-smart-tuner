# -*- coding: utf-8 -*-
"""样例工程定位：优先环境变量，其次打包内的 samples，最后作者本机路径。

这样别人 clone 下来也能跑测试，而不需要把某台机器的绝对路径写进仓库。
用法：
    set BST_PROJECT=D:\my\project.3mf   （Windows）
    export BST_PROJECT=~/my/project.3mf  （Linux/macOS）
找不到样例时，相关用例自动 skip。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: 仓库自带的最小工程（tools/make_sample_3mf.py 生成，含几何与 500+ 参数）
BUNDLED = ROOT / "samples" / "shape_plate_flat.3mf"
#: 作者本机的一份真实工程，仅作为最后兜底，不参与分发
AUTHOR_HINT = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")


def project() -> Path:
    """返回一个可用的 3mf；都找不到就返回不存在的路径（调用方 skip）。"""
    env = os.environ.get("BST_PROJECT")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    if AUTHOR_HINT.exists():
        return AUTHOR_HINT
    return BUNDLED


PROJ = project()
