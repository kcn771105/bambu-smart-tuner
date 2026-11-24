"""把「喷嘴流量同步」接进 _clamp_flow。

改动点：
1. import nozzle_flow。
2. `_clamp_flow(...)` 新增形参 `nozzle: float | None = None`、
   `project_nozzle: float | None = None`。
3. 在算出 official 之后、把工程值当上限之前，插入喷嘴折算：
   - 工程标定值是按 `project_nozzle` 标的；用户现在选的是 `nozzle`；
   - 两者不同 → 按官方流量比把工程值折算到新喷嘴，并与新喷嘴的官方上限取小；
   - 追加一条 note 说明「喷嘴 0.4 → 0.2，流量上限 18 → 1」。
4. 两处调用点补传 nozzle / project_nozzle。

用法：python tools/_patch_flow_nozzle.py [--apply]
"""
import io
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "core" / "rules_engine.py"

OLD_SIG = """    def _clamp_flow(self, values, reasons, pnode: dict, fnode: dict, warnings,
                    overlay_max: float | None = None,
                    project_max: float | None = None,
                    printer_key: str = "") -> None:"""

NEW_SIG = """    def _clamp_flow(self, values, reasons, pnode: dict, fnode: dict, warnings,
                    overlay_max: float | None = None,
                    project_max: float | None = None,
                    printer_key: str = "",
                    nozzle: float | None = None,
                    project_nozzle: float | None = None) -> None:"""

OLD_OFFICIAL = """        max_flow = official
        if overlay_max:"""

NEW_OFFICIAL = """        # ---- 喷嘴同步：工程里的流量标定是按工程那个喷嘴标的
        # 用户在下拉里换了喷嘴（例如 0.4 → 0.2），流量上限必须一起换，
        # 否则 0.2 喷嘴会被按 0.4 的 13 mm³/s 去算速度（物理跑不到，堵料）。
        group = pnode.get("group") or printer_key
        noz_official, noz_src = nozzle_flow.limit(
            self.rules, group=group, filament_key=str(fnode.get("key") or ""),
            nozzle=nozzle)
        if noz_official is not None:
            srcs.append(noz_src or f"官方 {nozzle:g} 喷嘴标定 {noz_official:g}")
            official = min(official, noz_official) if official else noz_official
        proj_noz = nozzle_flow.snap_nozzle(project_nozzle)
        pick_noz = nozzle_flow.snap_nozzle(nozzle)
        if (project_max and proj_noz and pick_noz and proj_noz != pick_noz):
            r, rsrc = nozzle_flow.ratio(
                self.rules, group=group, filament_key=str(fnode.get("key") or ""),
                from_nozzle=proj_noz, to_nozzle=pick_noz)
            if r is not None:
                scaled = float(project_max) * r
                notes_flow = (
                    f"喷嘴同步：工程里的流量 {float(project_max):g} mm³/s 是按 "
                    f"{proj_noz:g} 喷嘴标的（{rsrc}），已折算成 {scaled:.1f} mm³/s，"
                    f"再与 {pick_noz:g} 喷嘴的官方上限 {noz_official or 0:g} 取小。")
                warnings.append(notes_flow)
                project_max = scaled
        max_flow = official
        if overlay_max:"""

OLD_CALL = """                    overlay_max=overlay_max, project_max=project_max,
                    printer_key=printer_key)"""

NEW_CALL = """                    overlay_max=overlay_max, project_max=project_max,
                    printer_key=printer_key, nozzle=nozzle,
                    project_nozzle=(hardware_info.nozzle_diameter
                                    if hardware_info is not None else None))"""


def main() -> int:
    apply = "--apply" in sys.argv
    s = io.open(ENGINE, encoding="utf-8").read()
    steps = []

    if "from . import nozzle_flow" not in s:
        old_imp = "from . import estimator, hardware, modes as modes_registry, schema, scope"
        assert old_imp in s, "import 锚点没找到"
        s = s.replace(old_imp,
                      old_imp.replace("estimator, hardware", "estimator, hardware, nozzle_flow"), 1)
        steps.append("加 import")

    if "nozzle: float | None = None," not in s:
        assert OLD_SIG in s, "_clamp_flow 签名没找到"
        s = s.replace(OLD_SIG, NEW_SIG, 1)
        steps.append("扩签名")

    if "喷嘴同步：工程里的流量" not in s:
        assert OLD_OFFICIAL in s, "official 锚点没找到"
        s = s.replace(OLD_OFFICIAL, NEW_OFFICIAL, 1)
        steps.append("插喷嘴折算")

    if "project_nozzle=(hardware_info.nozzle_diameter" not in s:
        if OLD_CALL in s:
            s = s.replace(OLD_CALL, NEW_CALL, 1)
            steps.append("调用点补参")
        else:
            steps.append("⚠ 调用点锚点没匹配，需手查")

    print("\n".join(steps) or "无变化")
    if apply:
        shutil.copy2(ENGINE, ENGINE.with_suffix(".py.bak_nozflow"))
        io.open(ENGINE, "w", encoding="utf-8").write(s)
        print("已写回 core/rules_engine.py")
    else:
        print("（dry-run）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
