import io

p = "tools/smoke_ui_nozzle.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("from ui.main_window import MainWindow  # noqa: E402",
              "from core import rules_engine  # noqa: E402\nfrom ui.main_window import MainWindow  # noqa: E402")
s = s.replace("    win = MainWindow()",
              "    engine = rules_engine.build_engine()\n"
              "    win = MainWindow(engine, rules_path=rules_engine.default_rules_path())")
io.open(p, "w", encoding="utf-8").write(s)
print("fixed ctor")
