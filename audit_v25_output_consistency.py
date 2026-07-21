"""Audit v25 output consistency between Cepstral RFF and final landmarks.

Usage:
    python audit_v25_output_consistency.py <output_folder>

Creates `rff_v25_final_selection_consistency_audit.csv` in the output folder
and exits non-zero if any natively valid Cepstral side is inconsistent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python audit_v25_output_consistency.py <output_folder>")
        return 2
    out = Path(sys.argv[1]).resolve()
    wide_path = out / "rff_all_traces_wide.csv"
    lm_path = out / "rff_final_landmarks_long.csv"
    if not wide_path.exists() or not lm_path.exists():
        print("Required files not found in output folder.")
        return 2

    wide = pd.read_csv(wide_path)
    lm = pd.read_csv(lm_path)
    wide = wide.loc[wide["Method"].astype(str).eq("RFF_CEPSTRAL")].copy()
    lm = lm.loc[lm["Method"].astype(str).eq("RFF_CEPSTRAL")].copy()
    rows = []
    for _, r in wide.iterrows():
        for side in ("OFF", "ON"):
            valid = bool(r["OffValid" if side == "OFF" else "OnValid"])
            if not valid:
                continue
            g = lm.loc[
                lm["Subject"].astype(str).eq(str(r["Subject"]))
                & lm["Token"].astype(str).str.lower().eq(str(r["Token"]).lower())
                & pd.to_numeric(lm["Rep"], errors="coerce").sub(float(r["Rep"])).abs().lt(1e-8)
                & lm["Side"].astype(str).str.upper().eq(side)
            ].sort_values("LandmarkIndex")
            times = pd.to_numeric(g["Time_s"], errors="coerce").dropna().to_numpy(float)
            error = np.nan
            consistent = False
            reason = ""
            if times.size != 11:
                reason = f"expected_11_landmarks_found_{times.size}"
            else:
                periods = np.diff(times)
                if periods.size != 10 or not np.all(np.isfinite(periods)) or np.any(periods <= 0):
                    reason = "invalid_periods"
                else:
                    freqs = 1.0 / periods
                    base = freqs[0] if side == "OFF" else freqs[-1]
                    recalculated = 12.0 * np.log2(freqs / base)
                    stored = pd.to_numeric(r[[f"{side}{i}" for i in range(1, 11)]], errors="coerce").to_numpy(float)
                    error = float(np.nanmax(np.abs(recalculated - stored)))
                    consistent = bool(np.isfinite(error) and error <= 1e-6)
                    if not consistent:
                        reason = "rff_landmark_mismatch"
            rows.append({
                "Subject": r["Subject"], "Token": r["Token"], "Rep": r["Rep"],
                "Side": side, "NLandmarks": int(times.size),
                "MaxAbsoluteError_ST": error, "Consistent": consistent,
                "Reason": reason,
            })

    audit = pd.DataFrame(rows)
    audit_path = out / "rff_v25_final_selection_consistency_audit.csv"
    audit.to_csv(audit_path, index=False, encoding="utf-8-sig")
    bad = audit.loc[~audit["Consistent"]] if not audit.empty else audit
    print(f"Audited {len(audit)} natively valid Cepstral sides.")
    print(f"Inconsistent sides: {len(bad)}")
    print(f"Saved: {audit_path}")
    if len(bad):
        print(bad.to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
