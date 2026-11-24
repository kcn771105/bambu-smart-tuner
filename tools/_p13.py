import io

p = "ui/main_window.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace('getattr(self, "last_result", None) is not None',
              'self.result is not None')
s = s.replace('getattr(self.last_result, "flow_limit", None)',
              'getattr(self.result, "flow_limit", None)')
io.open(p, "w", encoding="utf-8").write(s)
print("fixed:", s.count("self.result is not None"),
      s.count("getattr(self.result"))
