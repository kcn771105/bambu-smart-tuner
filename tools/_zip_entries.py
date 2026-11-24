"""3mf 里到底有哪些条目，model_settings.config 里有不有工艺参数。"""
import sys
import zipfile
from pathlib import Path

SRC = Path(r"F:\deep seek\鱼缸温度计支架\鱼缸温度计支架.3mf")
OUT = Path(r"F:\deep seek\bambu_smart_tuner\dist\_roundtrip.3mf")

for p in (SRC, OUT):
    print("=" * 20, p.name)
    with zipfile.ZipFile(p) as z:
        for info in z.infolist():
            print(f"  {info.filename:52} {info.file_size:8}  comp={info.compress_type}")
        md = [n for n in z.namelist() if n.endswith("model_settings.config")]
        if md:
            txt = z.read(md[0]).decode("utf-8")
            print(f"\n  --- {md[0]} 前 1600 字符 ---")
            print(txt[:1600])
    print()
