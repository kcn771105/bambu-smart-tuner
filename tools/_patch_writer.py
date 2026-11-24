import io

# ============ threemf.py：写入加固（值一律字符串化 + 标成自定义工艺档 + 自检） ============
p = "core/threemf.py"
s = io.open(p, encoding="utf-8").read()

# 1) 新增：把 settings 规范成 Bambu Studio 认识的形态（值全部字符串/字符串数组）
anchor = "    def save_as(self, target: str | os.PathLike, *, strip_stale_slice: bool = True) -> Path:"
helper = '''    # ---------------------------------------------------------------- 写入形态
    def studio_settings(self) -> dict:
        """规范成 Bambu Studio 认识的形态。

        Bambu 的 project_settings.config 里，值一律是字符串，数组也是字符串数组
        （"0.2" / ["200","500","500"]）。引擎新增的键如果写成数字/浮点，Studio 的
        解析器可能整份拒绝 —— 表现出来就是「文件打开了但参数没变」。
        所以写盘前统一 stringify，避免这类静默失效。
        """
        out: dict = {}
        for key, val in self._typed_settings().items():
            if isinstance(val, list):
                out[key] = [self._stringify(x) for x in val]
            else:
                out[key] = self._stringify(val)
        return out

    @staticmethod
    def _stringify(val) -> str:
        if isinstance(val, str):
            return val
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, float):
            if val == int(val):
                return str(int(val))
            return f"{val:g}"
        return str(val)

    def mark_custom_process(self, suffix: str = " - Smart Tuner") -> str:
        """把工程标成「自定义工艺档」，让 Studio 必定采用文件里的参数。

        Studio 打开 3mf 时会按 print_settings_id 去盘上找同名预设；名字撞上系统预设时，
        容易变成「显示的是预设、看不见文件里的改动」。把名字改成一个盘上不存在的名字，
        Studio 就只能把文件里的值当成一份自定义档读进来。
        只改工艺档名，不动耗材/机型的 id（那两个决定喷头与 AMS 映射，改了会掉料）。
        """
        old = str(self.settings.get("print_settings_id") or "")
        if not old or old.endswith(suffix):
            return old
        new = old + suffix
        self.settings["print_settings_id"] = new
        if "default_print_profile" in self.settings:
            self.settings["default_print_profile"] = new
        return new

'''
assert anchor in s
s = s.replace(anchor, helper + anchor, 1)

# 2) save_as 用 studio_settings()，并加预设目录闸门
s = s.replace(
    "        payload = json.dumps(self._typed_settings(), ensure_ascii=False, indent=4).encode(\"utf-8\")",
    "        from . import safety\n"
    "        safety.guard_target(dst)\n"
    "        payload = json.dumps(self.studio_settings(), ensure_ascii=False,\n"
    "                             indent=4).encode(\"utf-8\")", 1)

io.open(p, "w", encoding="utf-8").write(s)
print("threemf：studio_settings / mark_custom_process / 预设闸门")
