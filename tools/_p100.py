import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

anchor = '''                warnings.append(
                    f"{s.label} 受体积流量上限约束（{max_flow:g} mm³/s，{src}），"
                    f"已从 {v:g} 降到 {values[speed_key]:g} mm/s。想更快需要换高流量热端。"
                )'''

addition = anchor + '''

        # 支撑接触面必须比支撑本体慢（接触面决定好不好撕）。
        # 流量钳制会把两者都压到同一个上限，这里把比例再拉回来。
        try:
            body = float(values.get("support_speed") or 0)
            iface = float(values.get("support_interface_speed") or 0)
            if body > 0 and iface >= body * 0.95:
                values["support_interface_speed"] = round(max(10.0, body * 0.6), 1)
                reasons.setdefault("support_interface_speed", []).append(
                    f"支撑接触面要慢于本体（本体 {body:g} → 接触面 ×0.6），"
                    f"已调整到 {values['support_interface_speed']:g} mm/s。")
        except (TypeError, ValueError):
            pass'''

assert anchor in s, "没找到流量钳制的告警文案"
if "支撑接触面必须比支撑本体慢" not in s:
    s = s.replace(anchor, addition, 1)

io.open(p, "w", encoding="utf-8").write(s)
print("引擎：接触面速度比例已恢复")
