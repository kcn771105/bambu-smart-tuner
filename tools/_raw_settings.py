import zipfile

P = r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf"
KEYS = ("outer_wall_speed", "layer_height", "sparse_infill_density",
        "nozzle_diameter", "printable_area", "wall_loops")

with zipfile.ZipFile(P) as z:
    name = [n for n in z.namelist() if n.endswith("project_settings.config")][0]
    raw = z.read(name).decode("utf-8")

print("settings 文件：", name, len(raw), "chars")
print("前 300 字符：", repr(raw[:300]))
print()
for k in KEYS:
    i = raw.find('"' + k + '"')
    print(repr(raw[i:i + 140]))
    print()
