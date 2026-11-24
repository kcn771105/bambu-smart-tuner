"""一次性脚本：把几何层 priority>=99 的「set 型占位规则」改成 no-op（mul 1.0）。

原因：占位规则用绝对 set 实现时，会把模式档/用户工程里已经确定的值翻掉
（实测 ironing_type top→no ironing、seam_position aligned_back→aligned、
enable_prime_tower True→False、only_one_wall_top False→True，共 10 个键）。
占位规则的本意是「这一层不表态，跟随上层」，所以改成 mul 1.0。
"""
import io
import json

PAIRS = [
    ("brim_type", "auto_brim"),
    ("only_one_wall_top", True),
    ("wall_sequence", "inner wall/outer wall"),
    ("top_one_wall_type", "top only"),
    ("seam_position", "aligned"),
    ("seam_slope_type", "none"),
    ("seam_slope_conditional", False),
    ("seam_slope_entire_loop", False),
    ("ironing_type", "no ironing"),
    ("enable_prime_tower", False),
]


def main() -> None:
    p = "core/geom_rules.py"
    s = io.open(p, encoding="utf-8").read()
    n = 0
    for key, val in PAIRS:
        old = f'_r("{key}", "always", {{"set": {json.dumps(val, ensure_ascii=False)}}},'
        idx = s.find(old)
        if idx < 0:
            print("MISS:", key)
            continue
        # 找到这一整行的结尾（reason 文本 + priority=99）
        end = s.find("\n", idx)
        line = s[idx:end]
        # 保留 reason 文本，把 set 换成 mul 1.0，并在 reason 后加「（不覆盖模式档）」
        new_line = line.replace(
            old,
            f'_r("{key}", "always", {{"mul": 1.0}},',
        )
        new_line = new_line.replace("priority=99)", "priority=99)  # 不覆盖上层")
        s = s[:idx] + new_line + s[end:]
        n += 1
    io.open(p, "w", encoding="utf-8").write(s)
    print("replaced", n, "of", len(PAIRS))


if __name__ == "__main__":
    main()
