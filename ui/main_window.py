"""主窗口：加载 → 识别 → 选模式 → 优化 → 对比 → 另存 3mf。"""

from __future__ import annotations

import html
import json
import os
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIntValidator, QDesktopServices, QFont, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
    QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QToolButton,
    QFrame, QMenu, QPushButton, QRadioButton, QScrollArea, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

def _same_value(a, b) -> bool:
    """比较「表格里的值」与「文件里的值」。

    文件里的值是 JSON 字符串（`["0.4"]` / `[0.4]` / `"70"`），表格里是显示文本。
    先按 JSON 解一次，逐元素比；解不开再按数值/原文比。否则 `[0.4]` 和 `["0.4"]`
    会被当成两回事，核对页上凭空多出一条「不一致」。
    """
    def _norm(v):
        if isinstance(v, (list, tuple)):
            return [_norm(x) for x in v]
        txt = str(v).strip()
        try:
            return _norm(json.loads(txt))
        except Exception:
            pass
        try:
            return float(txt.split()[0])
        except (TypeError, ValueError, IndexError):
            return txt
    na, nb = _norm(a), _norm(b)
    if isinstance(na, list) and isinstance(nb, list):
        return len(na) == len(nb) and all(_norm(x) == _norm(y) for x, y in zip(na, nb))
    if isinstance(na, float) and isinstance(nb, float):
        return abs(na - nb) < 1e-6
    return na == nb


def _same_num(a, b) -> bool:
    """文件里的值可能是 '70'、'70.0'、'["70"]'，表格里是 '70 °C'，按数值/原文都比一次。"""
    def _num(v):
        try:
            return float(str(v).strip().split()[0])
        except (TypeError, ValueError, IndexError):
            return None
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-6
    return str(a).strip() == str(b).strip()


from core import (bambu_profiles, brief, detector, filament_write, hardware, hotend,
                  ironing, machine_sync, model_analysis,
                  modes as modes_reg, preset_diff, report, rules_engine, safety,
                  schema, scope, seam_plan, shape_rules, slice_check, special,
                  studio_env, studio_ui,
                  support_model, thermal, threemf)
from html import escape as html_escape

# 模式顺序与提示统一放在 core/modes.py（新增模式只改那里 + 规则库）
MODE_ORDER = modes_reg.MODE_UI_ORDER
# 规则库预览页用的「形状夹具」：不需要真模型也能预览按件调参会改什么
PREVIEW_SHAPES: tuple[tuple[str, str], ...] = (
    ("none", "（不按形状）"),
    ("small", "小件 / 多件"),
    ("tall", "高瘦件"),
    ("plate", "扁平板件"),
    ("support", "支撑重件"),
)
MODE_HINT = modes_reg.MODE_HINT
COLOR_OK = "#0f766e"
COLOR_WARN = "#b45309"
COLOR_ERR = "#b91c1c"
COLOR_MUTED = "#9ca3af"


def _is_number(v) -> bool:
    try:
        float(str(v).strip().rstrip("%"))
        return True
    except (TypeError, ValueError):
        return False


def _li_from_limit(text: str) -> str:
    """把「短标题：说明」形态的一条限制渲染成列表项，标题加粗。"""
    for sep in ("：", "，", "。"):
        if sep in text:
            head, _, tail = text.partition(sep)
            if 0 < len(head) <= 14:
                return f"<li><b>{html.escape(head)}</b>{html.escape(sep + tail)}</li>"
            break
    return f"<li>{html.escape(text)}</li>"


class _SliceWorker(QThread):
    """后台跑一次 Studio 命令行切片（约 1 分钟），别把界面卡住。"""

    done = Signal(object)

    def __init__(self, project_path: str, write_values: dict, parent=None):
        super().__init__(parent)
        self._path = project_path
        self._values = dict(write_values or {})

    def run(self):
        try:
            res = slice_check.run_slice_check(self._path, self._values)
        except Exception as exc:                      # noqa: BLE001 - 交给界面显示
            res = slice_check.SliceCheck()
            res.warnings.append(f"切片核对异常：{exc}")
        self.done.emit(res)


class MainWindow(QMainWindow):
    def __init__(self, engine: rules_engine.RulesEngine, rules_path: str | Path | None = None):
        super().__init__()
        self.engine = engine
        self.rules = engine.rules
        self.rules_path = Path(rules_path) if rules_path else rules_engine.default_rules_path()

        self.project: threemf.ThreeMfProject | None = None
        self.original_settings: dict[str, str] = {}
        self.det: detector.Detection | None = None
        self.result = None
        self.last_output: Path | None = None
        self._suppress = False          # 防止信号回环
        self.custom_presets: list[bambu_profiles.FilamentPreset] = []
        self.model_profile = None
        self._profile_error: str = ""
        self.last_timecap: dict | None = None
        self.hw: hardware.HardwareInfo | None = None

        self.setWindowTitle("Bambu Smart Tuner — 拓竹 3mf 智能调参")
        self.resize(1440, 960)
        self.setMinimumSize(1180, 720)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 右上角「投喂作者」：点开是收款码弹窗
        self.btn_donate = QToolButton()
        self.btn_donate.setText("☕ 投喂作者")
        self.btn_donate.setToolTip("如果这个小工具帮你省了时间，可以请作者喝杯咖啡。")
        self.btn_donate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_donate.clicked.connect(self._show_donate)
        self.tabs.setCornerWidget(self.btn_donate, Qt.Corner.TopRightCorner)

        self.tabs.addTab(self._build_work_tab(), "调参工作台")
        self.tabs.addTab(self._build_rules_tab(), "规则库预览")
        self.tabs.addTab(self._build_coverage_tab(), "参数覆盖清单")
        self.tabs.addTab(self._build_help_tab(), "使用说明 / 已知限制")

        self.statusBar().showMessage("就绪")
        self._refresh_rules_controls()
        self._render_rules_preview()
        self._render_coverage()
        self._log("Bambu Smart Tuner 已启动。", "ok")
        try:
            shown = self.rules_path.relative_to(Path(os.getcwd()))
        except Exception:
            shown = self.rules_path.name
        self._log(f"规则库：{shown}（改这个文件后到「规则库预览」页点「重新加载 JSON」）")
        self._log("第 1 步：点「加载 3mf」，选 Bambu Studio 保存的工程文件（.3mf / .bambu）。")

    # ================================================================ UI 搭建

    def _build_work_tab(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # 上下可拖：上半是「工程 / 识别 / 模式」，下半是「对比表 + 日志」。
        # 以前全塞在一个纵向布局里，表格只能分到很矮的一条。
        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        self.vsplit.setChildrenCollapsible(False)
        top = QWidget()
        root_top = QVBoxLayout(top)
        root_top.setContentsMargins(0, 0, 0, 0)
        root_top.setSpacing(8)
        bottom = QWidget()
        root_bot = QVBoxLayout(bottom)
        root_bot.setContentsMargins(0, 0, 0, 0)
        root_bot.setSpacing(6)

        # ---- ① 文件加载区
        box_file = QGroupBox("① 工程文件")
        g = QGridLayout(box_file)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(6)

        self.ed_src = QLineEdit()
        self.ed_src.setPlaceholderText("选择 Bambu Studio 保存的工程文件（.3mf / .bambu），也可直接把文件拖进窗口")
        btn_load = QPushButton("加载 3mf…")
        btn_reload = QPushButton("重新读取")
        btn_load.clicked.connect(self.on_load_clicked)
        btn_reload.clicked.connect(self.on_reload_clicked)

        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("留空则自动命名为 原文件名_optimized_时间戳.3mf，保存到原目录")
        btn_out = QPushButton("另存为…")
        btn_out.clicked.connect(self.on_pick_output)

        g.addWidget(QLabel("工程文件"), 0, 0)
        g.addWidget(self.ed_src, 0, 1)
        g.addWidget(btn_load, 0, 2)
        g.addWidget(btn_reload, 0, 3)
        g.addWidget(QLabel("输出文件"), 1, 0)
        g.addWidget(self.ed_out, 1, 1, 1, 3)

        # 只改工艺参数还是顺带改工艺档名：默认只改参数（用户要求「只更改工艺板块参数」）
        self.chk_custom_profile = QCheckBox(
            "把工艺档标为自定义（仅当 Studio 打开后没反映改动时才勾）")
        self.chk_custom_profile.setToolTip(
            "勾上后会把 3mf 里的 print_settings_id 改成「原名 - Smart Tuner」，"
            "Studio 就不会去盘上找同名系统预设、必定采用文件里的参数。\n"
            "只改工程文件内部这一行元数据，不写 Bambu Studio 的任何预设。")
        self.chk_custom_profile.setChecked(False)
        g.addWidget(self.chk_custom_profile, 3, 0, 1, 4)

        self.lbl_file_state = QLabel("尚未加载工程")
        self.lbl_file_state.setObjectName("muted")
        self.lbl_file_state.setWordWrap(True)
        g.addWidget(self.lbl_file_state, 2, 0, 1, 4)
        g.setColumnStretch(1, 1)
        root_top.addWidget(box_file)

        # ---- ② 识别面板
        box_det = QGroupBox("② 识别结果（自动识别，可手动修正）")
        d = QGridLayout(box_det)
        d.setHorizontalSpacing(8)
        d.setVerticalSpacing(6)

        self.cmb_printer = QComboBox()
        self.cmb_filament = QComboBox()
        self.cmb_nozzle = QComboBox()
        for key, label in self.engine.printer_choices():
            self.cmb_printer.addItem(label, key)
        for key, label in self.engine.filament_choices():
            self.cmb_filament.addItem(label, key)
        for n in detector.SUPPORTED_NOZZLES:
            self.cmb_nozzle.addItem(f"{n:g} mm", float(n))
        i = self.cmb_nozzle.findData(0.4)
        self.cmb_nozzle.setCurrentIndex(i if i >= 0 else 0)

        for cmb in (self.cmb_printer, self.cmb_filament, self.cmb_nozzle):
            cmb.setMinimumWidth(190)
            cmb.currentIndexChanged.connect(self._on_override_changed)

        # 换机型 → 这台机器支持的板型可能不一样，重建下拉（别让人选到装不上的板）
        self.cmb_printer.currentIndexChanged.connect(lambda *_: self._refill_bed_options())

        d.addWidget(QLabel("打印机型号"), 0, 0)
        d.addWidget(self.cmb_printer, 0, 1)
        d.addWidget(QLabel("耗材类型"), 0, 2)
        d.addWidget(self.cmb_filament, 0, 3)
        d.addWidget(QLabel("喷嘴直径"), 0, 4)
        d.addWidget(self.cmb_nozzle, 0, 5)
        # 热端流量类型（标准 / 高流量 / E3D 高流量）：工程里能读出来，也可以手改
        self.cmb_hotend = QComboBox()
        self.cmb_hotend.setMinimumWidth(150)
        # 自动识别回填也会选中「标准流量」——记住用户是否真的动过，
        # 否则引擎会把「自动识别」当成「用户手选」，日志里会误写成「依据 用户选择」
        self._hotend_touched = False
        self.cmb_hotend.activated.connect(lambda *_: setattr(self, "_hotend_touched", True))
        for key, label in hotend.options(self.engine.rules):
            self.cmb_hotend.addItem(label, key)
        self.cmb_hotend.currentIndexChanged.connect(self._on_override_changed)
        d.addWidget(QLabel("热端流量"), 0, 6)
        d.addWidget(self.cmb_hotend, 0, 7)

        # 自定义耗材（常驻可选，没同步过时为禁用态）
        self.cmb_custom = QComboBox()
        self.cmb_custom.setMinimumWidth(240)
        self.cmb_custom.addItem("（不使用自定义耗材）", None)
        self.cmb_custom.setEnabled(False)
        self.cmb_custom.currentIndexChanged.connect(self._on_override_changed)
        self.btn_sync_fil = QPushButton("同步 Bambu 自定义耗材")
        self.btn_sync_fil.clicked.connect(self.on_sync_filaments)
        d.addWidget(QLabel("自定义耗材"), 1, 0)
        d.addWidget(self.cmb_custom, 1, 1, 1, 3)
        d.addWidget(self.btn_sync_fil, 1, 4, 1, 2)

        # 模型形状识别（按件调参的开关）
        self.lbl_shape = QLabel("模型形状：—（加载工程后自动分析）")
        self.lbl_shape.setObjectName("muted")
        self.lbl_shape.setWordWrap(True)
        d.addWidget(self.lbl_shape, 2, 0, 1, 7)

        self.chk_shape = QCheckBox("按模型形状自动微调（高瘦降加速度 / 平板加裙边 / 支撑重加大间隙）")
        self.chk_shape.setChecked(True)
        self.chk_shape.stateChanged.connect(lambda *_: self._reoptimize())
        self.chk_shape.setEnabled(False)
        d.addWidget(self.chk_shape, 3, 0, 1, 7)

        # ---- 热床 / 风速 / 支撑好拆 / 接缝 / 方案预设（v1.2）
        # 用户反馈：天冷翘边要按「耗材 × 板子 × 室温」给热床温度和风速；
        # 支撑要按好拆程度调 Z 面；圆柱接缝要光滑；并且要能存几套自己的方案。
        self.cmb_bed = QComboBox()
        # 第一项是「跟随工程」：不指定就按 3mf 里 curr_bed_type 记的板子算，
        # 免得默认选中 Supertack 把 Textured PEI 工程的板温和板型一起写错。
        # 只列 Bambu Studio 切片器里真实有的板型（五个），再按所选机型的
        # not_support_bed_type 滤掉这台机器装不了的（H2C/H3C/P3C 不支持低温板等）。
        self._fill_bed_options()
        self.cmb_bed.setMinimumWidth(170)

        # 室温：直接敲数字（空着 = 不指定）。用 QLineEdit 是因为 QSpinBox 的
        # 「特殊值 = 不指定」和「0°C 也是有效室温」会打架，而且那个值很难改回来。
        self.ed_room = QLineEdit()
        self.ed_room.setPlaceholderText("室温 °C（可不填）")
        self.ed_room.setValidator(QIntValidator(-10, 50, self))
        self.ed_room.setMinimumWidth(90)
        self.ed_room.setToolTip(
            "房间/环境温度。填了就按「天冷加温、天热减温」修正热床，首层跟着热一点；\n"
            "低于 18°C 时风扇也会自动降一档防翘边。空着 = 不动这两项。")

        # 风扇强弱：默认「自动」= 按耗材基线 + 室温自己定；想插手就选一个百分比。
        self.cmb_fan = QComboBox()
        self.cmb_fan.addItem("自动（按耗材/板子/室温）", None)
        self.cmb_fan.addItem("比标定低 20%（最保守）", -20)
        self.cmb_fan.addItem("比标定低 10%", -10)
        self.cmb_fan.addItem("按标定值（不加不减）", 0)
        self.cmb_fan.addItem("比标定高 10%", 10)
        self.cmb_fan.addItem("比标定高 20%（悬垂更挺）", 20)
        self.cmb_fan.setMinimumWidth(210)
        self.cmb_fan.setToolTip(
            "自动＝按耗材基线和室温算（冷天自动降一档防翘边）；\n"
            "选具体百分比＝照你给的来，不再叠加自动修正。首层关风不受影响。")

        self.cmb_ease = QComboBox()
        self.cmb_ease.addItem("标准", "standard")
        self.cmb_ease.addItem("好拆（推荐）", "easy")
        self.cmb_ease.addItem("极好拆（支撑会明显变松）", "max")
        self.cmb_ease.setMinimumWidth(150)
        self.cmb_ease.setToolTip(
            "支撑好拆程度：只改支撑顶面 Z 间隙、接触面层数与接触线距，\n"
            "让支撑用手一掰就掉；不会改支撑落在哪里（那要在 Studio 里看）。")

        d.addWidget(QLabel("打印板"), 4, 0)
        d.addWidget(self.cmb_bed, 4, 1)
        d.addWidget(QLabel("室温"), 4, 2)
        d.addWidget(self.ed_room, 4, 3)
        d.addWidget(QLabel("风扇强弱"), 4, 4)
        d.addWidget(self.cmb_fan, 4, 5)
        d.addWidget(QLabel("支撑好拆"), 4, 6)
        d.addWidget(self.cmb_ease, 4, 7)

        self.cmb_bed.currentIndexChanged.connect(lambda *_: self._reoptimize())
        self.cmb_ease.currentIndexChanged.connect(lambda *_: self._reoptimize())
        # 室温每敲一个字就重算会卡，停顿 0.5 秒再算；回车/离开输入框立刻算
        self._room_timer = QTimer(self)
        self._room_timer.setSingleShot(True)
        self._room_timer.setInterval(500)
        self._room_timer.timeout.connect(lambda: self._reoptimize())
        self.ed_room.textChanged.connect(lambda *_: self._room_timer.start())
        self.ed_room.editingFinished.connect(lambda: self._reoptimize())
        self.cmb_fan.currentIndexChanged.connect(lambda *_: self._reoptimize())

        # 圆柱 / 圆管的接缝：斜接缝（scarf）把竖线斜过去
        self.chk_seam = QCheckBox("圆柱/圆管接缝做斜接（外壁能看出来一条竖线的件）")
        self.chk_seam.setChecked(True)
        self.chk_seam.setToolTip(
            "圆件没有棱角能藏接缝，只能靠斜接缝把竖线斜切过去。\n"
            "只对判定为圆柱/细高的件生效，其它件不受影响。")
        self.chk_seam.stateChanged.connect(lambda *_: self._reoptimize())
        d.addWidget(self.chk_seam, 5, 0, 1, 8)

        # ---- 耗材页 / 熨烫 / 特殊模式（全都由用户自己定，软件不替你决定）
        self.cmb_fil_mode = QComboBox()
        for label, key in filament_write.mode_options():
            self.cmb_fil_mode.addItem(label, key)
        self.cmb_fil_mode.setCurrentIndex(max(0, self.cmb_fil_mode.findData("file")))
        self.cmb_fil_mode.setMinimumWidth(240)
        self.cmb_fil_mode.setToolTip("不改耗材页 = 热床温度、风速、喷头温度、压力提前这些一个都不写，只调工艺。" + chr(10) + "写进当前耗材 = 在你自己那份耗材上改（默认）。" + chr(10) + "新建一份耗材 = 参数照写，并把耗材另存为「原名 + 优化」，原预设不动。")

        self.cmb_iron = QComboBox()
        for label, key in ironing.type_options():
            self.cmb_iron.addItem(label, key)
        self.cmb_iron.setMinimumWidth(200)
        self.cmb_iron.setToolTip("熨烫＝拿热喷嘴在打好的平面上再刮一遍，把层纹和缝隙抹平。")
        self.chk_iron_auto = QCheckBox("熨烫参数自动优化")
        self.chk_iron_auto.setChecked(True)
        self.chk_iron_auto.setToolTip("勾上：流量、间距、速度、图案按耗材、层高、喷嘴、优化模式算。" + chr(10) + "去掉：只改熨烫类型，这四个参数保留你原来的值。")
        self.btn_special = QPushButton("特殊模式…")
        self.btn_special.setToolTip("「其他」页里的开关（逐件打印、螺旋花瓶、圆弧拟合、磨砂皮肤等）。" + chr(10) + "点开自己选；不选就等于一个都不改。")
        self.lbl_special = QLabel("特殊模式：全部跟随工程")
        self.lbl_special.setObjectName("muted")

        d.addWidget(QLabel("耗材页"), 6, 0)
        d.addWidget(self.cmb_fil_mode, 6, 1)
        d.addWidget(QLabel("熨烫"), 6, 2)
        d.addWidget(self.cmb_iron, 6, 3)
        d.addWidget(self.chk_iron_auto, 6, 4)
        d.addWidget(self.btn_special, 6, 5)
        d.addWidget(self.lbl_special, 6, 6, 1, 2)

        self._special_modes: dict[str, str] = {}
        self.cmb_fil_mode.currentIndexChanged.connect(lambda *_: self._reoptimize())
        self.cmb_iron.currentIndexChanged.connect(lambda *_: self._reoptimize())
        self.chk_iron_auto.stateChanged.connect(lambda *_: self._reoptimize())
        self.btn_special.clicked.connect(self.on_pick_special)

        # 方案功能已移除：选模式 + 几个下拉本身就是「方案」，套两层反而更绕。

        # 新增那两行控件的一句话解释（用户反馈：不要一屏参数值，先给「这是什么」）
        self.lbl_newhint = QLabel(
            "打印板 × 室温 → 定热床温度与首层温度（天冷翘边就治这两项）；"
            "风扇强弱 = 在算好的风速上整体加减；支撑好拆只改拆的难易，不改支撑落在哪；"
            "耗材页 = 动不动你的耗材；熨烫 = 顶面要不要再刮平；特殊模式 = 你自己勾的 Studio 开关。")
        self.lbl_newhint.setObjectName("muted")
        self.lbl_newhint.setWordWrap(True)
        d.addWidget(self.lbl_newhint, 7, 0, 1, 8)

        self.lbl_raw = QLabel("原始值：—")
        self.lbl_raw.setObjectName("muted")
        self.lbl_raw.setWordWrap(True)
        d.addWidget(self.lbl_raw, 8, 0, 1, 8)

        # 逐件调参明细：每个对象判成什么形状原型、依据是什么、会被怎么调
        self.obj_box = QGroupBox("逐件调参明细（按对象判形状原型，按最保守者合并成全局值）")
        ov = QVBoxLayout(self.obj_box)
        ov.setContentsMargins(8, 4, 8, 8)
        self.obj_tree = QTreeWidget()
        self.obj_tree.setColumnCount(5)
        self.obj_tree.setHeaderLabels(["对象", "尺寸 / 体积", "形状原型", "判定依据", "会怎么调"])
        self.obj_tree.setAlternatingRowColors(True)
        self.obj_tree.setUniformRowHeights(True)
        self.obj_tree.setRootIsDecorated(False)
        oh = self.obj_tree.header()
        oh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        oh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        oh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        oh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        oh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.obj_tree.setMinimumHeight(96)
        self.obj_tree.setMaximumHeight(170)
        ov.addWidget(self.obj_tree)
        # obj_box 放到下方「逐件明细」页签（见 _build_work_tab 底部）

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
        self.deriv_tree.setMinimumHeight(96)
        self.deriv_tree.setMaximumHeight(230)
        dv.addWidget(self.deriv_tree)
        # deriv_box 放到下方「推导复核」页签

        # 真机同步清单（喷嘴 / 流量 / 机器上限 / 板面，全部来自工程，只读）
        self.hw_box = QGroupBox("真机同步（来自工程文件，只读不写，用于约束工艺参数）")
        hv = QVBoxLayout(self.hw_box)
        hv.setContentsMargins(8, 4, 8, 8)
        self.lbl_hw = QLabel("尚未加载工程")
        self.lbl_hw.setObjectName("muted")
        self.lbl_hw.setWordWrap(True)
        hv.addWidget(self.lbl_hw)
        # hw_box 放到下方「真机同步」页签

        self.lbl_warn = QLabel()
        self.lbl_warn.setObjectName("warn")
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setVisible(False)
        d.addWidget(self.lbl_warn, 8, 0, 1, 8)
        d.setColumnStretch(1, 1)
        d.setColumnStretch(3, 1)
        root_top.addWidget(box_det)

        # ---- ③ 模式选择
        box_mode = QGroupBox("③ 优化模式")
        m = QVBoxLayout(box_mode)
        row1 = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for i, key in enumerate(MODE_ORDER):
            rb = QRadioButton(self.engine.mode(key).get("label", key))
            rb.setToolTip(MODE_HINT.get(key, ""))
            self.mode_group.addButton(rb, i)
            self.radios[key] = rb
            row1.addWidget(rb)
        row1.addStretch(1)
        self.chk_timecap = QCheckBox("按时长预算自动回调")
        self.chk_timecap.setToolTip(
            "勾选后按规则库每个档位自带的时长预算执行回调：均衡 40%、草稿 10%、"
            "强度 200%、质量 170%，精细两档不限。超出预算时按「代价最小」的顺序"
            "自动回退（先降填充密度 → 顶底壳层 → 墙圈数 → 提速度 → 提加速度），"
            "强度档不动墙圈数、草稿档不动层高以上的墙数。"
            "不勾选 = 完全不做时长回调，参数全按规则给足。")
        self.chk_timecap.setChecked(True)   # 默认按时长预算回调，否则均衡档会算出 +78% 的时长
        self.chk_timecap.stateChanged.connect(lambda *_: self._reoptimize())
        row1.addWidget(self.chk_timecap)

        # 支撑开关：自动只决定「开不开 + 用多少料」，落点必须人看过
        lbl_sup = QLabel("支撑")
        row1.addWidget(lbl_sup)
        self.cmb_support = QComboBox()
        self.cmb_support.addItem("自动（按模型判断）", "auto")
        self.cmb_support.addItem("强制开启", "on")
        self.cmb_support.addItem("强制关闭", "off")
        self.cmb_support.setToolTip(
            "自动：模型有悬垂就开，并按悬垂面积算密度/间隙/形态；\n"
            "       开启时会在日志里提醒你去 Studio 核对支撑落点。\n"
            "强制开启：即使判定为不需要支撑也开（适合你手动刷过支撑拦截器的件）。\n"
            "强制关闭：任何情况都不写支撑参数（悬垂塌陷风险自负）。\n"
            "注意：支撑**落在哪里**只能你在 Bambu Studio 里判断，本程序只调参数。")
        self.cmb_support.setFixedWidth(150)
        self.cmb_support.currentIndexChanged.connect(lambda *_: self._reoptimize())
        row1.addWidget(self.cmb_support)
        m.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_mode_hint = QLabel(self._mode_hint_text("balanced"))
        self.lbl_mode_hint.setObjectName("muted")
        self.lbl_mode_hint.setWordWrap(True)
        row2.addWidget(self.lbl_mode_hint, 1)
        m.addLayout(row2)

        self.radios["balanced"].setChecked(True)
        self.mode_group.idToggled.connect(self._on_mode_toggled)

        root_top.addWidget(box_mode)

        # 结论卡：用户最想知道「这样调整后的结果」，不看参数值。
        # 固定在下方页签区最上面（不随 ①②③ 一起滚走），一眼就能看到。
        self.brief_box = QGroupBox("结论：这样调整之后会变成什么样")
        bl = QVBoxLayout(self.brief_box)
        bl.setContentsMargins(8, 4, 8, 6)
        self.lbl_brief = QLabel("优化后会显示成一段人话结论：整体是不是更快/更结实、表面与附着变化、热床与风速、支撑好不好拆。")
        self.lbl_brief.setObjectName("muted")
        self.lbl_brief.setWordWrap(True)
        self.lbl_brief.setTextFormat(Qt.TextFormat.RichText)
        # 固定高度而不是「最多这么高」：否则一换机型、结论多两行，
        # 底下的 QTabWidget 会把这条挤到只剩一行，用户以为内容丢了。
        self.lbl_brief.setFixedHeight(196)
        bl.addWidget(self.lbl_brief)
        self.brief_box.setFixedHeight(226)

        # ---- ⑥ 操作按钮
        bar = QHBoxLayout()
        self.btn_run = QPushButton("开始优化")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.on_optimize_clicked)
        self.btn_report = QPushButton("导出报告")
        self.btn_report.clicked.connect(self.on_export_report)
        self.btn_save = QPushButton("保存为 3mf")
        self.btn_save.clicked.connect(self.on_save_3mf)
        self.btn_open_dir = QPushButton("打开输出目录")
        self.btn_open_dir.clicked.connect(self.on_open_output_dir)
        for b in (self.btn_report, self.btn_save, self.btn_open_dir):
            b.setEnabled(False)
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_save)
        bar.addWidget(self.btn_report)
        bar.addWidget(self.btn_open_dir)
        bar.addStretch(1)
        self.lbl_summary = QLabel("改动 — 项 · 预计时长 —")
        self.lbl_summary.setObjectName("pill")
        bar.addWidget(self.lbl_summary)
        root_top.addLayout(bar)

        # ---- ④ 对比表 + ⑤ 日志
        self.split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)

        filt = QHBoxLayout()
        self.chk_changed = QCheckBox("只看改动项")
        self.chk_changed.setChecked(True)
        self.chk_changed.stateChanged.connect(lambda *_: self._fill_table())
        self.cmb_scope = QComboBox()
        self.cmb_scope.addItem("全部归属", "")
        self.cmb_scope.addItem("只显示：切片工艺（会写入）", scope.PROCESS)
        self.cmb_scope.addItem("只显示：耗材页 / 机器页（只读）", "readonly")
        self.cmb_scope.currentIndexChanged.connect(lambda *_: self._fill_table())
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("搜索参数名 / 键名…")
        self.ed_search.textChanged.connect(lambda *_: self._fill_table())
        self.ed_search.setClearButtonEnabled(True)
        filt.addWidget(self.chk_changed)
        filt.addWidget(self.cmb_scope)
        filt.addWidget(self.ed_search, 1)
        lv.addLayout(filt)

        self.table = QTreeWidget()
        self.table.setColumnCount(7)
        self.table.setHeaderLabels(
            ["参数", "Studio 里在哪", "归属", "原始值", "优化后", "写入", "调整依据"])
        self.table.setAlternatingRowColors(True)
        self.table.setUniformRowHeights(True)
        self.table.setRootIsDecorated(True)
        self.table.setMinimumHeight(300)
        self.table.setColumnWidth(0, 208)
        self.table.setColumnWidth(1, 168)
        self.table.setColumnWidth(2, 76)
        self.table.setColumnWidth(3, 96)
        self.table.setColumnWidth(4, 96)
        self.table.setColumnWidth(5, 44)
        self.table.setAnimated(False)
        self.table.setIndentation(12)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_menu)
        hdr = self.table.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(self._on_table_double_click)
        lv.addWidget(self.table, 1)
        # 参数对比 / 逐件明细 / 推导复核 / 真机同步 收进页签：
        # 默认只给「参数对比」，其余三块留给想复核的人，界面不至于一屏堆满。
        self.detail_tabs = QTabWidget()
        self.detail_tabs.setDocumentMode(True)
        self.detail_tabs.addTab(left, "参数对比")
        self.detail_tabs.addTab(self.obj_box, "逐件明细")
        self.detail_tabs.addTab(self.deriv_box, "推导复核")
        self.detail_tabs.addTab(self.hw_box, "真机同步")
        # 写入核对：保存后把「表格里的值 → 新 3mf 里实际存的值」逐键比对，
        # 一眼看出哪些真进了文件、哪些没有（用户要「验证是否都在切片软件应用了」）。
        self.verify_page = QWidget()
        vv = QVBoxLayout(self.verify_page)
        vv.setContentsMargins(8, 8, 8, 8)
        vv.setSpacing(6)
        self.lbl_verify = QLabel("还没有保存。点「保存为 3mf」后，这里会逐键核对"
                                 "「表格里的值」和「文件里实际存的值」。")
        self.lbl_verify.setObjectName("muted")
        self.lbl_verify.setWordWrap(True)
        vv.addWidget(self.lbl_verify)

        srow = QHBoxLayout()
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(6)
        self.btn_slice = QPushButton("用本机 Studio 切片核对")
        self.btn_slice.setToolTip("调 bambu-studio.exe 无界面切一片，从 gcode 里读回实际生效的值（约 1 分钟）")
        self.btn_slice.clicked.connect(self.on_slice_check)
        self.lbl_slice = QLabel("切一片，验证参数真的进了 gcode（需要本机装 Bambu Studio）")
        self.lbl_slice.setObjectName("muted")
        self.lbl_slice.setWordWrap(True)
        srow.addWidget(self.btn_slice)
        srow.addWidget(self.lbl_slice, 1)
        vv.addLayout(srow)

        self.verify_tree = QTreeWidget()
        self.verify_tree.setRootIsDecorated(False)
        self.verify_tree.setAlternatingRowColors(True)
        self.verify_tree.setColumnCount(4)
        self.verify_tree.setHeaderLabels(["参数", "表格里的值", "文件里的值", "结果"])
        vh = self.verify_tree.header()
        vh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        vh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        vh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        vv.addWidget(self.verify_tree, 1)
        self.detail_tabs.addTab(self.verify_page, "写入核对")
        self.split.addWidget(self.detail_tabs)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        rv.addWidget(QLabel("日志 / 优化说明"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        rv.addWidget(self.log_view, 1)
        self.split.addWidget(right)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        self.split.setSizes([880, 460])
        root_bot.addWidget(self.brief_box)
        root_bot.addWidget(self.split, 1)
        self.top_scroll = QScrollArea()
        self.top_scroll.setWidgetResizable(True)
        self.top_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.top_scroll.setWidget(top)
        self.top_scroll.setMinimumHeight(220)
        self.vsplit.addWidget(self.top_scroll)
        self.vsplit.addWidget(bottom)
        self.vsplit.setStretchFactor(0, 0)
        self.vsplit.setStretchFactor(1, 1)
        self.vsplit.setSizes([430, 720])
        root.addWidget(self.vsplit, 1)
        return w

    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        bar = QHBoxLayout()
        self.rp_printer = QComboBox()
        self.rp_filament = QComboBox()
        self.rp_nozzle = QComboBox()
        self.rp_mode = QComboBox()
        self.rp_custom = QComboBox()
        self.rp_shape = QComboBox()
        for key, label in self.engine.printer_choices():
            self.rp_printer.addItem(label, key)
        for key, label in self.engine.filament_choices():
            self.rp_filament.addItem(label, key)
        for n in detector.SUPPORTED_NOZZLES:
            self.rp_nozzle.addItem(f"{n:g} mm", float(n))
        for key, label in self.engine.mode_choices():
            self.rp_mode.addItem(label, key)
        self.rp_custom.addItem("（无自定义耗材）", None)
        self.rp_custom.setEnabled(False)
        for key, label in PREVIEW_SHAPES:
            self.rp_shape.addItem(label, key)
        i = self.rp_nozzle.findData(0.4)
        self.rp_nozzle.setCurrentIndex(i if i >= 0 else 0)
        i = self.rp_mode.findData("balanced")
        self.rp_mode.setCurrentIndex(i if i >= 0 else 0)
        for c in (self.rp_printer, self.rp_filament, self.rp_nozzle, self.rp_mode,
                  self.rp_custom, self.rp_shape):
            c.currentIndexChanged.connect(lambda *_: self._render_rules_preview())

        btn_reload_rules = QPushButton("重新加载 JSON")
        btn_reload_rules.clicked.connect(self.on_reload_rules)
        btn_open_rules = QPushButton("打开 JSON 所在目录")
        btn_open_rules.clicked.connect(self._open_rules_dir)

        bar.addWidget(QLabel("机型"))
        bar.addWidget(self.rp_printer)
        bar.addWidget(QLabel("耗材"))
        bar.addWidget(self.rp_filament)
        bar.addWidget(QLabel("喷嘴"))
        bar.addWidget(self.rp_nozzle)
        bar.addWidget(QLabel("模式"))
        bar.addWidget(self.rp_mode)
        bar.addWidget(QLabel("自定义耗材"))
        bar.addWidget(self.rp_custom)
        bar.addWidget(QLabel("形状"))
        bar.addWidget(self.rp_shape)
        bar.addStretch(1)
        bar.addWidget(btn_reload_rules)
        bar.addWidget(btn_open_rules)
        v.addLayout(bar)

        tip = QLabel("这里是该「机型 + 耗材 + 喷嘴 + 模式（+ 自定义耗材 / 形状）」组合最终会写出的基准参数，"
                     f"全部来自 {self.rules_path.name}；改完 JSON 点「重新加载 JSON」即可生效，不需要重启程序。"
                     "形状一栏用合成夹具模拟各类模型，用来预览「按件调参」会改哪些值。")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        v.addWidget(tip)

        self.rp_table = QTableWidget(0, 5)
        self.rp_table.setHorizontalHeaderLabels(["分组", "参数", "基准值", "合法区间", "依据"])
        self.rp_table.verticalHeader().setVisible(False)
        self.rp_table.setAlternatingRowColors(True)
        self.rp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        h = self.rp_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.rp_table, 1)
        return w

    def _build_coverage_tab(self) -> QWidget:
        """参数覆盖清单：说明哪些参数能调、哪些有意不改、为什么。"""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        head = QHBoxLayout()
        self.lbl_cov_top = QLabel()
        self.lbl_cov_top.setObjectName("pill")
        btn_audit = QPushButton("扫描当前工程统计覆盖")
        btn_audit.clicked.connect(self.on_audit_current)
        head.addWidget(self.lbl_cov_top)
        head.addStretch(1)
        head.addWidget(btn_audit)
        v.addLayout(head)

        split = QSplitter(Qt.Orientation.Horizontal)

        left_box = QGroupBox("可调参数（本程序会改 = 切片工艺页）")
        lv = QVBoxLayout(left_box)
        self.cov_tree = QTreeWidget()
        self.cov_tree.setColumnCount(5)
        self.cov_tree.setHeaderLabels(["归属", "分组", "参数", "键名", "工程是否存储"])
        self.cov_tree.setAlternatingRowColors(True)
        self.cov_tree.setUniformRowHeights(True)
        self.cov_tree.setIndentation(12)
        hc = self.cov_tree.header()
        hc.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hc.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hc.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hc.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hc.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.cov_tree.setColumnWidth(2, 190)
        lv.addWidget(self.cov_tree)
        split.addWidget(left_box)

        right_box = QGroupBox("有意不改的参数（附原因）")
        rv = QVBoxLayout(right_box)
        self.cov_note = QTextBrowser()
        self.cov_note.setOpenExternalLinks(False)
        rv.addWidget(self.cov_note)
        split.addWidget(right_box)

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([720, 540])
        v.addWidget(split, 1)
        return w

    def _render_coverage(self, project_keys: set[str] | None = None) -> None:
        from core import coverage
        policy = scope.ScopePolicy.from_rules(self.engine.rules)
        n_process = sum(1 for k in schema.PARAMS if policy.allows(k))
        self.lbl_cov_top.setText(
            f"共 {len(schema.PARAMS)} 个参数 · {len(schema.GROUPS)} 个分组 · "
            f"本程序只写切片工艺页 {n_process} 项")
        self.cov_tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        per_group: dict[str, int] = {}
        for key, s in schema.PARAMS.items():
            per_group[s.group] = per_group.get(s.group, 0) + 1
            parent = groups.get(s.group)
            if parent is None:
                parent = QTreeWidgetItem([s.group_label, "", "", "", ""])
                f = parent.font(0)
                f.setBold(True)
                parent.setFont(0, f)
                self.cov_tree.addTopLevelItem(parent)
                groups[s.group] = parent
            if project_keys is None:
                stored = "（未加载工程）"
            else:
                stored = "是" if key in project_keys else "否（只给推荐值）"
            sc = scope.scope_of(key)
            item = QTreeWidgetItem([scope.SCOPE_LABEL.get(sc, sc), s.group_label, s.label, key, stored])
            item.setToolTip(3, key)
            if sc != scope.PROCESS:
                item.setForeground(0, QColor(COLOR_WARN))
                item.setToolTip(0, scope.SCOPE_NOTE.get(sc, ""))
            if project_keys is not None and key not in project_keys:
                item.setForeground(4, QColor(COLOR_WARN))
            parent.addChild(item)
        for g, item in groups.items():
            item.setText(2, f"{per_group[g]} 项")
            item.setExpanded(g in ("quality", "speed"))
        self.cov_tree.resizeColumnToContents(0)
        self.cov_tree.resizeColumnToContents(1)

        html = ["<style>body{font-size:13px;color:#1f2937}"
                "h3{font-size:13px;margin:12px 0 4px}"
                "p{margin:4px 0 8px;color:#4b5563;line-height:1.6}"
                "code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:12px}"
                "ul{margin:2px 0 8px 18px;padding:0}"
                "li{margin:2px 0;color:#6b7280;font-size:12px}</style>"]
        html.append("<p><b>写入范围：只改切片工艺页</b></p>")
        for label, cnt, note in policy.summary():
            html.append(f"<h3>{html_escape(label)}（{cnt} 项）</h3>")
            html.append(f"<p>{html_escape(note)}</p>")
        html.append("<p><b>第二类：有意不改，附原因</b></p>")
        for name, why, keys, note in coverage.EXCLUDED_CATEGORIES:
            html.append(f"<h3>{html_escape(name)}（{len(keys)} 类）</h3>")
            html.append(f"<p><b>原因</b>：{html_escape(why)}</p>")
            html.append(f"<p><b>做法</b>：{html_escape(note)}</p>")
            sample = "、".join(html_escape(k) for k in keys[:14])
            more = "…" if len(keys) > 14 else ""
            html.append(f"<ul><li><code>{sample}</code>{more}</li></ul>")
        html.append("<p><b>第三类：表内已声明、默认不动，由你按需手动开</b>"
                    "（程序会配好配套参数，但开关留给你决定）</p>")
        for name, what, when in coverage.ON_DEMAND:
            html.append(f"<h3>{html_escape(name)}</h3>")
            html.append(f"<p><b>作用</b>：{html_escape(what)}</p>")
            html.append(f"<p><b>何时开</b>：{html_escape(when)}</p>")
        self.cov_note.setHtml("".join(html))

    def on_audit_current(self) -> None:
        if not self.project:
            QMessageBox.information(self, "先加载工程", "加载一个 3mf 后再统计覆盖情况。")
            return
        keys = set(self.project.settings)
        self._render_coverage(keys)
        covered = len(set(schema.PARAMS) & keys)
        # 工程里有、但我们声明为「不改」的
        from core import coverage
        excluded_prefix = tuple(p for _, _, keys_, _ in coverage.EXCLUDED_CATEGORIES for p in keys_)
        not_ours = [k for k in keys if k not in schema.PARAMS]
        self.lbl_cov_top.setText(
            f"本工程 {len(keys)} 个键：可调参数命中 {covered} 个，"
            f"其余 {len(not_ours)} 个属于「有意不改」类别")
        self._log(f"覆盖统计：工程 {len(keys)} 键，命中可调参数 {covered} 个，"
                  f"其余 {len(not_ours)} 个为硬件/温度/元数据类。", "ok")

    def _build_help_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        steps = "".join(f"<li>{html.escape(s)}</li>" for s in (
            "Bambu Studio 里摆好模型、选好打印机/耗材/喷嘴。",
            "文件 → 保存工程（或 另存为 .3mf），得到 .3mf 工程文件。",
            "本程序点「加载 3mf」，核对机型 / 耗材 / 喷嘴。",
            "选优化模式 → 看对比表与时长预估 → 点「保存为 3mf」。",
            "回到 Bambu Studio 打开新文件，直接切片打印。",
        ))
        limits = "".join(_li_from_limit(t) for t in report.LIMITATIONS)
        browser.setHtml(f"""
        <style>
          body {{ font-size: 13px; color: #1f2937; }}
          h2 {{ font-size: 15px; margin: 14px 0 6px; }}
          code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; }}
          li {{ margin: 4px 0; line-height: 1.6; }}
        </style>
        <h2>使用流程</h2>
        <ol>{steps}</ol>
        <h2>已知限制</h2>
        <ul>{limits}</ul>
        <h2>自定义调参策略</h2>
        <p>规则全部在程序目录下的 <code>rules/{html.escape(self.rules_path.name)}</code>
        （在哪台机器上运行，这个路径就在那台机器上；想直接定位，去「规则库预览」页点
        「打开 JSON 所在目录」）：
        机型硬件上限在 <code>printers</code>，耗材特性在 <code>filaments</code>，
        模式档的加减乘改在 <code>modes</code>，跨维度特例在 <code>interactions</code>，
        板温与风扇在 <code>thermal</code>，几何阈值在 <code>geometry_rules</code>。
        改完回到「规则库预览」页点「重新加载 JSON」，不用重启。</p>
        """)
        v.addWidget(browser, 1)
        return w

    # ---------------------------------------------------------------- 投喂作者

    def _asset_path(self, name: str) -> Path | None:
        """在「EXE 同目录 → _MEIPASS → 源码目录」里找一张图。"""
        cands = []
        try:
            import sys
            base = Path(sys.executable).resolve().parent
            cands.append(base / "assets" / name)
            mp = getattr(sys, "_MEIPASS", None)
            if mp:
                cands.append(Path(mp) / "assets" / name)
        except Exception:
            pass
        cands.append(Path(__file__).resolve().parent.parent / "assets" / name)
        for c in cands:
            if c.exists():
                return c
        return None

    def _show_donate(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("投喂作者")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        title = QLabel("请作者喝杯咖啡 ☕")
        f = QFont()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        tip = QLabel("如果这个工具帮你省了几个小时调参，\n可以扫码随意打赏，金额无所谓。")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(tip)

        img = self._asset_path("donate.png") or self._asset_path("donate.jpg")
        if img is None:
            warn = QLabel("没找到收款码图片（assets/donate.jpg）。")
            warn.setStyleSheet("color:#b45309;")
            lay.addWidget(warn)
        else:
            pix = QPixmap(str(img))
            if pix.isNull():
                lay.addWidget(QLabel("收款码图片读不出来。"))
            else:
                if pix.width() > 340:
                    pix = pix.scaledToWidth(340, Qt.TransformationMode.SmoothTransformation)
                pic = QLabel()
                pic.setPixmap(pix)
                pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(pic)

        note = QLabel("微信扫码 · 感谢支持")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        row.addWidget(btn)
        row.addStretch(1)
        lay.addLayout(row)

        dlg.exec()
        self._log("谢谢支持：投喂面板已打开过。", "ok")

    # ================================================================ 文件

    def on_load_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Bambu Studio 工程文件", str(Path.home()),
            "Bambu 工程 (*.3mf *.bambu);;所有文件 (*.*)")
        if path:
            self.load_file(path)

    def on_reload_clicked(self) -> None:
        if self.project:
            self.load_file(str(self.project.path))
        else:
            self._log("还没有加载过文件。", "warn")

    def load_file(self, path: str | Path) -> None:
        self._busy(True)
        try:
            proj = threemf.ThreeMfProject.load(path)
        except threemf.ThreeMfError as exc:
            self._busy(False)
            self._log(f"加载失败：{exc}", "err")
            QMessageBox.critical(self, "加载失败", str(exc))
            return
        except Exception as exc:                        # 兜底，不让 UI 崩
            self._busy(False)
            self._log("加载时出现未预期错误：\n" + traceback.format_exc(), "err")
            QMessageBox.critical(self, "加载失败", f"{type(exc).__name__}: {exc}")
            return

        self.project = proj
        self.original_settings = dict(proj.settings)
        self.result = None
        self.last_output = None
        self.ed_src.setText(str(proj.path))
        self.ed_out.setText("")
        self.btn_save.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.btn_open_dir.setEnabled(False)

        det = detector.detect(proj, self.engine.rules)
        self.det = det
        self._apply_detection_to_ui(det)

        # 真机同步：喷嘴 / 流量 / 机器上限 / 板面，全部来自工程，只读
        try:
            self.hw = hardware.read(proj)
        except Exception as exc:
            self.hw = None
            self._log(f"真机信息读取失败（不影响调参）：{exc}", "warn")
        # 喷嘴直径与打印机同步：工程里的值优先，下拉自动跳到对应项
        if self.hw and self.hw.nozzle_diameter:
            nz = float(self.hw.nozzle_diameter)
            idx = self.cmb_nozzle.findData(nz)
            if idx >= 0:
                self.cmb_nozzle.setCurrentIndex(idx)
            else:
                self.cmb_nozzle.addItem(f"{nz:g} mm（工程值）", nz)
                self.cmb_nozzle.setCurrentIndex(self.cmb_nozzle.count() - 1)
        self._render_hw()

        self._analyse_model(proj)

        sliced = "已切片过（旧切片结果会在保存时被清掉）" if proj.is_sliced else "未切片"
        self.lbl_file_state.setText(
            f"已加载：{proj.path.name} · {proj.path.stat().st_size / 1024 / 1024:.2f} MB · "
            f"{len(proj.entries)} 个条目 · {len(proj.settings)} 个切片参数 · {sliced}")
        self._log(f"已加载 {proj.path}", "ok")
        self._log(f"参数条目 {len(proj.settings)} 个；{sliced}。")
        # 换工程时先清空上一份的自定义耗材选择，再按新耗材名重新匹配
        if self.cmb_custom.count() > 0:
            self._suppress = True
            self.cmb_custom.setCurrentIndex(0)
            self._suppress = False
        if self.custom_presets:
            self._autopick_custom()
        self._busy(False)
        if self.project:
            self._render_coverage(set(self.project.settings))
        self.run_optimize(silent=True)

    def _render_hw(self) -> None:
        """把工程里读到的真机信息显示出来（只读清单）。"""
        hw = self.hw
        if not hw:
            self.lbl_hw.setText("尚未加载工程")
            self.lbl_hw.setObjectName("muted")
            return
        lines = hw.summary_lines()
        # 喷嘴读到的值与下拉不一致时说明会怎么处理（流量要跟着换）
        extra: list[str] = []
        cur = self._current_nozzle()
        if hw.nozzle_diameter and abs(hw.nozzle_diameter - cur) > 1e-6:
            extra.append(
                f"（当前选 {cur:g} mm、工程里装的是 {hw.nozzle_diameter:g} mm —— "
                f"已按你的选择算，层高/线宽等比缩放，体积流量上限也按官方"
                f"「{cur:g} 喷嘴」标定重新折算，不再沿用工程那个喷嘴的值）")
        if self.result is not None:
            fl = getattr(self.result, "flow_limit", None)
            if fl:
                extra.append(f"本次采用体积流量上限 {fl:g} mm³/s")
            hd = getattr(self.result, "hotend", "")
            if hd:
                extra.append(hd)
            pl = getattr(self.result, "plate", "")
            if pl:
                extra.append(pl)
        if not hw.from_project:
            extra.append("（这个 3mf 里没读到机器信息，已回退到规则库里的机型基线）")
        text = " ｜ ".join(lines)
        if extra:
            text += " ｜ " + " ｜ ".join(extra)
        self.lbl_hw.setText(text)
        self.lbl_hw.setObjectName("muted")

    def _analyse_model(self, proj: threemf.ThreeMfProject) -> None:
        """读几何算形状画像；失败只降级，不影响调参主流程。"""
        self.model_profile = None
        self._profile_error = ""
        try:
            prof = model_analysis.analyse(
                proj, overhang_angle=float(proj.settings.get("support_threshold_angle", 30) or 30)
                if _is_number(proj.settings.get("support_threshold_angle")) else 30.0,
                layer_height=float(proj.settings.get("layer_height", 0.2))
                if _is_number(proj.settings.get("layer_height")) else 0.2)
        except model_analysis.ModelError as exc:
            self._profile_error = str(exc)
            self.lbl_shape.setText("模型形状：读不到几何（" + str(exc).splitlines()[0] + "）")
            self.lbl_shape.setObjectName("warn")
            self.chk_shape.setEnabled(False)
            self._log("模型形状分析跳过：" + str(exc).replace("\n", " "), "warn")
            return
        except Exception:
            self._profile_error = "未预期错误"
            self.lbl_shape.setText("模型形状：分析出错，已跳过形状自适应")
            self.chk_shape.setEnabled(False)
            self._log("模型形状分析出错：\n" + traceback.format_exc(), "err")
            return

        self.model_profile = prof
        self.chk_shape.setEnabled(True)
        tags = prof.tags()
        text = prof.summary()
        if tags:
            text += " ｜ " + "、".join(tags)
        if prof.sampled:
            text += f" ｜ 三角面 {prof.triangles} 个，已抽样分析"
        self.lbl_shape.setText("模型形状：" + text)
        self.lbl_shape.setObjectName("muted")
        self._log("模型形状：" + prof.summary(), "ok")
        if tags:
            self._log("形状标签：" + "、".join(tags))
        self._render_objects()

    def _render_brief(self, res=None) -> None:
        """结论卡：用户最想看的「这样调整后的结果」（不列参数值）。"""
        if not hasattr(self, "lbl_brief"):
            return
        res = res if res is not None else self.result
        if not res:
            self.lbl_brief.setText("优化后会显示成一段人话结论。")
            return
        try:
            lines = brief.build(
                res,
                thermal_rows=getattr(res, "thermal_rows", None),
                machine_note=getattr(res, "machine_sync_note", "") or "",
                support_ease=getattr(res, "support_ease", "standard") or "standard")
        except Exception:
            self.lbl_brief.setText("结论卡生成失败（不影响优化结果，详情见日志）。")
            self._log("结论卡生成失败：\n" + traceback.format_exc(), "warn")
            return
        head = lines[0] if lines else ""
        rest = lines[1:]
        html_parts = [f"<b>{html.escape(head)}</b>"]
        html_parts += [f"· {html.escape(x)}" for x in rest]
        self.lbl_brief.setText("<br>".join(html_parts))

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

    def _render_objects(self) -> None:
        """逐件调参明细表：每个对象判成什么原型、依据、会被怎么调。"""
        self.obj_tree.clear()
        prof = self.model_profile
        if not prof or not prof.objects:
            self.obj_tree.addTopLevelItem(QTreeWidgetItem(
                ["—", "—", "—", "尚未加载工程或工程里没有可解析的对象", "—"]))
            return
        mode = self._current_mode()
        try:
            details = shape_rules.per_object_detail(
                prof, mode=mode,
                profiles=self.engine.rules.get("shape_profiles"))
        except Exception:
            details = []
        if not details:
            for obj in prof.objects:
                pkey, why = shape_rules.classify(obj)
                label = (shape_rules.PROTO_BY_KEY[pkey].label
                         if pkey in shape_rules.PROTO_BY_KEY else pkey)
                self.obj_tree.addTopLevelItem(QTreeWidgetItem(
                    [f"件{obj.index + 1}", obj.summary(), label,
                     "、".join(why) if why else "未触发特殊特征", "—"]))
            return
        for det in details:
            item = QTreeWidgetItem([
                f"件{det['index'] + 1}", det["summary"], det["proto_label"],
                det["why"], det["ops"] or "—"])
            item.setToolTip(3, det["why"])
            item.setToolTip(4, det["ops"])
            self.obj_tree.addTopLevelItem(item)

    def _apply_detection_to_ui(self, det: detector.Detection) -> None:
        self._suppress = True
        idx = self.cmb_printer.findData(det.printer_key)
        self.cmb_printer.setCurrentIndex(idx if idx >= 0 else self.cmb_printer.count() - 1)
        idx = self.cmb_filament.findData(det.filament_key)
        self.cmb_filament.setCurrentIndex(idx if idx >= 0 else self.cmb_filament.count() - 1)
        idx = self.cmb_nozzle.findData(float(det.nozzle))
        self.cmb_nozzle.setCurrentIndex(idx if idx >= 0 else 1)
        # 热端流量类型：把工程里识别到的填进下拉（用户可改，改了就按新的算）
        self.hotend_info = hotend.detect(self.original_settings or {})
        hidx = self.cmb_hotend.findData(self.hotend_info.key)
        self.cmb_hotend.setCurrentIndex(hidx if hidx >= 0 else 0)
        # 板子：工程里写了就默认选它；没写就留在「跟随工程」
        try:
            raw_bed = (self.original_settings or {}).get("curr_bed_type")
            if isinstance(raw_bed, list):
                raw_bed = raw_bed[0] if raw_bed else ""
            if str(raw_bed or "").strip():
                bed_now = thermal.bed_type_of(self.original_settings)
                self._bed_keep_temp_value = None
                bidx = self.cmb_bed.findData(bed_now)
                self.cmb_bed.setCurrentIndex(bidx if bidx >= 0 else 0)
                if bidx < 0:
                    # 工程里的板子本机 Studio 不认识（典型：Supertack 出现在旧版 Studio 上）。
                    # 那就换成本机认识的板，但**把原板温带过去**，不偷偷改温度。
                    fallback = self._pick_fallback_bed()
                    if fallback:
                        fidx = self.cmb_bed.findData(fallback)
                        if fidx >= 0:
                            self.cmb_bed.setCurrentIndex(fidx)
                        keep = thermal.read_bed_temp(self.original_settings, bed_now)
                        self._bed_keep_temp_value = keep
                        self._log(
                            f"⚠ 工程用的是「{thermal.plate_label(bed_now)}」，"
                            f"但本机 Studio 的板子里没有它 —— 已换成"
                            f"「{thermal.plate_label(fallback)}」"
                            + (f"，并把板温以原来的 {keep:.0f}°C 为基准（室温修正照常叠加）。"
                               if keep else "，板温按工程原值走。"),
                            "warn")
                    else:
                        self._log(
                            f"⚠ 工程用的是「{thermal.plate_label(bed_now)}」，"
                            f"本机 Studio 也不认识替代板 —— 按「跟随工程」处理，"
                            f"板温/风速仍按工程里的板子算。", "warn")
        except Exception:
            pass
        self._suppress = False
        if hasattr(self, "cmb_hotend") and self.original_settings:
            self._log("热端流量：" + self.hotend_info.summary_line(),
                      "info" if self.hotend_info.detected else "warn")

        nozzle_s = f"{det.nozzle:g}" if det.nozzle else "—"
        self.lbl_raw.setText(
            f"原始值：printer_model={det.printer_raw or '—'} · "
            f"filament_type={det.filament_raw or '—'} · nozzle={nozzle_s} mm")
        if det.warnings:
            self.lbl_warn.setText("⚠ " + " / ".join(det.warnings))
            self.lbl_warn.setVisible(True)
        else:
            self.lbl_warn.setVisible(False)
        for note in det.notes:
            self._log(note, "warn")

    def on_pick_output(self) -> None:
        default = self._default_output()
        path, _ = QFileDialog.getSaveFileName(
            self, "另存优化后的工程", str(default), "Bambu 工程 (*.3mf)")
        if path:
            self.ed_out.setText(path)

    def _default_output(self) -> Path:
        if not self.project:
            return Path.home() / "optimized_v2.3mf"
        src = self.project.path
        # 用户要求「出第二版同时保留第一版」：输出名带 v2 且带时间戳，
        # 不同次优化各存一份，永不覆盖上一版和原工程。
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cand = src.with_name(f"{src.stem}_optimized_v2_{stamp}.3mf")
        n = 2
        while cand.exists():
            cand = src.with_name(f"{src.stem}_optimized_v2_{stamp}_{n}.3mf")
            n += 1
        return cand

    # ================================================================ 识别/模式

    def _current_printer(self) -> str:
        return self.cmb_printer.currentData() or "GENERIC"

    def _current_filament(self) -> str:
        return self.cmb_filament.currentData() or "GENERIC"

    def _current_nozzle(self) -> float:
        return float(self.cmb_nozzle.currentData() or 0.4)

    def _current_mode(self) -> str:
        for key, rb in self.radios.items():
            if rb.isChecked():
                return key
        return "balanced"

    # ---- v1.2 新增的几个维度（热床/风速/支撑/接缝/方案）
    def _printer_not_support(self) -> str:
        """所选机型不支持的板型（官方 machine 预设的 not_support_bed_type）。"""
        key = self._current_printer()
        printers = (self.engine.rules.get("printers", {}) or {})
        info = printers.get(key) or {}
        return str(info.get("not_support_bed_type") or "")

    def _studio_env(self):
        """本机 Studio 的能力快照（缓存，第一次探测约几十毫秒）。"""
        env = getattr(self, "_studio_cache", None)
        if env is None:
            try:
                env = studio_env.detect()
            except Exception:
                env = studio_env.StudioEnv()
            self._studio_cache = env
        return env

    def _pick_fallback_bed(self) -> str:
        """工程里的板子本机不认时，选一块本机认识的替代板。

        优先顺序照顾「板温和外观别变太多」：纹理 PEI → 光面/高温 → 工程板 → 低温板。
        """
        for name in ("Textured PEI Plate", "Smooth PEI Plate / High Temp Plate",
                     "Engineering Plate", "Cool Plate"):
            idx = self.cmb_bed.findData(name)
            if idx >= 0:
                return name
        return ""

    def _studio_plate_filter(self) -> set | None:
        """本机 Studio 认识的板子；它没装/读不到就返回 None（不拦）。"""
        env = self._studio_env()
        if not env.found or not env.plates:
            return None
        return set(env.plates)

    def _bed_keep_temp(self) -> float | None:
        """换板子时沿用原板温；没换就是 None。"""
        return getattr(self, "_bed_keep_temp_value", None)

    def _fill_bed_options(self) -> None:
        """按当前机型重建板子下拉：只留 Studio 真有、这台机器也支持的板型。"""
        if not hasattr(self, "cmb_bed"):
            return
        keep = self.cmb_bed.currentData() if self.cmb_bed.count() else ""
        self.cmb_bed.blockSignals(True)
        self.cmb_bed.clear()
        self.cmb_bed.addItem("（跟随工程）", "")
        allowed = self._studio_plate_filter()
        for label, key in thermal.plate_options(self._printer_not_support()):
            if allowed is not None and key not in allowed:
                continue
            self.cmb_bed.addItem(label, key)
        idx = self.cmb_bed.findData(keep) if keep else 0
        self.cmb_bed.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_bed.blockSignals(False)

    def _refill_bed_options(self) -> None:
        """换机型后调用：重建下拉；原来选的板被这台机器排除时退回「跟随工程」。"""
        before = self.cmb_bed.currentData() if self.cmb_bed.count() else ""
        self._fill_bed_options()
        after = self.cmb_bed.currentData() if self.cmb_bed.count() else ""
        if before and before != after:
            self._log(
                f"所选机型不支持「{thermal.plate_label(before)}」，板子已退回「跟随工程」。"
            )

    def _current_bed(self) -> str:
        return self.cmb_bed.currentData() or ""

    def _current_room(self) -> float | None:
        """输入框里的室温；空着/写错就是不指定（返回 None）。"""
        txt = (self.ed_room.text() or "").strip().replace("°C", "").replace("°c", "")
        if not txt:
            return None
        try:
            return float(int(txt))
        except ValueError:
            return None

    def _current_fan_trim(self) -> int | None:
        """None = 自动（交给 thermal 按耗材/室温算）；整数 = 用户手动指定的偏移。"""
        data = self.cmb_fan.currentData()
        return None if data is None else int(data)

    def _current_ease(self) -> str:
        return self.cmb_ease.currentData() or "standard"

    def _current_seam(self) -> bool:
        return bool(self.chk_seam.isChecked())

    def _filament_slots(self) -> int:
        """工程里有几个耗材槽（filament_settings_id 是分槽数组）。"""
        raw = self.project.settings.get("filament_settings_id") if self.project else None
        try:
            if isinstance(raw, str) and raw.strip().startswith("["):
                arr = json.loads(raw)
                return max(1, len(arr))
        except ValueError:
            pass
        return 1

    def _current_fil_mode(self) -> str:
        return self.cmb_fil_mode.currentData() or "file"

    def _current_iron(self) -> str:
        return self.cmb_iron.currentData() or "keep"

    def _current_iron_auto(self) -> bool:
        return bool(self.chk_iron_auto.isChecked())

    def _current_special(self) -> dict:
        return dict(self._special_modes or {})

    def on_pick_special(self) -> None:
        """勾「其他」页的特殊模式：默认全跟随工程，只写你亲手选的。"""
        from ui.special_dialog import SpecialDialog
        try:
            opts = special.options(self.engine.rules)
        except Exception:
            self._log("读取特殊模式选项失败：" + chr(10) + traceback.format_exc(), "err")
            return
        dlg = SpecialDialog(opts, self._special_modes, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        self._special_modes = dlg.selections()
        if self._special_modes:
            names = []
            table = {o["key"]: o for o in opts}
            for key, value in self._special_modes.items():
                item = table.get(key) or {}
                shown = dict(item.get("choices") or []).get(str(value), str(value))
                names.append(f"{item.get('label', key)}={shown}")
            self.lbl_special.setText("特殊模式：" + "、".join(names))
        else:
            self.lbl_special.setText("特殊模式：全部跟随工程")
        self._reoptimize()

    def _current_custom(self) -> bambu_profiles.FilamentPreset | None:
        name = self.cmb_custom.currentData()
        if not name:
            return None
        for p in self.custom_presets:
            if p.name == name:
                return p
        return None

    def _current_overlay(self) -> dict | None:
        p = self._current_custom()
        return bambu_profiles.to_overlay(p) if p else None

    def _sync_family_to_custom(self) -> bool:
        """选了自定义耗材时，把「耗材类型」下拉同步到它所属的族，避免 PLA 选的料套 PETG 基线。"""
        p = self._current_custom()
        if not p:
            return False
        cur = self._current_filament()
        if cur == p.family:
            return False
        idx = self.cmb_filament.findData(p.family)
        if idx < 0:
            return False
        self._suppress = True
        self.cmb_filament.setCurrentIndex(idx)
        self._suppress = False
        self._log(f"自定义耗材「{p.name}」属于 {p.family} 族，耗材类型已自动切到 {p.family}。")
        return True

    # ================================================================ 自定义耗材同步

    def on_sync_filaments(self, quiet: bool = False) -> None:
        """扫描 Bambu Studio / OrcaSlicer 用户预设目录，填充自定义耗材下拉。"""
        self._busy(True)
        try:
            presets = bambu_profiles.scan()
        except Exception:
            self._busy(False)
            self._log("扫描自定义耗材时出错：\n" + traceback.format_exc(), "err")
            return
        self._busy(False)

        self.custom_presets = presets
        self._suppress = True
        self.cmb_custom.clear()
        self.cmb_custom.addItem("（不使用自定义耗材）", None)
        for p in presets:
            mark = "" if p.resolvable else "  ⚠"
            self.cmb_custom.addItem(f"{p.name}{mark}", p.name)
            i = self.cmb_custom.count() - 1
            self.cmb_custom.setItemData(i, p.display_detail, Qt.ItemDataRole.ToolTipRole)
        self.cmb_custom.setEnabled(bool(presets))
        self._suppress = False
        self._sync_preview_custom_list()
        self._render_rules_preview()

        summary = bambu_profiles.describe(presets)
        if not presets:
            self._log("没有找到 Bambu Studio 的用户自定义耗材。"
                      "先在 Bambu Studio 里「另存为自定义耗材」，再回来点同步。", "warn")
            roots = bambu_profiles.candidate_roots()
            if not roots:
                self._log("也没找到预设目录，确认 Bambu Studio 已经至少启动过一次、"
                          "并且不是装在非标准位置。", "warn")
            return
        self._log(f"已同步 {summary}", "ok")
        for p in presets:
            tail = "" if p.resolvable else "（父预设缺失，按族基线处理）"
            self._log(f"  · {p.name} ← {p.family} ｜ {p.display_detail}{tail}")
        if not quiet:
            self.statusBar().showMessage(f"已同步 {len(presets)} 支自定义耗材", 5000)
        # 自动挑一支名字与工程里识别出的耗材最接近的
        self._autopick_custom()

    def _autopick_custom(self) -> None:
        """把工程里读到的耗材名优先匹配到自定义表。

        保守起见：只认「名字有实质重合」的匹配，族名（PLA / PETG 这类 3~4 个字母）
        单独出现不算，否则只要是 PLA 工程就会被随手挂到某支自定义料上；
        带「拷贝 / 副本 / copy」字样的预设也不自动选。
        """
        if not self.custom_presets or not self.det:
            return
        raw = (self.det.filament_raw or "").strip().lower()
        if len(raw) < 6:            # 只有族名，谈不上是哪支具体耗材
            return
        best: tuple[int, str] | None = None
        for p in self.custom_presets:
            nl = (p.name or "").lower()
            if not nl or any(w in nl for w in ("拷贝", "副本", "copy", "- 拷贝")):
                continue
            if nl in raw:
                score = len(nl) + 5
            elif raw in nl:
                score = len(raw)
            elif p.family.lower() in raw and len(nl) >= 8:
                score = 1                      # 族对上且名字够长，只作最低优先
            else:
                continue
            if best is None or score > best[0]:
                best = (score, p.name)
        if not best or best[0] <= 1:
            return
        idx = self.cmb_custom.findData(best[1])
        if idx > 0:
            self._suppress = True
            self.cmb_custom.setCurrentIndex(idx)
            self._suppress = False
            self._log(f"自动匹配到自定义耗材「{best[1]}」，将使用它标定的参数。", "ok")

    def _on_override_changed(self, *_) -> None:
        if self._suppress:
            return
        if not self.project:
            return
        # 选自定义耗材时把「耗材类型」拉到同族，避免跨族套错基线
        self._sync_family_to_custom()
        det = self.det
        manual = []
        if det:
            if self._current_printer() != det.printer_key:
                manual.append(f"机型手动改为 {self.cmb_printer.currentText()}")
            if self._current_filament() != det.filament_key:
                manual.append(f"耗材手动改为 {self.cmb_filament.currentText()}")
            if abs(self._current_nozzle() - det.nozzle) > 1e-6:
                manual.append(f"喷嘴手动改为 {self.cmb_nozzle.currentText()}")
        p = self._current_custom()
        if p:
            manual.append(f"使用自定义耗材「{p.name}」（{p.display_detail}）")
        if manual:
            self._log("手动修正：" + "；".join(manual), "warn")
        self.run_optimize(silent=True)

    def _mode_hint_text(self, key: str) -> str:
        """模式提示 + 该档的时长预算（预算值来自规则库 modes.<k>.time_budget_pct）。"""
        text = MODE_HINT.get(key, "")
        node = self.rules.get("modes", {}).get(key, {}) or {}
        budget = node.get("time_budget_pct")
        if budget is None:
            tail = "时长预算：不限（这一档靠小层高换质量，不回调层高）"
        else:
            tail = f"时长预算：最多慢 {float(budget):g}%（超出会按代价最小的顺序自动回退）"
        return f"{text}\n{tail}"

    def _on_mode_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked or self._suppress:
            return
        key = MODE_ORDER[btn_id] if 0 <= btn_id < len(MODE_ORDER) else "balanced"
        self.lbl_mode_hint.setText(self._mode_hint_text(key))
        if self.project:
            self.run_optimize(silent=True)

    # ================================================================ 优化

    def on_optimize_clicked(self) -> None:
        if not self.project:
            QMessageBox.information(self, "还没加载文件", "先点「加载 3mf」选一个 Bambu Studio 工程。")
            return
        self.run_optimize(silent=False)

    def _reoptimize(self) -> None:
        """静默重算（供开关/下拉变化时用）。"""
        if self.project:
            self.run_optimize(silent=True)

    def run_optimize(self, silent: bool = False) -> None:
        if not self.project:
            return
        self._busy(True)
        try:
            det = self.det
            printer = self._current_printer()
            filament = self._current_filament()
            nozzle = self._current_nozzle()
            mode = self._current_mode()
            overlay = self._current_overlay()

            # 手动改过机型/耗材时，不再沿用「识别失败」类告警（避免误导）
            same_as_detected = bool(det) and printer == det.printer_key and filament == det.filament_key
            warns = list(det.warnings) if (det and same_as_detected) else []
            notes = list(det.notes) if (det and same_as_detected) else []

            profile = self.model_profile if (self.chk_shape.isChecked() and self.model_profile) else None
            # 时长预算现在由规则库按档位给定（modes.<k>.time_budget_pct）：
            #   均衡 40% / 草稿 10% / 强度 200% / 质量 170% / 精细两档不限。
            # 勾选 = 交给引擎按这个预算自动回调；不勾 = 传一个极大的上限，
            # 等于完全不做时长回调（用户想自己控制时间时用）。
            cap = None if self.chk_timecap.isChecked() else 9999.0

            # 自定义耗材自带族信息：以它为准选基线，避免 UI 状态不一致时跨族套错
            if overlay and overlay.get("family") and overlay["family"] != filament:
                notes.append(
                    f"自定义耗材「{overlay.get('label')}」属于 {overlay['family']} 族，"
                    f"基线已按 {overlay['family']} 计算（下拉里选的 {filament} 只影响界面显示）。")
                filament = overlay["family"]

            # 喷嘴：用户手动改过下拉就以 UI 为准（nozzle_explicit=True），
            # 否则交给引擎按工程 machine 页的值同步（那是这台机器真实装的喷嘴）。
            hw_noz = self.hw.nozzle_diameter if self.hw else None
            nozzle_explicit = bool(hw_noz) and abs(float(nozzle) - float(hw_noz)) > 1e-6

            res = self.engine.optimize(
                self.original_settings,
                printer_key=printer, filament_key=filament, nozzle=nozzle,
                mode_key=mode, detection_warnings=warns, detection_notes=notes,
                filament_overlay=overlay, model_profile=profile, time_cap_pct=cap,
                hardware_info=self.hw, nozzle_explicit=nozzle_explicit,
                hotend_flow=((self.cmb_hotend.currentData() or None)
                             if getattr(self, "_hotend_touched", False) else None),
                support_mode=(self.cmb_support.currentData() or "auto"),
                support_ease=self._current_ease(),
                room_temp_c=self._current_room(),
                bed_type=self._current_bed(),
                fan_trim=self._current_fan_trim(),
                seam_smooth=self._current_seam(),
                ironing_choice=self._current_iron(),
                ironing_auto=self._current_iron_auto(),
                filament_mode=self._current_fil_mode(),
                special_modes=self._current_special(),
                bed_keep_temp=self._bed_keep_temp())
        except Exception:
            self._busy(False)
            self._log("优化时出错：\n" + traceback.format_exc(), "err")
            if not silent:
                QMessageBox.critical(self, "优化失败", "规则计算异常，详情见下方日志。")
            return

        self.result = res
        self.last_timecap = getattr(self.engine, "last_timecap", None)
        self._fill_table()
        self._render_hw()
        self._render_objects()
        self._render_derivations(res)
        self._render_brief(res)

        changed = res.changed_count if hasattr(res, "changed_count") else sum(1 for r in res.rows if r.changed)
        delta = res.time.delta_pct if res.time else 0.0
        self.lbl_summary.setText(
            f"{res.mode_label} · 改动 {changed} 项 · 预计时长 {delta:+.1f}%")
        self.lbl_summary.setToolTip(res.time.text if res.time else "")

        self.btn_save.setEnabled(True)
        self.btn_report.setEnabled(True)
        self._busy(False)

        self._log("—— 优化完成 ——", "ok")
        self._log(f"机型 {res.printer_label} ｜ 耗材 {res.filament_label} ｜ 喷嘴 {res.nozzle:g} mm ｜ 模式 {res.mode_label}")
        self._log(f"改动 {changed} 项，预计打印时长变化 {delta:+.1f}%（{res.time.text if res.time else ''}）")
        for w in res.warnings:
            self._log("⚠ " + w, "warn")
        for n in res.notes:
            self._log("· " + n)
        if res.skipped:
            names = "、".join(r.label for r in res.skipped)
            self._log(f"工程里没有这些键，只给推荐值不写入：{names}", "warn")
        if getattr(res, "blocked", None):
            by_scope: dict[str, int] = {}
            for r in res.blocked:
                by_scope[r.scope] = by_scope.get(r.scope, 0) + 1
            detail = "、".join(f"{scope.SCOPE_LABEL.get(k, k)} {v} 项"
                              for k, v in sorted(by_scope.items()))
            self._log(f"按你的要求，这些页的参数只读不改：{detail}。", "warn")
        if silent:
            self.statusBar().showMessage(f"已自动按「{res.mode_label}」重算", 4000)

    # ================================================================ 表格

    def _fill_table(self) -> None:
        self.table.clear()
        res = self.result
        if not res:
            return
        only_changed = self.chk_changed.isChecked()
        kw = self.ed_search.text().strip().lower()
        scope_filter = self.cmb_scope.currentData()
        groups: dict[str, QTreeWidgetItem] = {}
        shown = 0
        for row in res.rows:
            if only_changed and not row.changed:
                continue
            if kw and kw not in row.label.lower() and kw not in row.key.lower():
                continue
            if scope_filter == scope.PROCESS and row.scope != scope.PROCESS:
                continue
            if scope_filter == "readonly" and row.scope == scope.PROCESS:
                continue
            parent = groups.get(row.group)
            if parent is None:
                parent = QTreeWidgetItem([row.group_label, "", "", "", "", "", ""])
                f = parent.font(0)
                f.setBold(True)
                parent.setFont(0, f)
                parent.setFirstColumnSpanned(True)
                parent.setForeground(0, QColor("#111827"))
                self.table.addTopLevelItem(parent)
                groups[row.group] = parent
            if row.changed:
                write = "是" if row.will_write else "否"
                reason = row.reason or ("目标机型/耗材下该参数不该动" if not row.will_write else "")
            else:
                write = ""
                reason = ""
            spot = studio_ui.info(row.key, fallback_label=row.label, group=row.group)
            item = QTreeWidgetItem([row.label, spot.path,
                                     scope.SCOPE_LABEL.get(row.scope, row.scope),
                                     row.old_display, row.new_display, write, reason])
            item.setForeground(2, QColor(COLOR_MUTED if row.scope == scope.PROCESS else COLOR_WARN))
            if row.changed:
                item.setForeground(4, QColor(COLOR_OK))
                f = item.font(4)
                f.setBold(True)
                item.setFont(4, f)
                if not row.will_write:
                    item.setForeground(5, QColor(COLOR_WARN))
                    item.setToolTip(5, row.skip_reason or "工程文件里没有这个键，只给推荐值")
            else:
                item.setForeground(3, QColor(COLOR_MUTED))
                item.setForeground(4, QColor(COLOR_MUTED))
            if spot.hidden:
                item.setForeground(1, QColor(COLOR_WARN))
            item.setData(0, Qt.ItemDataRole.UserRole, row.key)
            tip = [f"键名：{row.key}", f"Studio 位置：{spot.path}"]
            if spot.search_hint:
                tip.append(f"在 Studio 搜索框里输入：{spot.search_hint}")
            item.setToolTip(0, "\n".join(tip))
            item.setToolTip(1, "\n".join(tip))
            if reason:
                item.setToolTip(6, reason)
            parent.addChild(item)
            shown += 1
        for i in range(self.table.topLevelItemCount()):
            self.table.topLevelItem(i).setExpanded(True)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)

    def _on_table_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self._log(f"参数键名：{key}（Bambu Studio 开发者模式里可搜到这个键）")

    def _on_table_menu(self, pos) -> None:
        """右键菜单：复制一行（参数/原值/新值/依据），或只复制键名。"""
        item = self.table.itemAt(pos)
        if item is None:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        cols = [item.text(i) for i in range(self.table.columnCount())]
        menu = QMenu(self)
        spot = studio_ui.info(str(key or ""), fallback_label=cols[0]) if key else None
        act_row = menu.addAction("复制这一行（制表符分隔，可直接粘进 Excel）")
        act_key = menu.addAction(f"复制键名：{key or '（无）'}")
        act_key.setEnabled(bool(key))
        act_spot = menu.addAction(
            f"复制 Studio 搜索词：{spot.search_hint}" if (spot and spot.search_hint)
            else "这条在 Studio 界面上没有对应开关")
        act_spot.setEnabled(bool(spot and spot.search_hint))
        act = menu.exec(self.table.viewport().mapToGlobal(pos))
        if act is act_row:
            QApplication.clipboard().setText("\t".join(cols))
            self._log("已复制一行参数到剪贴板。")
        elif act is act_key:
            QApplication.clipboard().setText(str(key))
            self._log(f"已复制键名：{key}")
        elif act is act_spot:
            QApplication.clipboard().setText(spot.search_hint)
            self._log(f"已复制 Studio 搜索词「{spot.search_hint}」—— 到 Studio 工艺面板的搜索框里粘上就能跳过去。")

    # ================================================================ 保存 / 报告

    # ---------------------------------------------------------- 切片器核对

    def on_slice_check(self) -> None:
        """拿刚保存出来的 3mf，调本机 Studio 切一片，把实际生效的值读回来。"""
        path = getattr(self, "last_output", "") or ""
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "先保存", "先点「保存为 3mf」，再拿这个文件去切片核对。")
            return
        if getattr(self, "_slice_worker", None) is not None:
            return
        exe = slice_check.find_studio()
        if not exe:
            self.lbl_slice.setText("没找到 bambu-studio.exe（装完 Bambu Studio 再试，或把路径告诉作者）。")
            self._log("⚠ 没找到 bambu-studio.exe，跳过切片核对。", "err")
            return

        want = {}
        for key in slice_check.CHECKED_KEYS:
            if self.result is not None and key in self.result.write_values:
                want[key] = self.result.write_values[key]
        for key in ("supertack_plate_temp", "textured_plate_temp", "hot_plate_temp",
                    "eng_plate_temp", "cool_plate_temp"):
            if self.result is not None and key in self.result.write_values:
                want[key] = self.result.write_values[key]
                break
        if self.result is not None and "enable_support" in self.result.write_values:
            want["enable_support"] = self.result.write_values["enable_support"]

        self.btn_slice.setEnabled(False)
        self.lbl_slice.setText(f"正在用 {os.path.basename(exe)} 切片…（约 1 分钟，界面可继续用）")
        self._log(f"切片核对：{exe} --slice … {os.path.basename(path)}")
        worker = _SliceWorker(path, want, self)
        worker.done.connect(self._on_slice_done)
        self._slice_worker = worker
        worker.start()

    def _on_slice_done(self, res) -> None:
        self._slice_worker = None
        self.btn_slice.setEnabled(True)
        try:
            self._render_slice(res)
        except Exception:
            self._log("⚠ 切片核对结果渲染失败：" + traceback.format_exc(), "err")

    def _render_slice(self, res) -> None:
        for note in getattr(res, "notes", []) or []:
            self._log(f"· 切片兼容处理：{note}")
        for warn in getattr(res, "warnings", []) or []:
            self._log(f"⚠ {warn}", "err")
            self.lbl_slice.setText(str(warn))
        probe = getattr(res, "probe", None)
        if probe is None:
            if getattr(res, "log_tail", ""):
                self._log("切片器输出（尾部）：")
                for line in res.log_tail.splitlines():
                    self._log("    " + line)
            return

        tree = self.verify_tree
        head = QTreeWidgetItem(["—— 切片器实测 gcode ——", "表格里的值", "gcode 里的值", "结果"])
        for col in range(4):
            head.setForeground(col, QColor("#1d6fb8"))
        tree.addTopLevelItem(head)

        bad = 0
        for key, want, got, same in getattr(res, "rows", []) or []:
            item = QTreeWidgetItem([key, want, got, "✅ 生效" if same else "⚠ 没生效"])
            if not same:
                bad += 1
                for col in range(4):
                    item.setForeground(col, QColor("#c0392b"))
            tree.addTopLevelItem(item)
        last = tree.topLevelItem(tree.topLevelItemCount() - 1)
        tree.scrollToItem(last or head)

        total = len(getattr(res, "rows", []) or [])
        head_txt = (f"切片实测：{total - bad}/{total} 项一致 ｜ 层数 {probe.layers} ｜ "
                    f"预计 {probe.time_text or '?'} ｜ 支撑路径 {probe.support_moves} 条")
        self.lbl_slice.setText(head_txt + ("（全部一致）" if bad == 0 else "（有项没生效，见标红）"))
        self._log(head_txt)
        if bad:
            self._log(f"⚠ 有 {bad} 项在 gcode 里和表格不一致：可能是机型上限、体积流量或层高范围把它夹掉了。", "err")

        # 全量逐键核对：写进去的每一项，切片器是不是真的用了这个值
        all_rows = getattr(res, "all_rows", []) or []
        if not all_rows:
            return
        head2 = QTreeWidgetItem(["—— 全量核对（写入的每一项 vs 切片器实际采用）——",
                                 "写进去的", "gcode 里", "结果"])
        for col in range(4):
            head2.setForeground(col, QColor("#1d6fb8"))
        tree.addTopLevelItem(head2)

        over = 0
        for key, want, got, verdict in all_rows:
            if verdict == "ok":
                text, colour = "✅ 生效", None
            elif verdict == "overridden":
                text, colour = "⚠ 被切片器改成别的值", QColor("#c0392b")
                over += 1
            else:
                text, colour = ("· 切片器内部开关（不进 gcode，正常）"
                                 if key in slice_check.KNOWN_NO_GCODE else
                                 "· 不参与切片（这类键不进 gcode 配置）"), None
            item = QTreeWidgetItem([key, str(want), str(got) if got else "—", text])
            if colour is not None:
                for col in range(4):
                    item.setForeground(col, colour)
            tree.addTopLevelItem(item)

        ok_n = getattr(res, "effective_ok", 0)
        absent = [k for k in (getattr(res, "effective_absent", []) or [])
                  if k not in slice_check.KNOWN_NO_GCODE]
        tail = (f"全量核对：写入 {len(all_rows)} 项 → 切片器采用一致的 {ok_n} 项"
                f"，被改成别的值 {over} 项，不参与切片 {len(absent)} 项")
        self._log(tail, "ok" if over == 0 else "err")
        if over == 0 and not absent:
            self.lbl_slice.setText(head_txt + " ｜ 写入的每一项都进了 gcode")
        over_keys = [row[0] for row in all_rows if row[3] == "overridden"]
        if over_keys:
            self._log("⚠ 这些键切片器没采用文件里的值：" + "、".join(over_keys[:12]), "err")

    def on_save_3mf(self) -> None:
        if not self.project or not self.result:
            QMessageBox.information(self, "先优化", "还没有可保存的优化结果。")
            return
        target = self.ed_out.text().strip()
        if not target:
            target = str(self._default_output())
            self.ed_out.setText(target)
        self._busy(True)
        try:
            fp_before = safety.fingerprint()
            written, skipped = self.project.apply(
                self.result.write_values,
                allow_missing=(thermal.STANDARD_KEYS | machine_sync.SYNC_KEYS
                                  | seam_plan.STANDARD_KEYS
                                  | support_model.SUPPORT_KEYS))
            # v1.2：同步机器页（机型/工艺前缀/板面尺寸/机器上限）。
            # 不做这一步，Studio 打开时按机器页认机型，会把参数按机器预设盖回默认值
            # —— 这正是用户说的「选了机型后 3mf 不对应 / 手选机型参数变回默认」。
            mp = machine_sync.plan(
                self.engine.rules, printer_key=self._current_printer(),
                nozzle=self._current_nozzle(),
                detected_key=(getattr(self.det, "printer_key", "") if self.det else ""),
                current=self.project.settings)
            machine_written = 0
            if mp.ops:
                mv, _ms = self.project.apply(mp.ops, allow_missing=machine_sync.SYNC_KEYS)
                machine_written = len(mv)
            # 耗材页的处理方式：keep 档在引擎里已经把这些键筛掉了；
            # new 档在这里把耗材名换成「原名 + 优化」—— Studio 里另存即得一份新耗材，
            # 你原来那份预设一个字都不会被改。
            fp = filament_write.plan(
                self._current_fil_mode(),
                base_name=str(self.project.settings.get("filament_settings_id") or ""),
                settings=self.project.settings,
                slots=self._filament_slots())
            filament_written = 0
            if fp.ops:
                fv, _fs = self.project.apply(fp.ops,
                                             allow_missing=frozenset({"filament_settings_id"}))
                filament_written = len(fv)
            # 关键：告诉 Studio「这些键不是预设值，别用预设覆盖」
            # 三槽都要声明：工艺 → 槽0，耗材+热床/风速 → 槽1，机器 → 槽2
            diff_info = preset_diff.apply_to_project(
                self.project,
                also=(list(self.result.write_values.keys()) + list(mp.ops.keys())
                      + list(fp.ops.keys())))
            # 工艺档名默认不动（用户要求只改工艺参数）；
            # 只有在勾选「标为自定义」时才改这一行元数据
            renamed = ""
            if self.chk_custom_profile.isChecked():
                renamed = self.project.mark_custom_process()
            out = self.project.save_as(target)
            # 保存后自检：重新打开新 3mf，核对写进去的值 == UI 里显示的值
            expected = dict(self.result.write_values)
            for k, v in fp.ops.items():
                expected.setdefault(k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                                    if isinstance(v, (list, dict)) else str(v))
            for k, v in mp.ops.items():
                expected.setdefault(k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                                    if isinstance(v, (list, dict)) else str(v))
            problems = safety.self_check(out, expected)
            fp_changed = safety.diff_fingerprint(fp_before, safety.fingerprint())
        except threemf.ThreeMfError as exc:
            self._busy(False)
            self._log(f"保存失败：{exc}", "err")
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        except Exception as exc:
            self._busy(False)
            self._log("保存时出错：\n" + traceback.format_exc(), "err")
            QMessageBox.critical(self, "保存失败", f"{type(exc).__name__}: {exc}")
            return
        self._busy(False)
        self.last_output = out
        self.btn_open_dir.setEnabled(True)

        # 让下一次优化以「已写入文件」为基准，避免重复点保存时基准错位
        self.original_settings = dict(self.project.settings)
        self._log(f"已写入 {len(written)} 项工艺参数，跳过 {len(skipped)} 项（工程里无此键）。", "ok")
        if machine_written:
            self._log(f"已同步机器页 {machine_written} 项（机型 / 板面尺寸 / 机器上限）。", "ok")
        for n in mp.notes:
            self._log("· " + n)
        for w in mp.warnings:
            self._log("⚠ " + w, "warn")
        if filament_written and fp.name:
            self._log(f"耗材已另存为「{fp.name}」（{filament_written} 项）："
                      "Studio 打开后会显示成一份改过但未保存的耗材，"
                      "在耗材列表里点「保存」就多出一份新的，原预设不变。", "ok")
        for n in fp.notes:
            self._log("· " + n)
        if self._current_fil_mode() == "keep":
            self._log("· 你选了「不改耗材页」：热床温度、风速、喷头温度等耗材页的键一个都没写。", "info")
        if self.result.ironing:
            self._log("· " + self.result.ironing)
        for n in getattr(self.result, "special_notes", []) or []:
            self._log("· " + n)
        self._log(f"已声明预设差异 {diff_info} —— Studio 只对声明过的键采用文件里的值。", "info")
        self._render_verify(out, expected, problems)
        if renamed:
            self._log(f"工艺档已标为自定义：print_settings_id = {renamed}"
                      f"（Studio 会采用文件里的参数，不会再回退到同名系统预设）", "info")
        if problems:
            self._log("⚠ 保存自检发现写入不一致：" + "；".join(problems[:6]), "err")
        else:
            self._log("保存自检通过：新 3mf 里的参数与表格里显示的完全一致。", "ok")
        if fp_changed:
            self._log("⚠ 检测到 Bambu Studio 预设目录在一次保存期间发生变化（不该发生）："
                      + "；".join(fp_changed[:6]), "err")
        else:
            self._log("预设隔离检查通过：Bambu Studio 的耗材/工艺/机型预设一个都没动。", "ok")
        self._log(f"输出：{out}", "ok")
        QMessageBox.information(
            self, "保存成功",
            f"已另存：\n{out}\n\n写入 {len(written)} 项参数。\n"
            "用 Bambu Studio 打开这个新文件，直接切片即可。\n"
            "原工程文件没有被修改。")

    def _compat_rows(self, settings: dict) -> list:
        """本机 Studio 认不认识这份文件：版本 / 板子 / 机型，三个最容易导致「导入不对」的点。"""
        rows = []
        try:
            env = self._studio_env()
            rep = studio_env.compat_report(settings, env, chosen_plate=self._current_bed())
        except Exception as exc:
            self._log(f"⚠ 本机 Studio 兼容性检查失败：{exc}", "warn")
            return rows
        if not rep.get("studio_found"):
            self._log("本机没找到 Bambu Studio，跳过兼容性检查（不影响文件本身）。")
            return rows

        def add(name: str, value: str, good: bool) -> None:
            item = QTreeWidgetItem([name, value, "—", "✅ 认识" if good else "⚠ 可能会被改回默认"])
            if not good:
                for col in range(4):
                    item.setForeground(col, QColor("#c0392b"))
            rows.append(item)

        add("本机 Studio 版本", str(rep.get("version") or "—"), not rep.get("project_newer"))
        if rep.get("project_version"):
            add("工程文件版本", str(rep["project_version"]), not rep.get("project_newer"))
        if rep.get("plate"):
            add("打印板", thermal.plate_label(str(rep["plate"])), bool(rep.get("plate_ok")))
        if rep.get("machine"):
            add("机型", str(rep["machine"]), bool(rep.get("machine_ok")))
        for warn in rep.get("warnings") or []:
            self._log(f"⚠ Studio 兼容性：{warn}", "warn")
        return rows

    def _render_verify(self, path, expected: dict, problems: list[str]) -> None:
        """保存后核对：表格里显示的值 vs 新文件里实际存的值。

        用户要的是「怎么确认参数真的进了切片软件」，所以这里给的是**逐键对照**，
        不是一句「保存成功」。Studio 那边还有一层「预设会不会盖回来」，
        所以声明槽位的结果也一并写进标题。
        """
        tree = getattr(self, "verify_tree", None)
        if tree is None:
            return
        tree.clear()
        try:
            back = threemf.ThreeMfProject.load(str(path))
            got = back.settings
        except Exception as exc:                     # 读不回来就说清楚，别假装核对过
            self.lbl_verify.setText(f"核对失败：新文件读不回来（{exc}）")
            self._log(f"⚠ 核对失败：{exc}", "err")
            return

        ok = bad = 0
        for key in sorted(expected):
            want = expected[key]
            have = got.get(key, "")
            same = _same_value(want, have) if key in got else False
            if same:
                ok += 1
            else:
                bad += 1
            item = QTreeWidgetItem([key, str(want), str(have) if key in got else "（文件里没有这个键）",
                                    "✅ 已写入" if same else "⚠ 不一致"])
            if not same:
                for col in range(4):
                    item.setForeground(col, QColor("#c0392b"))
            tree.addTopLevelItem(item)

        compat = self._compat_rows(got)
        for item in compat:
            tree.addTopLevelItem(item)

        if problems:
            self.lbl_verify.setText(
                f"写入 {len(expected)} 项：一致 {ok} 项，不一致 {bad} 项。"
                f"另外自检报了 {len(problems)} 处问题（见日志）。")
        else:
            self.lbl_verify.setText(
                f"写入 {len(expected)} 项：一致 {ok} 项，不一致 {bad} 项。"
                "文件里存的和你看到的一致；Studio 若仍显示旧值，多半是「预设差异槽」没声明，"
                "看日志里那行「已声明预设差异」。")
        self.detail_tabs.setCurrentWidget(self.verify_page)
        self._log(f"写入核对：{ok}/{len(expected)} 项一致" + (f"，{bad} 项不一致" if bad else ""),
                  "ok" if not bad else "err")

    def on_export_report(self) -> None:
        if not self.project or not self.result:
            QMessageBox.information(self, "先优化", "还没有可导出的报告。")
            return
        default = self._default_output().with_suffix(".md")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出优化报告", str(default), "Markdown (*.md);;文本 (*.txt)")
        if not path:
            return
        md_path = Path(path)
        try:
            md = report.build_markdown(
                str(self.project.path), self.det, self.result,
                output_path=str(self.ed_out.text().strip() or ""),
                model_profile=self.model_profile if self.chk_shape.isChecked() else None,
                custom_overlay=self._current_overlay())
            md_path.write_text(md, encoding="utf-8")
            csv_path = report.rows_to_csv(self.result.rows, md_path.with_suffix(".csv"))
        except Exception:
            self._log("导出报告出错：\n" + traceback.format_exc(), "err")
            QMessageBox.critical(self, "导出失败", "详情见日志。")
            return
        self._log(f"报告已导出：{md_path}", "ok")
        self._log(f"参数对照 CSV：{csv_path}", "ok")
        self.statusBar().showMessage("报告导出完成", 4000)

    def on_open_output_dir(self) -> None:
        target = self.last_output or Path(self.ed_out.text().strip() or "")
        if not str(target):
            return
        d = target.parent if target.name else target
        if d.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
        else:
            self._log(f"目录不存在：{d}", "warn")

    # ================================================================ 规则库页

    def _refresh_rules_controls(self) -> None:
        # 规则库可能被重新加载过，重新填一遍下拉（保留当前选择）
        for cmb, pairs in (
            (self.rp_printer, self.engine.printer_choices()),
            (self.rp_filament, self.engine.filament_choices()),
            (self.rp_mode, self.engine.mode_choices()),
        ):
            cur = cmb.currentData()
            cmb.blockSignals(True)
            cmb.clear()
            for key, label in pairs:
                cmb.addItem(label, key)
            i = cmb.findData(cur) if cur else 0
            cmb.setCurrentIndex(i if i >= 0 else 0)
            cmb.blockSignals(False)

    def _preview_profile(self):
        """规则库预览页用的合成形状夹具（不需要真模型）。"""
        key = self.rp_shape.currentData() or "none"
        if key == "none":
            return None
        from core.model_analysis import ModelProfile
        table = {
            "small": ModelProfile(objects=6, size_x=22, size_y=22, size_z=18,
                                  volume=3500, surface=3400, footprint=300,
                                  support_ratio=0.02, overhang_area=68, layers=91),
            "tall": ModelProfile(objects=1, size_x=60, size_y=60, size_z=190,
                                 volume=520000, surface=41000, footprint=2821,
                                 support_ratio=0.03, overhang_area=1230, layers=951),
            "plate": ModelProfile(objects=1, size_x=160, size_y=120, size_z=8,
                                  volume=153600, surface=42880, footprint=19200,
                                  support_ratio=0.0, overhang_area=0, layers=41),
            "support": ModelProfile(objects=1, size_x=60, size_y=20, size_z=120,
                                    volume=69600, surface=15680, footprint=580,
                                    support_ratio=0.26, overhang_area=4077, layers=601),
        }
        return table.get(key)

    def _render_rules_preview(self) -> None:
        try:
            res = self.engine.optimize(
                {}, printer_key=self.rp_printer.currentData() or "GENERIC",
                filament_key=self.rp_filament.currentData() or "GENERIC",
                nozzle=float(self.rp_nozzle.currentData() or 0.4),
                mode_key=self.rp_mode.currentData() or "balanced",
                filament_overlay=self._preview_overlay(),
                model_profile=self._preview_profile())
        except Exception:
            self._log("规则库预览计算失败：\n" + traceback.format_exc(), "err")
            return
        rows = res.rows
        self.rp_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            s = schema.PARAMS[row.key]
            if s.kind in (schema.ENUM, schema.BOOL) and s.choices:
                rng = " / ".join(str(c) for c in s.choices[:8])
            elif s.kind == schema.ARRAY_FLOAT:
                rng = f"{s.vmin:g} ~ {s.vmax:g}"
            elif s.kind in (schema.PCT, schema.PCT_NUM):
                rng = f"{s.vmin:g}% ~ {s.vmax:g}%"
            else:
                rng = f"{s.vmin:g} ~ {s.vmax:g} {s.unit}".strip()
            vals = [row.group_label, row.label, row.new_display, rng, row.reason or ""]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.rp_table.setItem(i, c, it)

    def _preview_overlay(self) -> dict | None:
        name = self.rp_custom.currentData()
        if not name:
            return None
        for p in self.custom_presets:
            if p.name == name:
                return bambu_profiles.to_overlay(p)
        return None

    def _sync_preview_custom_list(self) -> None:
        """把工作台同步到的自定义耗材复制一份到预览页下拉。"""
        cur = self.rp_custom.currentData()
        self.rp_custom.blockSignals(True)
        self.rp_custom.clear()
        self.rp_custom.addItem("（无自定义耗材）", None)
        for p in self.custom_presets:
            mark = "" if p.resolvable else "  ⚠"
            self.rp_custom.addItem(f"{p.name}{mark}", p.name)
            self.rp_custom.setItemData(self.rp_custom.count() - 1, p.display_detail,
                                       Qt.ItemDataRole.ToolTipRole)
        self.rp_custom.setEnabled(bool(self.custom_presets))
        i = self.rp_custom.findData(cur) if cur else 0
        self.rp_custom.setCurrentIndex(i if i >= 0 else 0)
        self.rp_custom.blockSignals(False)

    def on_reload_rules(self) -> None:
        try:
            new_engine = rules_engine.build_engine(self.rules_path)
        except Exception:
            self._log("规则库重新加载失败（JSON 语法或结构有问题）：\n" + traceback.format_exc(), "err")
            QMessageBox.critical(self, "规则库有误", "JSON 解析失败，详情见日志。修好后可再次点击重新加载。")
            return
        probs = new_engine.validate()
        self.engine = new_engine
        self._refresh_rules_controls()
        self._render_rules_preview()
        if probs:
            for p in probs:
                self._log("⚠ 规则库自检：" + p, "warn")
        else:
            self._log("规则库已重新加载，自检通过。", "ok")
        if self.project:
            self.run_optimize(silent=True)

    def _open_rules_dir(self) -> None:
        d = self.rules_path.parent
        if d.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
        else:
            self._log(f"目录不存在：{d}", "warn")

    # ================================================================ 杂项

    def _busy(self, on: bool) -> None:
        from PySide6.QtWidgets import QApplication
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
        self.btn_run.setEnabled(not on)

    def _log(self, text: str, level: str = "info") -> None:
        color = {"ok": COLOR_OK, "warn": COLOR_WARN, "err": COLOR_ERR}.get(level, "#374151")
        ts = datetime.now().strftime("%H:%M:%S")
        parts = []
        for line in str(text).splitlines() or [""]:
            parts.append(
                f'<span style="color:{COLOR_MUTED}">[{ts}]</span> '
                f'<span style="color:{color}">{html.escape(line)}</span>')
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertHtml("<br>".join(parts) + "<br>")
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.ensureCursorVisible()

    # 拖拽支持
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                if u.toLocalFile().lower().endswith((".3mf", ".bambu")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith((".3mf", ".bambu")):
                self.load_file(p)
                break
