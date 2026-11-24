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
import sys
from pathlib import Path

if __package__ in (None, ""):                       # 允许 python cli.py 直接跑
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import (bambu_profiles, detector, hardware, model_analysis, preset_diff,  # noqa: E402
                  report, rules_engine, schema, threemf)


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
    res = engine.optimize(
        proj.settings, printer_key=printer, filament_key=filament, nozzle=nozzle,
        mode_key=a.mode, detection_warnings=list(det.warnings) if a.printer is None else [],
        detection_notes=list(det.notes), filament_overlay=overlay,
        model_profile=profile, time_cap_pct=None if a.no_cap else a.cap,
        hardware_info=hw,
        nozzle_explicit=bool(a.nozzle),
        support_mode=getattr(a, "support", "auto"))
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
    written, skipped = proj.apply(res.write_values)
    preset_diff.apply_to_project(proj, also=list(res.write_values.keys()))
    out = proj.save_as(a.out) if a.out else proj.save_copy()

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
            proj.apply(res.write_values)
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


def main(argv: list[str] | None = None) -> int:
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
        p.add_argument("--no-shape", action="store_true", help="关闭按模型形状微调")
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

    a = ap.parse_args(argv)
    # batch 的 add_opt_args 也塞了 file，这里删掉免得混淆
    if a.cmd == "batch" and hasattr(a, "file"):
        del a.file
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
