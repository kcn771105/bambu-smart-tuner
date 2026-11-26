"""报告导出：Markdown / CSV / 纯文本摘要"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from . import brief, schema, shape_rules, studio_ui
from .detector import Detection
from .rules_engine import OptResult
from .scope import SCOPE_LABEL


def build_markdown(project_path: str, det: Detection, result: OptResult,
                   output_path: str | None = None,
                   model_profile=None, custom_overlay: dict | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    add = lines.append

    add("# Bambu Smart Tuner 参数优化报告")
    add("")
    add(f"- 生成时间：{now}")
    add(f"- 源工程：`{project_path}`")
    if output_path:
        add(f"- 输出工程：`{output_path}`")
    add(f"- 机型：**{result.printer_label}**（识别原值：{det.printer_raw or '空'}）")
    add(f"- 耗材：**{result.filament_label}**（识别原值：{det.filament_raw or '空'}）")
    if custom_overlay:
        add(f"- 自定义耗材：**{custom_overlay.get('label', '')}**"
            f"（族 {custom_overlay.get('family', '?')}，来自 {custom_overlay.get('source', '苯')}："
            f"`{custom_overlay.get('path', '')}`）")
        ov_lim = (custom_overlay.get("limits") or {}).get("max_volumetric_speed")
        if ov_lim:
            add(f"  - 该耗材标定的体积流量上限：{ov_lim} mm³/s")
        if custom_overlay.get("chain"):
            add(f"  - 预设继承链：{' → '.join(custom_overlay['chain'])}")
    add(f"- 喷嘴：**{result.nozzle:g} mm**")
    if getattr(result, "hotend", ""):
        add(f"- {result.hotend}")
    if getattr(result, "plate", ""):
        add(f"- {result.plate}")
    if result.flow_limit:
        add(f"- 体积流量上限：**{result.flow_limit:g} mm³/s**"
            f"（已按 {result.nozzle:g} 喷嘴标定折算）")
    hw_proj = getattr(result, "project_nozzle", None)
    if hw_proj and abs(float(hw_proj) - float(result.nozzle)) > 1e-6:
        add(f"- **喷嘴已更换**：工程里装的是 {float(hw_proj):g} mm，本次按 "
            f"{result.nozzle:g} mm 计算；层高/线宽等比缩放，体积流量上限按官方"
            f"「耗材 × 机型 × {result.nozzle:g} 喷嘴」标定重新折算过"
            f"（换喷嘴不换流量，0.2 喷嘴会被按 0.4 的流量算速度，物理跑不到）。")
    add(f"- 优化模式：**{result.mode_label}**")
    if model_profile is not None:
        add(f"- 模型形状：{model_profile.summary()}")
        tags = model_profile.tags()
        if tags:
            add(f"- 形状标签：{'、'.join(tags)}")
    add(f"- 改动参数：**{result.changed_count}** 项；预估打印时长：**{result.time.text}**")
    add("")

    if result.warnings:
        add("## 警告")
        add("")
        for w in result.warnings:
            add(f"- {w}")
        add("")

    if result.notes:
        add("## 说明")
        add("")
        for n in result.notes:
            add(f"- {n}")
        add("")

    # 结论卡：先讲「这样调完会怎样」，参数表放后面（用户反馈：参数值太多看不懂）
    try:
        card = brief.build(
            result,
            thermal_rows=getattr(result, "thermal_rows", None),
            machine_note=getattr(result, "machine_sync_note", ""),
            support_ease=getattr(result, "support_ease", "standard"))
    except Exception:
        card = []
    if card:
        add("## 一句话结论")
        add("")
        add(f"**{card[0]}**")
        add("")
        for line in card[1:]:
            add(f"- {line}")
        add("")

    add("## 参数对比")
    add("")
    current_group = None
    for row in result.rows:
        if row.group != current_group:
            current_group = row.group
            add("")
            add(f"### {row.group_label}")
            add("")
            add("| 参数 | Studio 里在哪 | 归属 | 原始 | 优化后 | 写入 | 原因 |")
            add("| --- | --- | --- | --- | --- | --- | --- |")
        mark = "" if row.changed else "（不变）"
        reason = row.reason.replace("|", "／")
        write = "是" if (row.changed and row.will_write) else ("否" if row.changed else "—")
        spot = studio_ui.info(row.key, fallback_label=row.label, group=row.group)
        add(f"| {row.label}{mark} | {spot.path.replace('|', '／')} | "
            f"{SCOPE_LABEL.get(row.scope, row.scope)} | "
            f"{row.old_display} | {row.new_display} | {write} | {reason} |")
    add("")

    thermal_rows = getattr(result, "thermal_rows", None) or []
    thermal_text = getattr(result, "thermal", "") or ""
    if thermal_rows or thermal_text:
        add("## 热床与风速（耗材 × 板子 × 室温）")
        add("")
        if thermal_text:
            add(f"- {thermal_text}")
            add("")
        add("热床温度按「耗材 × 板子」查基线，再按室温补偿；风扇按耗材基线给，"
            "冷天自动再降一档。这两类是**耗材页**的键，写入时会在耗材槽里声明为"
            "「与预设不同」，否则 Bambu Studio 会按预设把它们盖回默认值。")
        add("")
        if thermal_rows:
            add("| 指标 | 现在 | 公式 | 结论 |")
            add("| --- | --- | --- | --- |")
            for d in thermal_rows:
                add(f"| {d.get('metric', '')} | {d.get('measured', '')} | "
                    f"{str(d.get('formula', '')).replace('|', '／')} | "
                    f"{str(d.get('conclusion', '')).replace('|', '／')} |")
            add("")

    seam = getattr(result, "seam", None) or ""
    if seam:
        add("## 接缝与斜接缝")
        add("")
        add("圆柱 / 细长件的竖直接缝会在同一侧连成一条线，最显眼。这里把接缝对齐到"
            "背面并打开斜接缝（scarf joint），让收尾处沿层高方向搭接过渡。"
            "具体按什么算出来的，见下一节「按模型实测尺寸推导」里的 `接缝位置 seam_position`"
            " 与 `斜接缝 scarf` 两行。")
        add("")
        add(f"- {seam}")
        add("")

    machine_note = getattr(result, "machine_sync_note", "")
    if machine_note:
        add("## 机型同步")
        add("")
        add(f"- {machine_note}")
        add("")

    if model_profile is not None and getattr(model_profile, "objects", None):
        add("## 逐件调参明细")
        add("")
        add("Bambu Studio 的切片参数是**整盘全局**的，没法给单个对象单独设值。"
            "本程序的做法是：逐个对象判形状原型 → 每个原型给一套覆盖全部工艺组的建议 → "
            "合并成全局值时**同一个键取所有对象里最保守的那个**。")
        add("")
        add("| 对象 | 尺寸 / 体积 | 形状原型 | 判定依据 |")
        add("| --- | --- | --- | --- |")
        for obj in model_profile.objects:
            try:
                pkey, why = shape_rules.classify(obj)
                label = (shape_rules.PROTO_BY_KEY[pkey].label
                         if pkey in shape_rules.PROTO_BY_KEY else pkey)
            except Exception:
                label, why = "—", []
            add(f"| 件{obj.index + 1} | {obj.summary()} | {label} | "
                f"{'、'.join(why) if why else '未触发特殊特征'} |")
        add("")

    derivs = getattr(result, "derivations", None) or []
    if derivs:
        add("## 按模型实测尺寸推导")
        add("")
        add("这一节是「凭什么这么调」的硬依据：每条都由模型自己的尺寸算出来，"
            "不是套模板。公式列可以直接手算复核。")
        add("")
        add("| 指标 | 实测 | 公式 | 结论 |")
        add("| --- | --- | --- | --- |")
        for d in derivs:
            add(f"| {d.get('metric', '')} | {d.get('measured', '')} | "
                f"{str(d.get('formula', '')).replace('|', '／')} | "
                f"{str(d.get('conclusion', '')).replace('|', '／')} |")
        add("")

    if result.blocked:
        add("## 数组型参数（按热端变体分槽）")
        add("")
        add("`outer_wall_speed`、`inner_wall_speed`、`*_acceleration`、`travel_speed` 这类键"
            "在工程里是数组，一个槽位对应一种热端：`[\"200\", \"500\", \"500\"]`"
            "（标准流量 / 高流量 / E3D 高流量）。Bambu Studio 显示的是**当前所选热端**"
            "那一槽的值，只改第 0 槽时若你的 Studio 选的是「高流量」就会读第 1 槽，"
            "看起来像「速度没改」。因此本程序把这些键的**每一槽都写成同一个优化值**"
            "（保守值，任何热端下都生效）；没有变体列表的工程仍只改第 0 槽。")
        add("")
        add("## 只读参数（按要求原样保留）")
        add("")
        add("下列参数属于耗材页 / 机器页 / 元数据，本程序**只读不改**；"
            "它们的真实上限值仍被用来约束工艺参数（例如机器速度上限、"
            "热端体积流量上限、板面尺寸）。")
        add("")
        by_scope: dict[str, list] = {}
        for row in result.blocked:
            by_scope.setdefault(row.scope, []).append(row)
        for sc, rows in sorted(by_scope.items()):
            add(f"### {SCOPE_LABEL.get(sc, sc)}（{len(rows)} 项）")
            add("")
            for row in rows:
                add(f"- {row.label}（`{row.key}`）：{row.old_display}")
            add("")

    if result.skipped:
        add("## 未写入的参数")
        add("")
        add("下列参数在你的工程文件里不存在（Bambu Studio 没有为当前机型/版本存储它们），"
            "程序只给出推荐值，没有写入，避免引入脏键：")
        add("")
        for row in result.skipped:
            add(f"- {row.label}（`{row.key}`）：推荐 {row.new_display}")
        add("")

    add("## 已知限制")
    add("")
    for item in LIMITATIONS:
        add(f"- {item}")
    add("")
    add("---")
    add("")
    add("本报告由 Bambu Smart Tuner 自动生成。参数写入的是 3mf 的 "
        "`Metadata/project_settings.config`，模型几何、对象级覆盖设置均未改动。")
    return "\n".join(lines)


def build_summary(det: Detection, result: OptResult) -> str:
    return (
        f"机型 {result.printer_label} / 耗材 {result.filament_label} / "
        f"喷嘴 {result.nozzle:g} mm / 模式 {result.mode_label}；"
        f"改动 {result.changed_count} 项；预估时长 {result.time.text}"
    )


def rows_to_csv(rows, path: str | Path) -> Path:
    p = Path(path)
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["分组", "参数键", "参数名", "原始值", "优化后值", "是否改动", "写入", "原因"])
        for r in rows:
            w.writerow([
                r.group_label, r.key, r.label, r.old_display, r.new_display,
                "是" if r.changed else "否",
                "是" if r.will_write else "否（工程无此键）",
                r.reason,
            ])
    return p


def write_markdown(text: str, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(text, encoding="utf-8")
    return p


LIMITATIONS = [
    "只修改 3mf 里的 `Metadata/project_settings.config`；几何、对象级个性化设置（model_settings.config）不动。",
    "喷头温度、热床温度按「耗材 × 板子 × 室温」推导后写入耗材槽（v1.2 起）；"
    "腔体温度、压力提前量等仍沿用耗材预设，本版不改。",
    "热床/风扇参数写在耗材槽，一份工程只按第一种耗材的基线推导；"
    "多耗材工程里其他耗材如需同步，请分别在软件里按该耗材再导一次。",
    "Bambu Studio 的「工程设置」窗口里若手动再改，可能覆盖本次优化，请优化完直接切片。",
    "部分参数（摩擦补偿、支撑样式、辅助风扇等）在新版才有；工程里没有该键时程序只给推荐值不写入。",
    "打印时长是相对指数估算（±3% 量级误差），不是精确值；精确时长以 Bambu Studio 切片结果为准。",
    "多耗材/多喷嘴工程只按第一种耗材、第一个喷嘴计算。",
    "P2 系列的硬件上限按 Bambu Studio 自带机器预设读取；个别固件差异可能让实际可用值不同。",
    "不支持 .gcode.3mf（已切片的模型包）：那种文件里没有完整工程参数，请重新保存工程。",
    "自定义耗材同步只读 Bambu Studio / OrcaSlicer 的用户预设目录，不写回、不改动它的配置。",
    "形状自适应用的是几何统计（包围盒/体积/表面积/悬垂面占比），不做逐层切片仿真；"
    "极端模型（大量桥接、螺旋花瓶模式、多材料混打）只能给到方向性建议。",
    "同步到的自定义耗材若父预设缺失（Bambu Studio 装在非默认路径），会退化到按族基线处理并在列表里标 ⚠。",
]
