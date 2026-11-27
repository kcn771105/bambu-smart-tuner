"""切片器核对（`core/slice_check.py`）的单元测试。

真切片那一步要本机装 Bambu Studio、还要跑一分钟，所以这里只测：

    * 从 gcode 里读回参数（用一段手写的最小 gcode 当夹具）；
    * 「文件里的值 vs gcode 里的值」这条对照逻辑（含容差与风扇字段映射）；
    * 给命令行切片用的副本做了哪些兼容处理，以及**打印参数一项没被改**；
    * 找不到 Studio 时的退化行为（不抛异常，只给一句人话）。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core import slice_check

# ---------------------------------------------------------------- 夹具

GCODE = """\
; HEADER_BLOCK_START
; BambuStudio 02.03.00.70
; model printing time: 1h 3m 48s; total estimated time: 1h 3m 50s
; total filament weight [g] : 18.42
; HEADER_BLOCK_END

; CONFIG_BLOCK_START
; layer_height = 0.23
; wall_loops = 3
; outer_wall_speed = 137
; inner_wall_speed = 174
; initial_layer_speed = 40
; fan_min_speed = 20
; fan_max_speed = 50
; support_speed = 150
; enable_support = 1
; bed_temperature = 78
; CONFIG_BLOCK_END

M140 S0
M140 S78
M104 S250
M106 P1 S0
;LAYER_CHANGE
;Z:0.23
; FEATURE: Outer wall
G1 X10 Y10 E1
;LAYER_CHANGE
;Z:0.46
; FEATURE: Support
G1 X20 Y20 E2
;LAYER_CHANGE
;Z:0.69
; FEATURE: Support
G1 X30 Y30 E3
"""


def _write_gcode(tmp_path: Path, text: str = GCODE) -> Path:
    path = tmp_path / "plate_1.gcode"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- probe_gcode


class TestProbeGcode:
    def test_reads_numbers_from_config_block(self, tmp_path):
        p = slice_check.probe_gcode(str(_write_gcode(tmp_path)))
        assert p.layer_height == pytest.approx(0.23)
        assert p.wall_loops == 3
        assert p.outer_wall_speed == 137
        assert p.inner_wall_speed == 174
        assert p.initial_layer_speed == 40
        assert p.fan_min_pct == 20
        assert p.fan_max_pct == 50
        assert p.support_speed == 150

    def test_reads_actual_bed_temp_from_m140(self, tmp_path):
        """M140 S0 是关加热，不能被当成板温；要取真正的非零值。"""
        p = slice_check.probe_gcode(str(_write_gcode(tmp_path)))
        assert p.bed_temp == 78
        assert p.bed_temp_header == 78

    def test_counts_layers_and_support_moves(self, tmp_path):
        p = slice_check.probe_gcode(str(_write_gcode(tmp_path)))
        assert p.layers == 3
        assert p.support_moves == 2
        assert p.enable_support is True
        assert p.time_text == "1h 3m 48s"
        assert p.filament_g == pytest.approx(18.42)

    def test_support_off_shows_zero_moves(self, tmp_path):
        text = GCODE.replace("; enable_support = 1", "; enable_support = 0").replace(
            "; FEATURE: Support", "; FEATURE: Sparse infill")
        p = slice_check.probe_gcode(str(_write_gcode(tmp_path, text)))
        assert p.enable_support is False
        assert p.support_moves == 0


# ---------------------------------------------------------------- 对照逻辑


class TestCompare:
    def _probe(self, tmp_path):
        return slice_check.probe_gcode(str(_write_gcode(tmp_path)))

    def test_all_match(self, tmp_path):
        want = {"layer_height": "0.23", "wall_loops": "3", "fan_min_speed": '["20"]',
                "fan_max_speed": '["50"]', "supertack_plate_temp": '["78"]',
                "enable_support": "1"}
        rows = slice_check._compare(want, self._probe(tmp_path))
        assert rows and all(r[3] for r in rows), rows

    def test_array_text_is_unwrapped(self, tmp_path):
        """工程里的风扇/板温是 JSON 数组文本，要和 gcode 的标量对上。"""
        rows = slice_check._compare({"fan_max_speed": '["50"]'}, self._probe(tmp_path))
        assert rows[0][1] == "50" and rows[0][3] is True

    def test_fan_fields_map_to_probe_attributes(self, tmp_path):
        """风扇在 Probe 上叫 fan_min_pct，对照表必须走映射，否则永远是 0。"""
        rows = dict((k, (w, g, ok)) for k, w, g, ok in
                    slice_check._compare({"fan_min_speed": "20", "fan_max_speed": "50"},
                                         self._probe(tmp_path)))
        assert rows["fan_min_speed"][1] == "20"
        assert rows["fan_max_speed"][1] == "50"

    def test_mismatch_is_flagged(self, tmp_path):
        rows = slice_check._compare({"outer_wall_speed": "200"}, self._probe(tmp_path))
        assert rows[0][3] is False
        assert rows[0][2] == "137"

    def test_tolerance_follows_the_key(self, tmp_path):
        """层高按 0.005 卡（0.2 和 0.23 是两回事），速度/温度允许半个单位。"""
        p = self._probe(tmp_path)
        assert slice_check._compare({"layer_height": "0.23"}, p)[0][3] is True
        assert slice_check._compare({"layer_height": "0.2"}, p)[0][3] is False
        assert slice_check._compare({"outer_wall_speed": "137.4"}, p)[0][3] is True
        assert slice_check._compare({"outer_wall_speed": "140"}, p)[0][3] is False

    def test_support_row_carries_move_count(self, tmp_path):
        rows = slice_check._compare({"enable_support": "1"}, self._probe(tmp_path))
        assert "条支撑路径" in rows[0][2]


# ---------------------------------------------------------------- 副本准备


def _make_3mf(tmp_path: Path, cfg: dict) -> Path:
    path = tmp_path / "proj.3mf"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Metadata/project_settings.config",
                   json.dumps(cfg, ensure_ascii=False))
        z.writestr("3D/3dmodel.model", "<model/>")
    return path


class TestParseConfig:
    """gcode 里的 CONFIG_BLOCK 是切片器**实际采用**的整套参数。"""

    def test_reads_config_block(self, tmp_path):
        cfg = slice_check.parse_config(str(_write_gcode(tmp_path)))
        assert cfg["layer_height"] == "0.23"
        assert cfg["enable_support"] == "1"

    def test_array_values_kept_verbatim(self, tmp_path):
        text = GCODE.replace("; wall_loops = 3", '; wall_loops = ["3", "3"]')
        cfg = slice_check.parse_config(str(_write_gcode(tmp_path, text)))
        assert cfg["wall_loops"] == '["3", "3"]'

    def test_no_config_block_falls_back_to_whole_file(self, tmp_path):
        text = "G1 X0 Y0" + chr(10) + "; layer_height = 0.2" + chr(10)
        cfg = slice_check.parse_config(str(_write_gcode(tmp_path, text)))
        assert cfg["layer_height"] == "0.2"


class TestCompareAll:
    """逐键核对的三种结论：生效 / 被切片器改写 / 不参与切片。"""

    def test_ok_overridden_absent(self):
        cfg = {"layer_height": "0.23", "wall_loops": "2"}
        rows = slice_check.compare_all(
            {"layer_height": "0.23", "wall_loops": '["3"]', "seam_position": "aligned"}, cfg)
        verdict = {row[0]: row[3] for row in rows}
        assert verdict["layer_height"] == "ok"
        assert verdict["wall_loops"] == "overridden"      # 写 3，切片器用了 2
        assert verdict["seam_position"] == "absent"       # 这类键不进 gcode 配置

    def test_json_array_text_compares_by_first_slot(self):
        rows = slice_check.compare_all({"outer_wall_speed": '["137", "137", "137"]'},
                                       {"outer_wall_speed": "137"})
        assert rows[0][3] == "ok"

    def test_string_enum_compare(self):
        rows = slice_check.compare_all({"brim_type": "outer_only"},
                                       {"brim_type": "outer_only"})
        assert rows[0][3] == "ok"
        rows = slice_check.compare_all({"brim_type": "outer_only"},
                                       {"brim_type": "auto_brim"})
        assert rows[0][3] == "overridden"


class TestHeadlessCopy:
    def test_zero_filament_index_becomes_one(self, tmp_path):
        src = _make_3mf(tmp_path, {"wall_filament": "0", "sparse_infill_filament": "0",
                                   "solid_infill_filament": "2",
                                   "outer_wall_speed": "137", "layer_height": "0.23"})
        dst = tmp_path / "copy.3mf"
        notes = slice_check._headless_copy(str(src), str(dst))
        cfg = json.loads(zipfile.ZipFile(dst).read("Metadata/project_settings.config"))
        assert cfg["wall_filament"] == "1"
        assert cfg["sparse_infill_filament"] == "1"
        assert cfg["solid_infill_filament"] == "2", "已经是合法序号的不许动"
        assert any("耗材序号" in n for n in notes)

    def test_print_params_are_untouched(self, tmp_path):
        """兼容处理只碰 gcode 模板与耗材序号，打印参数必须原样。"""
        original = {"wall_filament": "0", "outer_wall_speed": "137",
                    "layer_height": "0.23", "fan_max_speed": '["50"]',
                    "enable_support": "1", "supertack_plate_temp": '["78"]',
                    "machine_start_gcode": "G28\nM104 S{nozzle_temperature}"}
        src = _make_3mf(tmp_path, original)
        dst = tmp_path / "copy.3mf"
        slice_check._headless_copy(str(src), str(dst))
        cfg = json.loads(zipfile.ZipFile(dst).read("Metadata/project_settings.config"))
        for key in ("outer_wall_speed", "layer_height", "fan_max_speed",
                    "enable_support", "supertack_plate_temp"):
            assert cfg[key] == original[key]

    def test_model_file_is_copied_verbatim(self, tmp_path):
        src = _make_3mf(tmp_path, {"wall_filament": "0"})
        dst = tmp_path / "copy.3mf"
        slice_check._headless_copy(str(src), str(dst))
        assert zipfile.ZipFile(dst).read("3D/3dmodel.model") == b"<model/>"


# ---------------------------------------------------------------- 找不到 Studio


class TestNoStudio:
    def test_missing_studio_returns_warning_not_exception(self, tmp_path, monkeypatch):
        monkeypatch.setattr(slice_check, "find_studio", lambda extra="": "")
        res = slice_check.run_slice_check(str(_make_3mf(tmp_path, {})), {})
        assert res.ok is False
        assert res.probe is None
        assert any("bambu-studio.exe" in w for w in res.warnings)

    def test_find_studio_accepts_explicit_path(self, tmp_path):
        fake = tmp_path / "bambu-studio.exe"
        fake.write_text("")
        assert slice_check.find_studio(str(fake)) == str(fake)
