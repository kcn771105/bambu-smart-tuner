import sys

sys.path.insert(0, ".")
from core import schema

raw = '["200", "500", "500"]'
print("slot_texts:", schema._slot_texts(raw))
sp = schema.PARAMS["outer_wall_speed"]
print("outer_wall_speed spec:", sp)
print("format →", schema.format_value(sp, 162.0, raw))
print("sparse spec:", schema.PARAMS["sparse_infill_speed"])
print("format sparse →", schema.format_value(schema.PARAMS["sparse_infill_speed"], 167.0,
                                             '["270", "600", "600"]'))
schema.set_variant_slots(3)
print("after set_variant_slots →", schema.format_value(sp, 162.0, raw))
