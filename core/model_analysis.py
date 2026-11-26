"""模型几何分析（逐对象）——让每一个模型都拿到针对性的调参

为什么必须做到「每个模型」
------------------------
同一个盘面上摆 3 个件：一个小齿轮、一根 200mm 细杆、一块 300×300×2mm 薄板。
一套全局参数没法同时伺候这三个：

    · 细杆：怕晃    → 要降加速度、加宽裙边、抬高 Z hop
    · 薄板：怕翘曲  → 要降首层速度、加象脚补偿
    · 齿轮：怕糊细节→ 要小层高、慢外壁

所以本模块的做法是：**逐个对象算形状画像 → 逐对象判形状原型 → 逐对象出参数
建议 → 合并成一个全局结果**（合并策略对每类参数取「最保守的那件」）。

画像指标（全部只读几何，O(顶点+三角形) 级别）
------------------------------------------
    尺寸 / 体积 / 表面积 / 层数 / 悬垂面积占比 / 质心偏移
    fill_ratio       填充率 = 体积 / 包围盒体积（实心≈1，薄壳≈0.1）
    wall_thickness   平均壁厚 ≈ 2×体积/表面积（薄壳件≈壁厚）
    slender          细高比 = 高 / √底面积
    flatness         扁平度 = 高 / max(宽,深)
    plan_aspect      平面长宽比（长条件）
    top_cap_ratio    顶盖占比 = 顶层水平朝上面积 / 顶层包围盒面积
                     （花瓶/杯 = 0，封闭盒 = 1）
    neck_ratio       颈部比 = 最窄处带宽 / 最宽处带宽
    bands            8 段高度剖面（每段的宽度、面积、朝上面积）

几何只读，绝不修改模型。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from . import threemf

MODEL_ENTRY = "3D/3dmodel.model"
MAX_TRIS = 220_000          # 超过这个数就抽样，保证大文件也不卡
BANDS = 8                   # 高度剖面分段数


class ModelError(Exception):
    """几何读不出来时抛出，消息可直接展示。"""


# ------------------------------------------------------------------ 数据结构

@dataclass
class BandProfile:
    """高度剖面的一段。"""
    index: int
    z_lo: float
    z_hi: float
    width_x: float = 0.0
    width_y: float = 0.0
    area: float = 0.0          # 该段所有表面面积
    up_area: float = 0.0      # 该段水平朝上面积
    bbox_area: float = 0.0     # 该段包围盒面积

    @property
    def fill(self) -> float:
        if self.bbox_area <= 1e-9:
            return 0.0
        return min(1.0, self.area / self.bbox_area)


@dataclass
class ObjectProfile:
    """盘面上单个对象的形状画像。"""
    oid: str
    index: int
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0
    min_z: float = 0.0
    max_z: float = 0.0
    volume: float = 0.0
    surface: float = 0.0
    overhang_area: float = 0.0
    overhang_hi_area: float = 0.0   # 落在上部 40% 高度里的悬垂面积
    max_bridge_span: float = 0.0    # 最长的一条悬垂边（mm）：越大越像「一大片悬空」
    centre_offset: float = 0.0
    bands: list[BandProfile] = field(default_factory=list)

    # ---- 派生指标 ----
    @property
    def bbox_volume(self) -> float:
        return max(self.size_x * self.size_y * self.size_z, 1e-9)

    @property
    def fill_ratio(self) -> float:
        """填充率：实心件接近 1，薄壳/镂空件很小。"""
        return min(1.0, self.volume / self.bbox_volume)

    @property
    def wall_thickness(self) -> float:
        """平均壁厚估计：2×体积/表面积。

        薄板/薄壳件 ≈ 真实壁厚；实心立方体 ≈ 边长/3（所以判断薄壁要配合 fill_ratio）。
        """
        if self.surface <= 1e-9:
            return 0.0
        return 2.0 * self.volume / self.surface

    @property
    def footprint(self) -> float:
        """底面积估算：最小面积那段剖面的包围盒面积。"""
        if not self.bands:
            return self.size_x * self.size_y
        b = min(self.bands, key=lambda s: s.bbox_area)
        return b.bbox_area if b.bbox_area > 1e-9 else self.size_x * self.size_y

    @property
    def slender(self) -> float:
        """细高比：高度 / 等效底边。越大越容易晃。"""
        fp = self.footprint
        if fp <= 1e-6:
            return 0.0
        return self.size_z / math.sqrt(fp)

    @property
    def flatness(self) -> float:
        """扁平度：高度 / max(宽,深)。小于 0.25 就是扁平板。"""
        m = max(self.size_x, self.size_y)
        return self.size_z / m if m > 1e-9 else 0.0

    @property
    def plan_aspect(self) -> float:
        """平面长宽比：min/max(宽,深)。小于 0.5 是长条件。"""
        m = max(self.size_x, self.size_y, 1e-9)
        return min(self.size_x, self.size_y) / m

    @property
    def overhang_ratio(self) -> float:
        return self.overhang_area / self.surface if self.surface > 1e-9 else 0.0

    @property
    def overhang_top_ratio(self) -> float:
        """悬垂里有多大比例挤在上部（>60% 高度）。

        下部悬垂多半能被下面的实体自己撑住，上部悬垂才是真的会塌——
        同样是 5% 悬垂，位置不同该给的支撑强度也不同。
        """
        total = self.overhang_area
        if total <= 1e-9:
            return 0.0
        return min(1.0, self.overhang_hi_area / total)

    @property
    def top_cap_ratio(self) -> float:
        """顶盖占比：最高一段里水平朝上面积占该段包围盒的比例。

        花瓶/杯体开口 → 接近 0；封闭盒顶 → 接近 1。
        """
        if not self.bands:
            return 0.0
        top = self.bands[-1]
        if top.bbox_area <= 1e-9:
            return 0.0
        return min(1.0, top.up_area / top.bbox_area)

    @property
    def neck_ratio(self) -> float:
        """颈部比：最窄段 / 最宽段的宽度。"""
        if len(self.bands) < 3:
            return 1.0
        widths = [max(b.width_x, b.width_y) for b in self.bands]
        mx = max(widths)
        if mx <= 1e-9:
            return 1.0
        return min(widths) / mx

    @property
    def circle_score(self) -> float:
        """圆柱度：横截面「真实朝上面积 / 包围盒面积」，圆 ≈ 0.785，方 ≈ 1.0。

        用户反馈第 4 条问「这个软件可以让圆柱体的接缝光滑吗」——
        要回答它，先得知道这件到底是不是圆柱/圆管。判据只看几何：

            圆截面   π r² / (2r)² = π/4 ≈ 0.785
            方截面   1.0
            带圆角的方  0.85~0.95

        取全部有数据的层段里最接近「圆」的那一段（最细处常常是圆柱销/圆管），
        再配合平面长宽比 ≥0.9（圆的包围盒近似正方形）判圆。

        返回值 0 = 明显不是圆；越接近 1 越像圆。
        """
        scores: list[float] = []
        for b in self.bands:
            if b.bbox_area <= 1e-9 or b.up_area <= 1e-9:
                continue
            scores.append(b.up_area / b.bbox_area)
        if not scores:
            return 0.0
        # 只信任「接近 0.785」的那一段：距 π/4 越远分越低
        best = min(scores, key=lambda r: abs(r - 0.7854))
        if self.plan_aspect < 0.9:            # 包围盒不是方的，谈不上圆
            return 0.0
        if abs(best - 0.7854) <= 0.06:
            return 1.0
        if abs(best - 0.7854) <= 0.12:
            return 0.6
        return 0.0

    @property
    def mid_width(self) -> float:
        """中段宽度（判断实心块 vs 细柱）。"""
        if not self.bands:
            return max(self.size_x, self.size_y)
        b = self.bands[len(self.bands) // 2]
        return max(b.width_x, b.width_y)

    @property
    def volume_cm3(self) -> float:
        return self.volume / 1000.0

    def tags(self) -> list[str]:
        out: list[str] = []
        if self.size_z < 30:
            out.append("矮件")
        elif self.size_z < 120:
            out.append("中高件")
        else:
            out.append("高件")
        if self.slender >= 2.6:
            out.append("高瘦易晃")
        if self.volume < 8000:
            out.append("小体积")
        elif self.volume > 400_000:
            out.append("大体积")
        if self.flatness < 0.25:
            out.append("扁平板件")
        if self.wall_thickness < 1.6 and self.fill_ratio < 0.55:
            out.append("薄壁")
        if self.overhang_ratio > 0.18:
            out.append(f"悬垂重({self.overhang_ratio*100:.0f}%)")
        if self.top_cap_ratio < 0.15 and self.fill_ratio < 0.5:
            out.append("开口容器")
        if self.neck_ratio < 0.45:
            out.append("带收腰")
        if self.plan_aspect < 0.5:
            out.append("细长条")
        if self.circle_score >= 0.6:
            out.append("圆柱/圆管")
        if self.centre_offset > 0.35:
            out.append("质心偏置")
        return out

    def summary(self) -> str:
        return (f"{self.size_x:.0f}×{self.size_y:.0f}×{self.size_z:.0f} mm ｜ "
                f"{self.volume_cm3:.1f} cm³ ｜ 壁厚≈{self.wall_thickness:.1f} mm ｜ "
                f"细高比 {self.slender:.2f} ｜ 悬垂 {self.overhang_ratio*100:.0f}%")


@dataclass
class ModelProfile:
    """整个工程（所有盘面对象）的形状画像。"""
    objects: list[ObjectProfile] = field(default_factory=list)
    triangles: int = 0
    sampled: bool = False
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0
    volume: float = 0.0
    surface: float = 0.0
    overhang_area: float = 0.0
    footprint: float = 0.0
    centre_offset: float = 0.0
    layers: int = 0
    min_z: float = 0.0

    # ---- 派生指标（场景级） ----
    @property
    def height(self) -> float:
        return self.size_z

    @property
    def overhang_top_ratio(self) -> float:
        """整盘悬垂里挤在上部的比例（按面积加权）。"""
        tot = sum(o.overhang_area for o in self.objects)
        if tot <= 1e-9:
            return 0.0
        hi = sum(o.overhang_hi_area for o in self.objects)
        return min(1.0, hi / tot)

    @property
    def max_bridge_span(self) -> float:
        """整盘最长的一条悬垂边。"""
        return max((o.max_bridge_span for o in self.objects), default=0.0)

    @property
    def support_ratio(self) -> float:
        return self.overhang_area / self.surface if self.surface > 1e-9 else 0.0

    @property
    def slender(self) -> float:
        if self.footprint <= 1e-6:
            return 0.0
        return self.size_z / math.sqrt(self.footprint)

    @property
    def thickness_index(self) -> float:
        """表面积 / 体积^(2/3)：实心立方体≈6，圆柱≈6.3，薄板/镂空明显更大。"""
        if self.volume <= 1e-9:
            return 0.0
        return self.surface / (self.volume ** (2 / 3))

    @property
    def avg_area(self) -> float:
        return self.volume / self.size_z if self.size_z > 1e-6 else 0.0

    @property
    def flatness(self) -> float:
        """场景级扁平度：高度 / max(宽,深)。小于 0.25 即扁平件。"""
        m = max(self.size_x, self.size_y)
        return self.size_z / m if m > 1e-9 else 0.0

    @property
    def plan_aspect(self) -> float:
        """场景级平面长宽比：min/max(宽,深)。"""
        m = max(self.size_x, self.size_y, 1e-9)
        return min(self.size_x, self.size_y) / m

    @property
    def object_count(self) -> int:
        return len(self.objects)

    @property
    def circle_score(self) -> float:
        """盘面上最像圆柱的那一件的圆柱度（0 = 没有圆形件）。"""
        best = 0.0
        for o in self.objects:
            try:
                best = max(best, o.circle_score)
            except Exception:
                continue
        return best

    def tags(self) -> list[str]:
        out: list[str] = []
        if self.objects:
            out.append(f"多件（{len(self.objects)} 个对象）")
        if self.size_z < 30:
            out.append("矮件")
        elif self.size_z < 120:
            out.append("中高件")
        else:
            out.append("高件")
        if self.slender >= 2.6:
            out.append("高瘦易晃")
        if self.volume < 8000:
            out.append("小体积")
        elif self.volume > 400_000:
            out.append("大体积")
        if self.flatness < 0.25:
            out.append("扁平板件")
        # 用「平均壁厚 + 填充率」判薄壁，不能用 thickness_index(S/V^(2/3))：
        # 那个量对**平板**同样很大（160×120×8 的实心盒算出来 15），
        # 结果普通盒子被贴上「薄壁/镂空」，连带吃到一串降速规则。
        if any(0 < o.wall_thickness < 1.8 and o.fill_ratio < 0.6 for o in self.objects):
            out.append("薄壁/镂空")
        if self.support_ratio > 0.18:
            out.append(f"支撑重（{self.support_ratio*100:.0f}%）")
        if self.centre_offset > 0.35:
            out.append("质心偏置")
        if (self.footprint > 0 and self.footprint < 900
                and self.size_z > 60):
            out.append("小脚高塔")
        if self.circle_score >= 0.6:
            out.append("圆柱/圆管（可做斜接缝）")
        return out

    def summary(self) -> str:
        return (f"{self.size_x:.0f}×{self.size_y:.0f}×{self.size_z:.0f} mm ｜ "
                f"体积 {self.volume/1000:.1f} cm³ ｜ 约 {self.layers} 层 ｜ "
                f"支撑面 {self.support_ratio*100:.0f}% ｜ 细高比 {self.slender:.2f}")

    def object_summaries(self) -> list[str]:
        return [f"件{i+1}：{o.summary()}" for i, o in enumerate(self.objects)]


# ------------------------------------------------------------------ 几何解析

def _tag(el) -> str:
    t = el.tag
    return t.rsplit("}", 1)[-1] if "}" in t else t


def _parse_transform(txt: str | None) -> tuple[list[float], list[float]]:
    """3mf transform = 3x3 矩阵 + 平移，12 个数：m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32。

    这个 order 在 3MF 规范里是按行展开的 4x3（最后一列是平移）。
    返回 (rot9, trans3)。
    """
    if not txt:
        return [1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 0, 0]
    parts = txt.replace(",", " ").split()
    if len(parts) != 12:
        return [1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 0, 0]
    try:
        v = [float(x) for x in parts]
    except ValueError:
        return [1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 0, 0]
    # 规范顺序：m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32
    m = [v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8]]
    t = [v[9], v[10], v[11]]
    return m, t


def _apply(m, t, x, y, z):
    # 3MF 用「行向量 × 矩阵」：x' = x*m00 + y*m10 + z*m20 + m30
    return (x * m[0] + y * m[3] + z * m[6] + t[0],
            x * m[1] + y * m[4] + z * m[7] + t[1],
            x * m[2] + y * m[5] + z * m[8] + t[2])


def _read_model_xml(project: threemf.ThreeMfProject) -> bytes:
    name = None
    low = {n.lower(): n for n in project.entries}
    for cand in (MODEL_ENTRY.lower(), "3d/3dmodel.model"):
        if cand in low:
            name = low[cand]
            break
    if name is None:
        for n in project.entries:
            if n.lower().endswith(".model"):
                name = n
                break
    if name is None:
        raise ModelError("工程里没有 3D/3dmodel.model，读不到模型几何。")
    return project.entries[name]


def _analyse_object(oid: str, index: int, verts, tris, m, t, *,
                    overhang_cos: float, min_z_guard: float) -> ObjectProfile | None:
    """算单个对象的画像。verts/tris 已按变换前给出，m/t 是该对象的变换。"""
    n = len(verts)
    if n == 0:
        return None
    if m != [1, 0, 0, 0, 1, 0, 0, 0, 1] or t != [0, 0, 0]:
        tv = [_apply(m, t, *v) for v in verts]
    else:
        tv = verts

    obj = ObjectProfile(oid=oid, index=index)
    minv = [float("inf")] * 3
    maxv = [float("-inf")] * 3
    vol = 0.0
    surf = 0.0
    over = 0.0
    over_hi = 0.0
    bridge = 0.0
    cx = cy = 0.0

    # 先定 Z 范围，才能分高度段
    zmin = min(p[2] for p in tv)
    zmax = max(p[2] for p in tv)
    if zmax - zmin < 1e-9:
        return None
    obj.min_z = zmin
    obj.max_z = zmax
    obj.size_z = zmax - zmin

    span = obj.size_z / BANDS
    bands = [BandProfile(index=i, z_lo=zmin + i * span, z_hi=zmin + (i + 1) * span)
             for i in range(BANDS)]
    bminx = [float("inf")] * BANDS
    bmaxx = [float("-inf")] * BANDS
    bminy = [float("inf")] * BANDS
    bmaxy = [float("-inf")] * BANDS

    for i0 in range(0, len(tris), 1):
        a, b, c = tris[i0]
        if a >= n or b >= n or c >= n:
            continue
        p0, p1, p2 = tv[a], tv[b], tv[c]
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        x2, y2, z2 = p2

        ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
        vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        nxlen = math.sqrt(nx * nx + ny * ny + nz * nz)
        if nxlen < 1e-12:
            continue
        area = nxlen * 0.5
        surf += area
        unit_nz = nz / nxlen

        # 朝下且够平 → 需要支撑。但贴床的底面不算悬垂（落在热床上）。
        if unit_nz < -overhang_cos and max(z0, z1, z2) > min_z_guard:
            over += area
            # 悬垂落在哪一层，决定要不要加强支撑：上部悬垂下面没东西可撑。
            if (z0 + z1 + z2) / 3.0 > zmin + 0.6 * (zmax - zmin):
                over_hi += area
            # 悬垂面上最长的一条投影边 ≈ 这段是「悬空的一大片还是一窄条」。
            # 一窄条靠自身冷却能扛，一大片得降桥接速度、加接触层。
            e = max(math.hypot(x1 - x0, y1 - y0),
                    math.hypot(x2 - x1, y2 - y1),
                    math.hypot(x0 - x2, y0 - y2))
            if e > bridge:
                bridge = e

        # 有符号体积（散度定理，对闭合网格正确）
        v6 = (x0 * (y1 * z2 - z1 * y2)
              - y0 * (x1 * z2 - z1 * x2)
              + z0 * (x1 * y2 - y1 * x2))
        vol += v6 / 6.0
        cx += (x0 + x1 + x2) / 4.0 * v6 / 6.0
        cy += (y0 + y1 + y2) / 4.0 * v6 / 6.0

        for p in (p0, p1, p2):
            if p[0] < minv[0]: minv[0] = p[0]
            if p[1] < minv[1]: minv[1] = p[1]
            if p[2] < minv[2]: minv[2] = p[2]
            if p[0] > maxv[0]: maxv[0] = p[0]
            if p[1] > maxv[1]: maxv[1] = p[1]
            if p[2] > maxv[2]: maxv[2] = p[2]

        # 归入高度段
        zc = (z0 + z1 + z2) / 3.0
        bi = int((zc - zmin) / span)
        if bi < 0:
            bi = 0
        elif bi >= BANDS:
            bi = BANDS - 1
        bd = bands[bi]
        bd.area += area
        if unit_nz > 0.9:                      # 水平朝上
            bd.up_area += area
        for p in (p0, p1, p2):
            if p[0] < bminx[bi]: bminx[bi] = p[0]
            if p[0] > bmaxx[bi]: bmaxx[bi] = p[0]
            if p[1] < bminy[bi]: bminy[bi] = p[1]
            if p[1] > bmaxy[bi]: bmaxy[bi] = p[1]

    if surf <= 0:
        return None

    for i, bd in enumerate(bands):
        if bminx[i] == float("inf"):
            bd.width_x = bd.width_y = 0.0
            bd.bbox_area = 0.0
            continue
        bd.width_x = bmaxx[i] - bminx[i]
        bd.width_y = bmaxy[i] - bminy[i]
        bd.bbox_area = bd.width_x * bd.width_y

    obj.bands = bands
    obj.volume = abs(vol)
    obj.surface = surf
    obj.overhang_area = over
    obj.overhang_hi_area = over_hi
    obj.max_bridge_span = bridge
    obj.size_x = maxv[0] - minv[0]
    obj.size_y = maxv[1] - minv[1]
    obj.size_z = maxv[2] - minv[2]

    if obj.volume > 1e-9:
        cx /= vol
        cy /= vol
    else:
        cx = (minv[0] + maxv[0]) / 2
        cy = (minv[1] + maxv[1]) / 2
    spanxy = max(obj.size_x, obj.size_y, 1e-6)
    obj.centre_offset = min(1.0, math.hypot(cx - (minv[0] + maxv[0]) / 2,
                                            cy - (minv[1] + maxv[1]) / 2) / (spanxy / 2 or 1))
    return obj


def analyse(project: threemf.ThreeMfProject, *, overhang_angle: float = 45.0,
            layer_height: float = 0.2) -> ModelProfile:
    """解析工程里的全部网格，逐对象算形状画像。

    overhang_angle：支撑判定角（面与水平面夹角小于它就算需要支撑），
    与 Bambu Studio 的 support_threshold_angle 含义一致。
    layer_height：只用来估层数，不影响几何量。
    """
    raw = _read_model_xml(project)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ModelError(f"3dmodel.model XML 解析失败：{exc}") from exc

    # ---- 收集对象网格（id → 顶点表 / 三角形表）
    objects: dict[str, tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = {}
    for el in root.iter():
        if _tag(el) != "object":
            continue
        oid = el.get("id") or ""
        verts: list[tuple[float, float, float]] = []
        tris: list[tuple[int, int, int]] = []
        for sub in el.iter():
            st = _tag(sub)
            if st == "vertex":
                try:
                    verts.append((float(sub.get("x", 0)), float(sub.get("y", 0)),
                                  float(sub.get("z", 0))))
                except (TypeError, ValueError):
                    verts.append((0.0, 0.0, 0.0))
            elif st == "triangle":
                try:
                    tris.append((int(sub.get("v1", 0)), int(sub.get("v2", 0)),
                                 int(sub.get("v3", 0))))
                except (TypeError, ValueError):
                    continue
        if verts and tris:
            objects[oid] = (verts, tris)

    if not objects:
        raise ModelError(
            "工程里的网格是空的（没有顶点/三角形）。\n"
            "如果你只保存了参数、盘面上没有模型，请先在 Bambu Studio 里摆好模型再保存工程。")

    # ---- build：哪几个对象真的在盘面上，带什么 transform
    placed: list[tuple[str, list[float], list[float]]] = []
    for el in root.iter():
        if _tag(el) != "item":
            continue
        oid = el.get("objectid") or ""
        if oid in objects:
            m, t = _parse_transform(el.get("transform"))
            placed.append((oid, m, t))
    if not placed:                                  # 没 build 就当作全部都在
        placed = [(oid, [1, 0, 0, 0, 1, 0, 0, 0, 1], [0, 0, 0]) for oid in objects]

    # ---- 全局最低 Z：贴床的朝下表面不算悬垂
    global_min_z = float("inf")
    for oid, m, t in placed:
        verts = objects[oid][0]
        if m != [1, 0, 0, 0, 1, 0, 0, 0, 1] or t != [0, 0, 0]:
            zs_iter = (_apply(m, t, *v)[2] for v in verts)
        else:
            zs_iter = (v[2] for v in verts)
        for zz in zs_iter:
            if zz < global_min_z:
                global_min_z = zz
    min_z_guard = global_min_z + max(layer_height * 1.5, 0.2)

    cos_limit = math.cos(math.radians(90.0 - overhang_angle))   # 面与水平面夹角阈值

    profiles: list[ObjectProfile] = []
    total_tris = 0
    any_sampled = False
    for idx, (oid, m, t) in enumerate(placed):
        verts, tris = objects[oid]
        total_tris += len(tris)
        # 超过上限就抽样，保证大文件也不卡。
        # stride 用 ceil：保证抽样后确实不超过预算，而且不会因为整除退化成 1
        # （旧写法 len//budget 在面数超预算 2 倍时会算出 1，等于没抽样）。
        budget = max(1, MAX_TRIS // max(1, len(placed)))
        stride = max(1, math.ceil(len(tris) / budget))
        if stride > 1:
            # 确定性伪随机抽样：按三角形下标做哈希取样。
            # 不能用 tris[::stride]——那与面在文件里的排列顺序强相关，
            # 某些 STL 的面序会让抽样结果偏向某一侧（实测四面锥会被抽成体积 0）。
            keep = [tr for i, tr in enumerate(tris)
                    if (i * 2654435761) % stride == 0]
            sub_tris = keep if keep else tris
        else:
            sub_tris = tris
        obj = _analyse_object(oid, idx, verts, sub_tris,
                              m, t, overhang_cos=cos_limit, min_z_guard=min_z_guard)
        if obj is None:
            continue
        if stride > 1:
            # 抽样时面积/体积要补回来；分层面积同样要补，
            # 否则 top_cap_ratio / footprint / neck_ratio 会系统性偏小，
            # 封闭的顶面会被误判成「开口容器」。
            obj.surface *= stride
            obj.overhang_area *= stride
            obj.volume *= stride
            for bd in obj.bands:
                bd.area *= stride
                bd.up_area *= stride
            any_sampled = True
        profiles.append(obj)

    if not profiles:
        raise ModelError("网格里没有有效三角形，无法分析形状。")

    prof = ModelProfile(objects=profiles, triangles=total_tris)
    prof.min_z = min(o.min_z for o in profiles)
    prof.size_x = max(o.size_x for o in profiles)
    prof.size_y = max(o.size_y for o in profiles)
    prof.size_z = max(o.size_z for o in profiles)
    prof.volume = sum(o.volume for o in profiles)
    prof.surface = sum(o.surface for o in profiles)
    prof.overhang_area = sum(o.overhang_area for o in profiles)
    # 底面积 = 各对象底面积之和（盘面同时打印，面积相加）
    prof.footprint = sum(o.footprint for o in profiles)
    prof.centre_offset = max((o.centre_offset for o in profiles), default=0.0)
    prof.layers = int(prof.size_z / max(layer_height, 0.02)) + 1
    prof.sampled = any_sampled
    return prof


# ------------------------------------------------------------------ 形状 → 参数策略
# 说明：真正的「按件调参」策略放在 core/shape_rules.py（规则表在 rules JSON 里，
# 用户可直接编辑）。这里只保留一个内置兜底实现，供旧调用方使用。

def suggestions(profile: ModelProfile, *, layer_height: float = 0.2,
                mode: str = "balanced") -> tuple[dict, list[str]]:
    """按形状给出一层参数覆盖（set/mul 运算）与说明（内置兜底规则）。"""
    from . import shape_rules
    ops, notes = shape_rules.default_suggestions(profile, layer_height=layer_height, mode=mode)
    return ops, notes


def layers_for(profile: ModelProfile, layer_height: float) -> int:
    return int(profile.size_z / max(layer_height, 0.02)) + 1
