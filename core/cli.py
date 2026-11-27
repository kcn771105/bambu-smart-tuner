"""命令行入口：不给 GUI 也能用，方便批处理与脚本调用。

    python -m core.cli analyze 工程.3mf
    python -m core.cli optimize 工程.3mf -m quality -o 输出.3mf
    python -m core.cli batch 目录 --pattern "*.3mf" -m balanced
    python -m core.cli sync-filaments --export my_filaments.json
    python -m core.cli rules

或者直接：python cli.py <同样参数>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):                       # 允许 python cli.py 直接跑
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (bambu_profiles, detector, hardware, machine_sync,  # noqa: E402
                  model_analysis, preset_diff, report, rules_engine, schema,
                  seam_plan, slice_check, studio_env, support_model, thermal,
                  threemf)


def _fmt(v) -> str:
    return "—" if v is None else str(v)


def cmd_analyze(a) -> int:
    rules = rules_engine.load_rules(a.rules)
    proj = threemf.ThreeMfProject.load(a.file)
    det = detector.detect(proj, rules)
    print(f"文件      : {proj.path}")
    print(f"条目      : {len(proj.entries)} 个，切片参数 {len(proj.settings)} 个")
    print(f"机型      : {det.printer_label}  [key={det.printer_key}]  原始={_fmt(det.printer_raw)}")
    print(f"耗材      : {det.filament_label}  [key={det.filament_key}]  原始={_fmt(det.filament_raw)}")
    print(f"喷嘴      : {det.nozzle:g} mm  原始={_fmt(det.nozzle_raw)}")
    print(f"已切片    : {'是（保存时会清掉旧切片结果）' if proj.is_sliced else '否'}")
    for w in det.warnings:
        print(f"  ⚠ {w}")
    for n in det.notes:
        print(f"  · {n}")
    try:
        lh = schema.parse_value(schema.PARAMS["layer_height"],
                                proj.settings.get("layer_height")) or 0.2
        prof = model_analysis.analyse(proj, layer_height=lh)
        print(f"模型形状  : {prof.summary()}")
        print(f"形状标签  : {'、'.join(prof.tags()) or '—'}")
        print(f"底面积    : {prof.footprint:.0f} mm²   细高比 {prof.slender:.2f}   "
              f"薄壁指数 {prof.thickness_index:.2f}   质心偏 {prof.centre_offset:.2f}")
    except model_analysis.ModelError as exc:
        print(f"模型形状  : 读不到几何（{exc}）")
    return 0


def _pick_cli_plate(proj, want: str) -> tuple[str, float | None]:
    """挑一块本机 Studio 认识的板子；工程原来那块它不认识就换一块，并把原板温带过去。

    返回 (写进文件的板名, 要沿用的板温或 None)。
    """
    try:
        env = studio_env.detect()
    except Exception:
        return want, None
    if not env.found or not env.plates:
        return want, None
    target = thermal.normalize_plate(want) or want if want else ""
    if not target:
        target = thermal.bed_type_of(proj.settings)
    if target in env.plates:
        return want, None
    alt = ""
    for name in ("Textured PEI Plate", "Smooth PEI Plate / High Temp Plate",
                 "Engineering Plate", "Cool Plate"):
        if name in env.plates:
            alt = name
            break
    if not alt:
        return want, None
    keep = thermal.read_bed_temp(proj.settings, target)
    msg = (f"工程用的是「{thermal.plate_label(target)}」，本机 Studio {env.version} "
           f"没有这块板 —— 已换成「{thermal.plate_label(alt)}」"
           + (f"，板温保持为 {keep:.0f}°C。" if keep else "。"))
    try:
        print("⚠ " + msg)
    except UnicodeEncodeError:          # 老控制台 cp936 编不出 ⚠/中文
        print(msg.encode("ascii", "replace").decode("ascii"))
    return alt, keep


def _parse_special(items) -> dict:
    """把 --special spiral_mode=1 --special ironing_type=top 解析成 {key: value}。"""
    out: dict[str, str] = {}
    for item in (items or []):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def _do_optimize(path: Path, a, engine, overlay: dict | None, rules) -> tuple[threemf.ThreeMfProject, object, object, object]:
    proj = threemf.ThreeMfProject.load(path)
    det = detector.detect(proj, rules)
    printer = a.printer or det.printer_key
    filament = a.filament or det.filament_key
    nozzle = a.nozzle or det.nozzle
    if overlay and overlay.get("family"):
        filament = overlay["family"]
    profile = None
    if not a.no_shape:
        try:
            lh = schema.parse_value(schema.PARAMS["layer_height"],
                                    proj.settings.get("layer_height")) or 0.2
            profile = model_analysis.analyse(proj, layer_height=lh)
        except model_analysis.ModelError:
            profile = None
    hw = hardware.read(proj)
    bed_choice, bed_keep = _pick_cli_plate(proj, getattr(a, "bed", "") or "")
    res = engine.optimize(
        proj.settings, printer_key=printer, filament_key=filament, nozzle=nozzle,
        mode_key=a.mode, detection_warnings=list(det.warnings) if a.printer is None else [],
        detection_notes=list(det.notes), filament_overlay=overlay,
        model_profile=profile, time_cap_pct=None if a.no_cap else a.cap,
        hardware_info=hw,
        nozzle_explicit=bool(a.nozzle),
        support_mode=getattr(a, "support", "auto"),
        support_ease=getattr(a, "ease", "standard"),
        room_temp_c=getattr(a, "room", None),
        bed_type=bed_choice,
        fan_trim=getattr(a, "fan_trim", None),
        seam_smooth=not getattr(a, "no_seam", False),
        ironing_choice=getattr(a, "ironing", "keep"),
        ironing_auto=not getattr(a, "no_iron_auto", False),
        filament_mode=getattr(a, "filament_mode", "file"),
        special_modes=_parse_special(getattr(a, "special", None)),
        bed_keep_temp=bed_keep)
    return proj, det, res, profile


def cmd_optimize(a) -> int:
    rules = rules_engine.load_rules(a.rules)
    engine = rules_engine.RulesEngine(rules)
    overlay = None
    if a.custom_filament:
        presets = bambu_profiles.scan()
        match = next((p for p in presets if p.name == a.custom_filament), None)
        if match is None:
            names = [p.name for p in presets]
            print(f"没找到自定义耗材「{a.custom_filament}」。可用：{names}", file=sys.stderr)
            return 2
        overlay = bambu_profiles.to_overlay(match)

    proj, det, res, profile = _do_optimize(Path(a.file), a, engine, overlay, rules)
    written, skipped = proj.apply(
        res.write_values,
        allow_missing=(thermal.STANDARD_KEYS | machine_sync.SYNC_KEYS
                       | seam_plan.STANDARD_KEYS
                       | support_model.SUPPORT_KEYS))
    # v1.2：机型和界面不一致时同步机器页，否则 Studio 打开会按旧机型覆盖回来
    mp = machine_sync.plan(rules, printer_key=det.printer_key if a.printer is None else a.printer,
                           nozzle=res.nozzle, detected_key=det.printer_key,
                           current=proj.settings)
    if mp.ops:
        proj.apply(mp.ops, allow_missing=machine_sync.SYNC_KEYS)
    preset_diff.apply_to_project(
        proj, also=list(res.write_values.keys()) + list(mp.ops.keys()))
    out = proj.save_as(a.out) if a.out else proj.save_copy()
    for n in mp.notes:
        print(f"机型同步  : {n}")
    for w in mp.warnings:
        print(f"  ⚠ {w}")

    print(f"源工程    : {proj.path}")
    print(f"输出      : {out}")
    print(f"机型/耗材 : {res.printer_label} / {res.filament_label}  喷嘴 {res.nozzle:g} mm")
    print(f"模式      : {res.mode_label}")
    if profile is not None:
        print(f"形状      : {profile.summary()}")
    print(f"改动      : {res.changed_count} 项写入 {len(written)} 项，跳过 {len(skipped)} 项")
    print(f"时长      : {res.time.text}")
    if getattr(engine, "last_timecap", None):
        c = engine.last_timecap
        print(f"时长上限  : 上限 {c['cap']:g}%  原方案 {c['before']:+.1f}%  →  最终 {c['after']:+.1f}%"
              f"{'（未达标）' if not c['met'] else ''}")
    if res.warnings:
        print("警告:")
        for w in res.warnings:
            print("  ⚠ " + w)
    if a.md:
        md = report.build_markdown(str(proj.path), det, res,
                                   output_path=str(out), model_profile=profile,
                                   custom_overlay=overlay)
        md_path = Path(a.md) if a.md != "auto" else out.with_suffix(".md")
        md_path.write_text(md, encoding="utf-8")
        report.rows_to_csv(res.rows, md_path.with_suffix(".csv"))
        print(f"报告      : {md_path}（+ 同名 .csv）")
    return 0


def cmd_batch(a) -> int:
    rules = rules_engine.load_rules(a.rules)
    engine = rules_engine.RulesEngine(rules)
    root = Path(a.dir)
    files = sorted(root.glob(a.pattern))
    if a.recursive:
        files = sorted(root.rglob(a.pattern))
    files = [f for f in files if f.suffix.lower() in (".3mf", ".bambu")]
    if not files:
        print(f"{root} 下没有匹配 {a.pattern} 的 3mf 文件", file=sys.stderr)
        return 2
    outdir = Path(a.outdir) if a.outdir else root / "optimized"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"批量处理 {len(files)} 个文件 → {outdir}\n")
    ok = fail = 0
    for f in files:
        try:
            proj, det, res, profile = _do_optimize(f, a, engine, None, rules)
            target = outdir / f"{f.stem}_optimized.3mf"
            if a.md:
                md = report.build_markdown(str(f), det, res, output_path=str(target),
                                           model_profile=profile)
                md_name = outdir / f"{f.stem}_optimized.md"
                md_name.write_text(md, encoding="utf-8")
                report.rows_to_csv(res.rows, md_name.with_suffix(".csv"))
            proj.apply(res.write_values,
                       allow_missing=(thermal.STANDARD_KEYS | machine_sync.SYNC_KEYS
                                      | seam_plan.STANDARD_KEYS
                                      | support_model.SUPPORT_KEYS))
            preset_diff.apply_to_project(proj, also=list(res.write_values.keys()))
            proj.save_as(target)
            print(f"  ✓ {f.name:40s} {res.changed_count:3d} 项改动  {res.time.delta_pct:+6.1f}%")
            ok += 1
        except Exception as exc:                    # 单个失败不影响其余
            print(f"  ✗ {f.name:40s} {type(exc).__name__}: {exc}", file=sys.stderr)
            fail += 1
    print(f"\n完成：成功 {ok}，失败 {fail}")
    return 0 if fail == 0 else 1


def cmd_sync(a) -> int:
    presets = bambu_profiles.scan()
    print(bambu_profiles.describe(presets))
    for p in presets:
        flag = "" if p.resolvable else "  ⚠ 父链缺失"
        print(f"  [{p.source}] {p.name}  ← {p.family}{flag}")
        print(f"      {p.display_detail}")
        if p.chain:
            print(f"      继承链: {' → '.join(p.chain)}")
    if presets and a.export:
        out = bambu_profiles.export_overlays(presets, a.export)
        print(f"\n已导出：{out}")
    return 0


def cmd_rules(a) -> int:
    rules = rules_engine.load_rules(a.rules)
    engine = rules_engine.RulesEngine(rules)
    print(f"规则库：{rules_engine.default_rules_path()}")
    print(f"版本  ：{rules.get('meta', {}).get('version', '?')}")
    print(f"机型  ：{len(engine.printers)} 个 — " + "、".join(
        v.get("label", k) for k, v in engine.printers.items()))
    print(f"耗材  ：{len(engine.filaments)} 个 — " + "、".join(
        v.get("label", k) for k, v in engine.filaments.items()))
    print(f"模式  ：{len(engine.modes)} 个 — " + "、".join(
        v.get("label", k) for k, v in engine.modes.items()))
    print(f"交叉  ：{len(engine.interactions)} 条")
    print(f"参数  ：{len(schema.PARAMS)} 个（其中 {sum(1 for s in schema.PARAMS.values() if s.soft)} 个为可缺失键）")
    probs = engine.validate()
    if probs:
        print("\n自检问题:")
        for p in probs:
            print("  ⚠ " + p)
        return 1
    print("\n自检：通过")
    return 0


def cmd_verify(a) -> int:
    """切一片，看参数是不是真的进了 gcode。"""
    from . import slice_check

    proj = threemf.ThreeMfProject.load(a.file)
    # 先取「工具声明过差异」的全部键 —— 那才是这次改动过的每一项；
    # 老工程没有声明数组时退回原来那几项特征值。
    declared = []
    raw = proj.settings.get("different_settings_to_system")
    if isinstance(raw, str):
        try:
            arr = json.loads(raw)
        except ValueError:
            arr = []
        for slot in (arr if isinstance(arr, list) else [arr]):
            if isinstance(slot, list):
                declared.extend(str(x) for x in slot)
            elif slot:
                declared.extend(str(slot).split(";"))
    declared = [k.strip() for k in declared if k.strip()]
    # gcode 模板这几项在兼容副本里被换过，逐键比没有意义（它们不是打印参数）
    skip = {"machine_start_gcode", "machine_end_gcode", "change_filament_gcode",
            "layer_change_gcode", "before_layer_change_gcode", "time_lapse_gcode",
            "printing_by_object_gcode", "machine_pause_gcode", "template_custom_gcode",
            # 元信息，不是打印参数
            "from", "name", "version", "is_custom_defined", "setting_id", "base_id"}
    keys = [k for k in declared if k in proj.settings and k not in skip]         or list(slice_check.CHECKED_KEYS)
    want = {k: proj.settings[k] for k in keys if k in proj.settings}
    for bed in ("supertack_plate_temp", "textured_plate_temp", "hot_plate_temp",
                "eng_plate_temp", "cool_plate_temp"):
        if bed in proj.settings:
            want.setdefault(bed, proj.settings[bed])
            break
    if "enable_support" in proj.settings:
        want.setdefault("enable_support", proj.settings["enable_support"])

    print(f"切片器 : {slice_check.find_studio(a.studio or '') or '（没找到）'}")
    res = slice_check.run_slice_check(a.file, want, studio=a.studio or "",
                                      out_dir=a.outdir or "")
    for note in res.notes:
        print(f"· 兼容处理：{note}")
    for warn in res.warnings:
        print(f"⚠ {warn}")
    if res.log_tail:
        print("切片器输出（尾部）：")
        for line in res.log_tail.splitlines():
            print("    " + line)
    if not res.probe:
        return 1

    p = res.probe
    print(f"gcode   : {res.gcode}")
    print(f"层数    : {p.layers} ｜ 预计时间：{p.time_text} ｜ 支撑路径：{p.support_moves} 条")
    print()
    print(f"{'参数':<26}{'文件里的值':>12}{'gcode 里的值':>14}   结果")
    bad = 0
    for key, want_s, got_s, ok in res.rows:
        print(f"{key:<26}{want_s:>12}{got_s:>14}   {'一致' if ok else '不一致'}")
        bad += 0 if ok else 1
    print()
    print(f"{'参数全部一致' if not bad else str(bad) + ' 项不一致'}："
          f"{len(res.rows) - bad}/{len(res.rows)}")

    # 全量核对：写入的每一项，切片器是否真的采用
    all_rows = res.all_rows or []
    if all_rows:
        over = [row for row in all_rows if row[3] == "overridden"]
        absent = res.effective_absent or []
        print()
        print("—— 全量核对（写入的每一项 vs 切片器实际采用）——")
        print(f"{'参数':<28}{'写进去的':>12}{'gcode 里':>12}   结果")
        for key, want_s, got_s, verdict in all_rows:
            tag = {"ok": "生效", "overridden": "被改写", "absent": "不参与切片"}[verdict]
            print(f"{key:<28}{str(want_s):>12}{str(got_s):>12}   {tag}")
        print()
        print(f"写入 {len(all_rows)} 项：切片器采用一致 {res.effective_ok} 项 | "
              f"被改成别的值 {len(over)} 项 | 不参与切片 {len(absent)} 项")
        if over:
            print("⚠ 这些键切片器没采用文件里的值："
                  + "、".join(row[0] for row in over))
            return 2
    return 0 if bad == 0 else 2


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 cp936，遇到 mm³/s、⚠ 这类字符会直接 UnicodeEncodeError 崩掉。
    # 改为 UTF-8 + replace，宁可显示成 ? 也不要让整条命令挂掉。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="bambu-smart-tuner",
        description="Bambu Smart Tuner 命令行：分析 / 优化 Bambu Studio 工程 3mf")
    ap.add_argument("--rules", default=None, help="规则库 JSON 路径（默认用内置）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("analyze", help="只分析：识别机型/耗材/形状")
    p1.add_argument("file")
    p1.set_defaults(func=cmd_analyze)

    def add_opt_args(p):
        p.add_argument("-m", "--mode", default="balanced",
                       choices=("strength", "quality", "balanced",
                                "draft", "fine", "ultrafine"))
        p.add_argument("-o", "--out", default=None, help="输出 3mf 路径")
        p.add_argument("--printer", default=None, help="覆盖机型 key，如 X1C/P1S/A1mini")
        p.add_argument("--filament", default=None, help="覆盖耗材族，如 PLA/PETG/ABS/ASA/TPU")
        p.add_argument("--nozzle", type=float, default=None, help="覆盖喷嘴直径")
        p.add_argument("--custom-filament", default=None,
                       help="用已同步的某支自定义耗材（名字要完全一致）")
        p.add_argument("--cap", type=float, default=25.0, help="时长涨幅上限 %%，默认 25")
        p.add_argument("--no-cap", action="store_true", help="不限制时长涨幅")
        p.add_argument("--support", choices=("auto", "on", "off"), default="auto",
                       help="支撑开关：auto=按模型判断（默认）、on=强制开启、off=强制关闭")
        p.add_argument("--bed", default=None,
                       help="打印板类型，如 \"Textured PEI Plate\"（默认读工程里的 curr_bed_type）")
        p.add_argument("--room", type=float, default=None,
                       help="室温 °C（给热床/风扇做冷天补偿；不给则按工程/默认）")
        p.add_argument("--fan-trim", type=int, default=0,
                       help="风扇整体偏置百分点，负数更保守（防翘边），如 -10")
        p.add_argument("--ease", choices=("standard", "easy", "max"), default="standard",
                       help="支撑好拆程度：standard/easy/max，默认 standard")
        p.add_argument("--no-seam", action="store_true",
                       help="关闭接缝/斜接缝自动调整")
        p.add_argument("--no-shape", action="store_true", help="关闭按模型形状微调")
        p.add_argument("--ironing", choices=("keep", "off", "top", "topmost", "solid"),
                       default="keep",
                       help="熨烫：keep=不动 / off=关掉 / top=只熨顶面 / topmost=所有朝上面 / solid=所有实心层")
        p.add_argument("--no-iron-auto", action="store_true",
                       help="熨烫参数不自动算，只改熨烫类型")
        p.add_argument("--filament-mode", choices=("keep", "file", "new"), default="file",
                       help="耗材页：keep=一个字不写 / file=写进当前耗材 / new=另存为「原名+优化」")
        p.add_argument("--special", action="append", metavar="KEY=VALUE",
                       help="手动指定其他页的特殊模式，可重复，如 --special spiral_mode=1")
        p.add_argument("--md", nargs="?", const="auto", default=None,
                       help="同时导出 Markdown 报告（auto=与输出同名）")

    p2 = sub.add_parser("optimize", help="优化单个工程并另存")
    p2.add_argument("file")
    add_opt_args(p2)
    p2.set_defaults(func=cmd_optimize)

    p3 = sub.add_parser("batch", help="批量优化一个目录")
    p3.add_argument("dir")
    p3.add_argument("--pattern", default="*.3mf")
    p3.add_argument("--recursive", action="store_true")
    p3.add_argument("--outdir", default=None)
    add_opt_args(p3)
    p3.set_defaults(func=cmd_batch)

    p4 = sub.add_parser("sync-filaments", help="扫描 Bambu Studio 的自定义耗材")
    p4.add_argument("--export", default=None, help="导出成 JSON")
    p4.set_defaults(func=cmd_sync)

    p5 = sub.add_parser("rules", help="打印规则库概览并自检")
    p5.set_defaults(func=cmd_rules)

    p6 = sub.add_parser("verify", help="用本机 Bambu Studio 切片一次，核对参数真的生效")
    p6.add_argument("file")
    p6.add_argument("--studio", default=None, help="bambu-studio.exe 路径（默认自动找）")
    p6.add_argument("--outdir", default=None, help="切片临时目录（默认用系统临时目录）")
    p6.set_defaults(func=cmd_verify)

    a = ap.parse_args(argv)
    # batch 的 add_opt_args 也塞了 file，这里删掉免得混淆
    if a.cmd == "batch" and hasattr(a, "file"):
        del a.file
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
