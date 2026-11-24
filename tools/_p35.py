import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

anchor = "        # ---- 8a"
i = s.find(anchor)
if i < 0:
    i = s.find("        # ---- 8")
if i < 0:
    raise SystemExit("找不到 8a 钳制段")

block = '''        # ---- 7.75：裙边定量（小件 / 底面小 / 易倒 → 加宽裙边）
        # 「倒不倒」用倾覆指数算：高 ÷ √底面积 ×(1+重心偏移比)
        if model_profile is not None:
            try:
                lw = 0.42
                try:
                    lw = float(values.get("line_width") or 0.42)
                except (TypeError, ValueError):
                    pass
                ad_ops, ad_notes, ad_rows = adhesion.tune(
                    model_profile,
                    line_width=lw,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    filament_key=filament_key,
                    mode=mode_key,
                    current=dict(values))
                if ad_ops:
                    self._apply_ops(values, reasons, ad_ops, "裙边定量（易倒件）",
                                    warnings, allow_preserve=True, respect_locked=False)
                notes.extend(ad_notes)
                for r in ad_rows:
                    self._derivations.append(r.as_dict())
            except Exception as exc:
                warnings.append(f"裙边定量计算失败（已跳过）：{exc}")

        # ---- 7.76：支撑按模型尺寸定量（密度/间隙/安全距/形态）
        if model_profile is not None:
            try:
                su = support_model.tune(
                    model_profile,
                    layer_height=float(values.get("layer_height", 0.2) or 0.2),
                    mode=mode_key,
                    values=dict(values))
                if su.ops:
                    self._apply_ops(values, reasons, su.ops, "支撑按模型尺寸",
                                    warnings, allow_preserve=True, respect_locked=False)
                notes.extend(su.reasons)
                for r in su.rows:
                    self._derivations.append(r.as_dict())
            except Exception as exc:
                warnings.append(f"支撑按模型计算失败（已跳过）：{exc}")

'''
s = s[:i] + block + s[i:]
io.open(p, "w", encoding="utf-8").write(s)
print("已插入 7.75 / 7.76 两段")
