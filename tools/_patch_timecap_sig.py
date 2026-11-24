import io

p = "core/rules_engine.py"
s = io.open(p, encoding="utf-8").read()

old_sig = """    def _enforce_time_cap(self, values, reasons, old_values, warnings, notes,
                          cap_pct: float) -> None:"""
new_sig = """    def _enforce_time_cap(self, values, reasons, old_values, warnings, notes,
                          cap_pct: float, mode_for_budget: str = "balanced") -> None:"""
assert old_sig in s, "signature not found"
s = s.replace(old_sig, new_sig)

old_call = """            self._enforce_time_cap(values, reasons, old_for_estimate, warnings,
                                   notes, float(time_cap_pct))"""
new_call = """            self._enforce_time_cap(values, reasons, old_for_estimate, warnings,
                                   notes, float(time_cap_pct), mode_for_budget=mode_key)"""
assert old_call in s, "call site not found"
s = s.replace(old_call, new_call)

io.open(p, "w", encoding="utf-8").write(s)
print("patched")
