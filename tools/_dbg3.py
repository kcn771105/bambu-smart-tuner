"""给 hotend 分槽、schema 整槽写入补测试，并跑通真实工程。"""
import io
import json
import sys

sys.path.insert(0, ".")

from core import hotend, schema

PROJECT = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"

from core.threemf import ThreeMfProject

prj = ThreeMfProject.load(PROJECT)
print("slot_count:", hotend.slot_count(prj.settings))

schema.set_variant_slots(hotend.slot_count(prj.settings))
sp = schema.PARAMS["outer_wall_speed"]
raw = prj.settings["outer_wall_speed"]
print("raw:", raw)
print("写回:", schema.format_value(sp, 150.0, raw))

# 单槽工程（没有 variant 列表）不应被整槽填充
schema.set_variant_slots(0)
print("单槽工程:", schema.format_value(sp, 150.0, raw))
