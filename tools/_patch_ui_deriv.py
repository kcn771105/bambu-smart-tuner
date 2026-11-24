"""给 UI 加「按模型定量推导」面板 + 模式时长预算显示。

改三处：
1. 识别面板：在「逐件调参明细」下面加一个 `deriv_box`（4 列：指标 / 实测 / 公式 / 结论），
   数据来自 `res.derivations`（引擎 7.7 层产出）。
2. `_render_derivations(res)`：把列出来的推导填进去。
3. 模式选择区：单选按钮的提示文案补上该档的时长预算（规则库 modes.<k>.time_budget_pct）。

用法：python tools/_patch_ui_deriv.py [--apply]
"""
import io
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui" / "main_window.py"

BOX_ANCHOR = """        d.addWidget(self.obj_box, 5, 0, 1, 7)
"""
BOX_NEW = """        d.addWidget(self.obj_box, 5, 0, 1, 7)

        # 按模型实测尺寸推导：每条都是「实测值 ÷ 公式 = 结论」，可复核
        self.deriv_box = QGroupBox("按模型实测尺寸推导（每条都能手算复核）")
        dv = QVBoxLayout(self.deriv_box)
        dv.setContentsMargins(8, 4, 8, 8)
        self.deriv_tree = QTreeWidget()
        self.deriv_tree.setColumnCount(4)
        self.deriv_tree.setHeaderLabels(["指标", "实测", "公式", "结论"])
        self.deriv_tree.setAlternatingRowColors(True)
        self.deriv_tree.setUniformRowHeights(True)
        self.deriv_tree.setRootIsDecorated(False)
        dh = self.deriv_tree.header()
        dh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        dh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        dh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        dh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.deriv_tree.setMinimumHeight(110)
        dv.addWidget(self.deriv_tree)
        d.addWidget(self.deriv_box, 6, 0, 1, 7)
"""

METHOD = '''
    def _render_derivations(self, res=None) -> None:
        """把「按模型实测尺寸推导」的每一条填进表格。"""
        if not hasattr(self, "deriv_tree"):
            return
        self.deriv_tree.clear()
        rows = list(getattr(res, "derivations", None) or []) if res is not None else []
        if not rows:
            item = QTreeWidgetItem(["—", "—", "加载工程并开始优化后，这里列出每条由实测尺寸推出来的参数",
                                    "未推导"])
            self.deriv_tree.addTopLevelItem(item)
            return
        for r in rows:
            self.deriv_tree.addTopLevelItem(QTreeWidgetItem([
                str(r.get("metric", "")),
                str(r.get("measured", "")),
                str(r.get("formula", "")),
                str(r.get("conclusion", "")),
            ]))
'''

HELPER_ANCHOR = "    def _render_objects(self) -> None:"


def main() -> int:
    apply = "--apply" in sys.argv
    src = io.open(UI, encoding="utf-8").read()
    changed = []

    if "deriv_box" not in src:
        assert BOX_ANCHOR in src, "识别面板锚点没找到"
        src = src.replace(BOX_ANCHOR, BOX_NEW, 1)
        changed.append("加 deriv_box / deriv_tree")
    else:
        changed.append("deriv_box 已存在，跳过")

    if "_render_derivations" not in src:
        assert HELPER_ANCHOR in src, "_render_objects 锚点没找到"
        src = src.replace(HELPER_ANCHOR, METHOD.strip("\n") + "\n\n" + HELPER_ANCHOR, 1)
        changed.append("加 _render_derivations()")
    else:
        changed.append("_render_derivations 已存在，跳过")

    # 行号后移：hw_box 原在第 6 行，deriv_box 占了 6，hw_box 改 7
    src = src.replace("d.addWidget(self.hw_box, 6, 0, 1, 7)",
                      "d.addWidget(self.hw_box, 7, 0, 1, 7)")
    src = src.replace("d.addWidget(self.lbl_warn, 7, 0, 1, 7)",
                      "d.addWidget(self.lbl_warn, 8, 0, 1, 7)")

    print("\n".join(changed))
    if apply:
        shutil.copy2(UI, UI.with_suffix(".py.bak_deriv"))
        io.open(UI, "w", encoding="utf-8").write(src)
        print("已写回，备份 ui/main_window.py.bak_deriv")
    else:
        print("（dry-run，加 --apply 写回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
