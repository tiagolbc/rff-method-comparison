"""Focused non-MATLAB regression checks for RFF Method Comparison v25."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py"
spec = importlib.util.spec_from_file_location("rff_v25", MAIN)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
assert spec.loader is not None
spec.loader.exec_module(module)


def synthetic_long() -> pd.DataFrame:
    rows = []
    traces = {
        1: np.asarray([0.0, -0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, -0.8, -1.0]),
        2: np.asarray([0.0, -0.05, -0.15, -0.25, -0.38, -0.52, -0.63, -0.76, -0.90, -1.15]),
        3: np.asarray([0.0, -0.12, -0.18, -0.28, -0.42, -0.49, -0.66, -0.72, -0.84, -0.95]),
    }
    for rep, values in traces.items():
        for cycle, value in enumerate(values, 1):
            rows.append({
                "Method": "TEST_METHOD", "Subject": "S01", "Filename": "test.wav",
                "Filepath": "test.wav", "Token": "afa", "Rep": rep, "Side": "OFF",
                "Cycle": cycle, "RFF_ST": value, "ValidSide": True,
                "AgeGroup": "18-39", "Sex": "Female", "MetadataSource": "test",
                "NormativeEligible": True, "NormativeStatus": "eligible",
            })
    return pd.DataFrame(rows)


def main() -> None:
    assert "v25" in module.SCRIPT_LABEL.lower()
    cfg = module.RFFConfig(calculate_sti=True)
    assert cfg.sti_min_traces == 2
    normalized = module._normalize_rff_trace_for_sti(np.arange(10, dtype=float), 1000, 50)
    assert normalized is not None and normalized.shape == (50,)
    assert abs(module._sti_bias_correction_factor(2) - np.sqrt(np.pi / 2.0)) < 1e-12
    subject, summary, profiles, audit = module.build_rff_sti_tables(synthetic_long(), cfg)
    assert len(subject) == 1 and subject.iloc[0]["STIStatus"] == "calculated"
    assert int(subject.iloc[0]["NTracesUsed"]) == 3
    assert np.isfinite(subject.iloc[0]["STI_bias_corrected"])
    assert len(summary) == 1 and int(summary.iloc[0]["SubjectsCalculable"]) == 1
    assert len(profiles) == 50
    assert len(audit) == 3 and set(audit["TraceStatus"]) == {"included"}
    cfg.calculate_sti = False
    assert cfg.calculate_sti is False
    print("v25 regression checks passed")


if __name__ == "__main__":
    main()
