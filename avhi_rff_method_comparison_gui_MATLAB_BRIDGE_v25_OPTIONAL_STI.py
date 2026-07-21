# -*- coding: utf-8 -*-
"""
RFF Method Comparison GUI
==============================

Purpose
-------
Run the same manually marked /f/ ROIs through multiple Relative Fundamental
Frequency (RFF) extraction variants so the AVHI corpus can be compared against
Vojtech/Buckley normative threshold values for OFF10 and ON1.

Implemented methods
-------------------
1) AVHI_PRAAT_STRICT
   ROI-guided Praat/Parselmouth PointProcess extraction with AVHI/aRFF-B-like
   rejection rules. This method runs directly in Python.

2) RFF_CEPSTRAL
   Robust cepstral-assisted classical RFF. A multi-candidate cepstral/AC pitch
   path controls a narrow-band analytic-phase cycle detector. The final output
   remains the classical 10-cycle RFF; a separate framewise transition proxy is
   stored in the complete CSV debug payload and is explicitly labelled
   exploratory/non-RFF.

3) RFF_MB_ROI_MATLAB
   Native RFF_auto_MB MATLAB/Praat path. Each ROI is isolated as one VCV;
   FricStart anchors OFF and FricEnd anchors ON. Original sliding-window
   voting, rejection thresholds, and RFF equations are retained.

4) RFF_AP_ROI_MATLAB
   Native aRFF-AP MATLAB path. Automatic fricative localization is replaced
   by the manually verified ROI; the unmodified original RFFoutput.m is the
   authority for values and rejection codes.

Legacy Python approximations of MB/AP remain in the file for development
comparison, but the main GUI run uses the MATLAB bridges for MB and aRFF-AP.

Normative reference used in output
----------------------------------
OFF10 lower normative thresholds by age group:
    18-39: -2.73 ST; 40-64: -3.33 ST; 65+: -3.58 ST
ON1 lower normative thresholds by sex:
    Male: 0.89 ST; Female: -0.03 ST
Values below these thresholds are flagged as below the normative threshold.

Outputs
-------
- rff_roi_marks.csv / .xlsx
- rff_all_cycles_long.csv
- rff_all_traces_wide.csv / .xlsx
- rff_debug.csv
- rff_subject_method_summary.csv
- rff_method_normative_ranking.csv
- rff_final_landmarks_long.csv
- rff_cycle_qc.csv
- rff_manual_review_queue.csv
- rff_exclusion_log.csv
- rff_cepstral_transition_index_long.csv (exploratory cTFI; not classical RFF)
- rff_sti_subject_method_side.csv (optional bias-corrected RFF STI)
- rff_sti_method_summary.csv (optional STI method summary)
- rff_sti_profiles_long.csv (optional 50-point STI profiles)
- rff_sti_trace_audit.csv (optional trace-level STI audit)

Dependencies
------------
Required: numpy, pandas, soundfile, scipy, matplotlib
Recommended: praat-parselmouth, openpyxl, sounddevice

Run
---
python avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py

Author note
-----------
This script is intentionally self-contained so it can be placed outside the
AVHI package and run against a corpus folder. It does not modify the AVHI code.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import queue
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import soundfile as sf

try:
    import scipy.signal as sp_signal
    from scipy.interpolate import CubicSpline
except Exception as exc:  # pragma: no cover
    raise RuntimeError("This script requires scipy. Install with: pip install scipy") from exc

import matplotlib
try:
    # Use TkAgg for the interactive GUI. In headless test environments this may fail,
    # so fall back to Agg while keeping the script importable.
    matplotlib.use("TkAgg")
except Exception:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Optional dependencies
try:
    import parselmouth
    from parselmouth.praat import call as praat_call
except Exception:  # pragma: no cover
    parselmouth = None
    praat_call = None

try:
    import sounddevice as sounddevice
except Exception:  # pragma: no cover
    sounddevice = None


# =============================================================================
# User/project defaults
# =============================================================================

DEFAULT_ROOT = r"I:\Fonoaudiologia\Post Doc\PPGMDS 2026\AVHI - selection analysis pos-normative"
DEFAULT_OUTPUT = r"I:\Fonoaudiologia\Post Doc\PPGMDS 2026\RFF Methods Comparison"
DEFAULT_PRAAT_EXE = r"C:\Praat\Praat.exe" if pathlib.Path(r"C:\Praat\Praat.exe").exists() else ""
DEFAULT_MATLAB_EXE = r"C:\Program Files\MATLAB\R2026a\bin\matlab.exe" if pathlib.Path(r"C:\Program Files\MATLAB\R2026a\bin\matlab.exe").exists() else "matlab"
TOKENS = ("afa", "ifi", "ufu")
AUDIO_EXTS = {".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg"}

BG_COLOR = "#CDCDC1"
ACCENT = "#2bb7a8"  # AVHI aqua/green family
DARK_TEXT = "#202020"
FONT = ("Calibri", 11)

# Vojtech/Buckley normative threshold values (two SD below typical-speaker mean)
VOJTECH_OFF10_THRESH_BY_AGE = {
    "18-39": -2.73,
    "40-64": -3.33,
    "65+": -3.58,
}
VOJTECH_ON1_THRESH_BY_SEX = {
    "Male": 0.89,
    "Female": -0.03,
}


# =============================================================================
# Participant metadata helpers
# =============================================================================

def _norm_key(text: Any) -> str:
    return str(text).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _normalize_sex_label(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"male", "m", "masculino", "masc"} or text.startswith("masc"):
        return "Male"
    if text in {"female", "f", "feminino", "fem"} or text.startswith("fem"):
        return "Female"
    return ""


def _age_to_group(value: Any) -> str:
    age = safe_float(value, np.nan)
    if not np.isfinite(age):
        return ""
    if age < 40:
        return "18-39"
    if age < 65:
        return "40-64"
    return "65+"


def _subject_from_metadata_row(row: Mapping[str, Any], columns: Sequence[str]) -> str:
    # Direct subject columns first.
    for c in columns:
        if _norm_key(c) in {"subject", "id", "participant", "patient", "speaker"}:
            val = str(row.get(c, "")).strip()
            if val and val.lower() != "nan":
                return subject_base_id(val)

    # Brazilian AVHI descriptive table pattern: anonymous_code=S01GC and group_code=GC.
    anon_col = next((c for c in columns if _norm_key(c) in {"anonymouscode", "anoncode", "codigoanonimo", "códigoanonimizado"}), None)
    group_col = next((c for c in columns if _norm_key(c) in {"groupcode", "group", "grupo", "grupocode"}), None)
    if anon_col:
        anon = str(row.get(anon_col, "")).strip()
        group = str(row.get(group_col, "")).strip().upper() if group_col else ""
        m = re.search(r"(?i)S?0*(\d+)\s*([A-Z]{1,3})?", anon)
        if m:
            number = int(m.group(1))
            suffix = (m.group(2) or group or "").upper()
            if suffix in {"GC", "GE"}:
                return f"{suffix}{number:02d}"
    return ""


def _read_any_metadata_file(path: str | pathlib.Path) -> List[pd.DataFrame]:
    p = pathlib.Path(path)
    frames: List[pd.DataFrame] = []
    if not p.exists() or not p.is_file():
        return frames
    try:
        if p.suffix.lower() in {".xlsx", ".xls"}:
            xls = pd.ExcelFile(p)
            preferred = [s for s in xls.sheet_names if s.lower() in {"participants_text", "participants", "metadata", "dados"}]
            sheet_order = preferred + [s for s in xls.sheet_names if s not in preferred]
            for sheet in sheet_order:
                try:
                    df = pd.read_excel(p, sheet_name=sheet)
                    if df is not None and not df.empty:
                        frames.append(df)
                except Exception:
                    continue
        else:
            frames.append(pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig"))
    except Exception:
        return frames
    return frames


def load_participant_metadata_file(path: str | pathlib.Path) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    """Load age/sex metadata from either a simple CSV/XLSX or the study_descriptive_data.xlsx workbook.

    The returned dictionary is keyed by normalized subject IDs such as GC01 or GE02.
    It supports:
      - Subject + AgeGroup + Sex columns;
      - Subject + age + sex columns;
      - anonymous_code/group_code + age_at_collection + Portuguese sex labels.
    """
    messages: List[str] = []
    meta: Dict[str, Dict[str, str]] = {}
    frames = _read_any_metadata_file(path)
    if not frames:
        return meta, [f"No readable metadata table found in {path}"]

    for df in frames:
        if df is None or df.empty:
            continue
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        cols = list(df.columns)
        norm_to_col = {_norm_key(c): c for c in cols}

        age_group_col = next((norm_to_col[k] for k in ("agegroup", "agegroupreal", "age_group", "age group") if k in norm_to_col), None)
        age_col = next((norm_to_col[k] for k in ("ageatcollection", "age", "idade", "idadecoleta", "ageyears", "age_years") if k in norm_to_col), None)
        sex_col = next((norm_to_col[k] for k in ("sex", "sexo", "gender", "genero", "gênero") if k in norm_to_col), None)

        if not (age_group_col or age_col or sex_col):
            continue

        loaded_here = 0
        for _, row in df.iterrows():
            subj = _subject_from_metadata_row(row.to_dict(), cols)
            if not subj:
                continue
            item: Dict[str, str] = {}
            if age_group_col:
                ag = str(row.get(age_group_col, "")).strip()
                if ag in VOJTECH_OFF10_THRESH_BY_AGE:
                    item["AgeGroup"] = ag
            if "AgeGroup" not in item and age_col:
                ag = _age_to_group(row.get(age_col))
                if ag:
                    item["AgeGroup"] = ag
            if sex_col:
                sx = _normalize_sex_label(row.get(sex_col))
                if sx:
                    item["Sex"] = sx
            if item:
                meta[subj] = {**meta.get(subj, {}), **item}
                loaded_here += 1
        if loaded_here:
            messages.append(f"{pathlib.Path(path).name}: loaded {loaded_here} metadata rows from one sheet/table")

    if not meta:
        messages.append(f"{pathlib.Path(path).name}: no usable Subject/Age/Sex metadata rows were found")
    return meta, messages


def find_metadata_candidates(root: str | pathlib.Path, out: str | pathlib.Path) -> List[pathlib.Path]:
    starts = []
    for p in (root, out):
        try:
            pp = pathlib.Path(p)
            starts.extend([pp, pp.parent])
        except Exception:
            pass
    seen = set()
    candidates: List[pathlib.Path] = []
    patterns = ("*descriptive*.xlsx", "*metadata*.xlsx", "*participant*.xlsx", "*participants*.xlsx",
                "*descriptive*.csv", "*metadata*.csv", "*participant*.csv", "*participants*.csv")
    for start in starts:
        if not start or not start.exists():
            continue
        for pat in patterns:
            for hit in start.glob(pat):
                key = str(hit.resolve()).lower()
                if key not in seen and hit.is_file():
                    seen.add(key)
                    candidates.append(hit)
    return candidates


def auto_load_participant_metadata(root: str | pathlib.Path, out: str | pathlib.Path) -> Tuple[Dict[str, Dict[str, str]], str]:
    for cand in find_metadata_candidates(root, out):
        meta, messages = load_participant_metadata_file(cand)
        if meta:
            return meta, f"Auto-loaded participant metadata from {cand} ({len(meta)} subjects). " + " | ".join(messages[:2])
    return {}, "No participant metadata file was auto-detected. Normative ranking will be withheld unless metadata is loaded or GUI defaults are explicitly authorized."


SCRIPT_VERSION = "2026-07-17_MATLAB_ROI_BRIDGE_v25_OPTIONAL_STI"
SCRIPT_LABEL = "v25: v24 RFF numerical methods frozen; optional bias-corrected RFF spatiotemporal-index post-processing"


# =============================================================================
# Configuration and result containers
# =============================================================================

@dataclass
class RFFConfig:
    script_version: str = SCRIPT_VERSION
    f0_floor: float = 75.0
    f0_ceiling: float = 500.0
    praat_min_pitch: float = 75.0
    praat_max_pitch: float = 500.0
    praat_path: str = ""
    use_bandpass: bool = False
    near_off_s: float = 0.35
    near_on_s: float = 0.35
    window_vote_s: float = 0.010
    vote_off_min: float = 0.50
    vote_on_min: float = 0.30
    var_threshold_s2: float = 2.9e-6
    percentile: float = 65.0
    outlier_mult: float = 1.5
    steady_off_abs_st: float = 0.8
    steady_on_abs_st: float = 0.8
    subharmonic_low: float = 1.75
    subharmonic_high: float = 2.25
    # Cepstral v22 settings. These parameters are used only by RFF_CEPSTRAL.
    # cep_frame_s remains as a compatibility/nominal value in saved configs;
    # the robust tracker uses the multi-resolution frame durations below.
    cep_frame_s: float = 0.040
    cep_hop_s: float = 0.005
    cep_prom_min: float = 0.030  # legacy field; not used as a raw-amplitude gate in v17
    cep_frame_short_s: float = 0.030
    cep_frame_medium_s: float = 0.045
    cep_frame_long_s: float = 0.060
    cep_max_candidates: int = 6
    cep_min_confidence: float = 0.24
    cep_min_ac_strength: float = 0.18
    cep_max_interp_gap_frames: int = 2
    cep_phase_band_low_ratio: float = 0.58
    cep_phase_band_high_ratio: float = 1.55
    cep_phase_min_envelope_ratio: float = 0.06
    cep_max_period_log2_error: float = 0.42
    cep_max_adjacent_period_ratio: float = 1.85
    cep_max_period_cv: float = 0.42
    cep_max_boundary_period_ratio: float = 1.60
    # v21 retains the v19 multi-hypothesis periodicity confirmation. Classical RFF is withheld
    # when independent AC/YIN evidence supports another harmonic family or the
    # selected phase-cycle periodicity is genuinely ambiguous. The cycles are
    # never silently rewritten and cTFI remains available.
    cep_independent_autocorr_min: float = 0.40
    cep_independent_pitch_max_deviation_st: float = 4.5
    cep_periodicity_window_s: float = 0.18
    cep_periodicity_min_candidate_score: float = 0.38
    cep_periodicity_octave_competitor_ratio: float = 0.78
    cep_periodicity_strong_margin: float = 0.08
    cep_yin_candidate_threshold: float = 0.30

    # v21 retains the v19 boundary-cycle validation. A large OFF10/ON1 is not rejected merely
    # for its sign or magnitude. Rejection requires a large boundary-period
    # deviation plus independent evidence such as local-path disagreement,
    # competing periodicity, peak/trough disagreement, or an extra same-phase
    # extremum inside the purported boundary cycle.
    cep_boundary_warn_ratio: float = 1.25
    cep_boundary_hard_ratio: float = 1.48
    cep_boundary_track_warn_st: float = 3.0
    cep_boundary_track_hard_st: float = 5.0
    cep_boundary_pair_warn_st: float = 3.0
    cep_boundary_independent_warn_st: float = 3.0
    cep_boundary_min_track_confidence: float = 0.30
    cep_boundary_min_envelope_ratio: float = 0.35
    cep_boundary_extremum_prominence_ratio: float = 0.08

    # v21 all-cycle trajectory controls. These gates
    # examine every one of the ten classical RFF periods. They do not impose a
    # desired RFF sign or normative curve and never merge/split cycles silently.
    cep_window_max_shifts_per_pool: int = 10
    cep_cycle_track_warn_st: float = 3.0
    cep_cycle_track_hard_st: float = 5.0
    cep_cycle_min_track_confidence: float = 0.30
    cep_cycle_independent_warn_st: float = 3.5
    cep_cycle_independent_hard_st: float = 5.5
    cep_cycle_independent_min_score: float = 0.38
    cep_cycle_adjacent_warn_ratio: float = 1.50
    cep_cycle_adjacent_hard_ratio: float = 1.80
    cep_cycle_cv_warn: float = 0.20
    cep_cycle_cv_hard: float = 0.35
    cep_cycle_alternation_warn_log2: float = 0.18
    cep_cycle_alternation_hard_log2: float = 0.28
    cep_cycle_min_envelope_ratio: float = 0.25
    cep_cycle_hard_evidence_count: int = 2
    # v22: low envelope is supporting evidence only, because attenuation is expected near /f/.
    cep_low_envelope_support_only: bool = True
    # v22: automatically exclude REVIEW sides from the strict-comparison subset,
    # while retaining native values for transparent sensitivity analyses.
    cep_strict_exclude_review: bool = True
    cep_window_reoptimization_penalty: float = 0.08
    edge_pad_s: float = 0.60
    # aRFF-AP-like extraction settings. MATLAB aRFF-AP defaults are 50-400 Hz.
    ap_min_pitch: float = 50.0
    ap_max_pitch: float = 400.0
    ap_pitch_step_s: float = 0.002
    ap_edge_skip_s: float = 0.002
    ap_search_cycles: int = 18
    ap_band_st: float = 3.0
    # v4: microphone/ROI-guided mode. MATLAB-like sharp-transition checks are
    # retained as QC, but no longer reject non-catastrophic traces by default.
    ap_autocorr_min: float = 0.70
    ap_period_tol_low: float = 0.60
    ap_period_tol_high: float = 1.60
    ap_min_voiced_amp_ratio: float = 0.10
    ap_sharp_reject: bool = False
    ap_sharp_hard_mult: float = 4.0
    ap_rff_abs_hard_limit_st: float = 12.0
    save_debug_plots: bool = False
    # v25 optional post-processing. This does not modify any RFF extraction method.
    calculate_sti: bool = False
    sti_min_traces: int = 2
    sti_interpolation_points: int = 1000
    sti_sample_points: int = 50
    default_age_group: str = "40-64"
    default_sex: str = "Male"
    allow_default_metadata_for_normative: bool = False
    matlab_path: str = "matlab"
    mb_bridge_dir: str = ""
    ap_bridge_dir: str = ""
    run_matlab_mb: bool = True
    run_matlab_ap: bool = True
    matlab_timeout_s: int = 7200
    qc_edge_warn_s: float = 0.10
    hard_max_edge_gap_s: float = 0.25
    qc_period_cv_warn: float = 0.25
    qc_adjacent_ratio_warn: float = 1.80
    strict_boundary_adjacency: bool = True
    max_skipped_boundary_candidates: int = 0


@dataclass
class TraceResult:
    method: str
    subject: str
    filename: str
    filepath: str
    token: str
    rep: int
    fric_start: float
    fric_end: float
    off_rff: Optional[np.ndarray]
    on_rff: Optional[np.ndarray]
    off_valid: bool
    on_valid: bool
    off_reject: str = ""
    on_reject: str = ""
    n_off_landmarks: int = 0
    n_on_landmarks: int = 0
    debug: Optional[Dict[str, Any]] = None


# =============================================================================
# Generic helpers
# =============================================================================

def ensure_dir(path: str | pathlib.Path) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def safe_float(value: Any, default: float = np.nan) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except Exception:
        return default


def nanmean(vals: Iterable[Any]) -> float:
    a = np.asarray([safe_float(v) for v in vals], dtype=float)
    a = a[np.isfinite(a)]
    return float(np.mean(a)) if a.size else np.nan


def nanstd(vals: Iterable[Any]) -> float:
    a = np.asarray([safe_float(v) for v in vals], dtype=float)
    a = a[np.isfinite(a)]
    return float(np.std(a, ddof=1)) if a.size > 1 else np.nan


def best_channel(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        return x.reshape(-1)
    if x.ndim == 2:
        rms = np.sqrt(np.nanmean(np.square(np.nan_to_num(x)), axis=0) + 1e-24)
        return x[:, int(np.argmax(rms))].astype(float).reshape(-1)
    return x.reshape(-1).astype(float)


def read_audio(path: str | pathlib.Path) -> Tuple[np.ndarray, int]:
    y, fs = sf.read(str(path), always_2d=False, dtype="float64")
    y = best_channel(y)
    y = np.nan_to_num(y, copy=False)
    if y.size == 0 or fs <= 0:
        raise RuntimeError(f"Empty or invalid audio: {path}")
    return y, int(fs)


def normalize_audio_for_display(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=float).reshape(-1)
    mx = float(np.nanmax(np.abs(y))) if y.size else 0.0
    if mx > 0:
        return y / mx
    return y


def display_downsample(y: np.ndarray, fs: int, max_points: int = 250000) -> Tuple[np.ndarray, int]:
    """Downsample only for plotting to avoid Tk bitmap allocation errors."""
    y = np.asarray(y, dtype=float).reshape(-1)
    if y.size <= max_points:
        return y, int(fs)
    step = int(math.ceil(y.size / float(max_points)))
    return y[::step], max(1, int(round(fs / step)))


def hz_to_st(f: np.ndarray, f_ref: float) -> np.ndarray:
    f = np.asarray(f, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 12.0 * np.log2(f / max(float(f_ref), 1e-12))
    out[~np.isfinite(out)] = np.nan
    return out


def periods_to_freq(periods_s: np.ndarray) -> np.ndarray:
    periods_s = np.asarray(periods_s, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = 1.0 / periods_s
    f[~np.isfinite(f)] = np.nan
    return f


def subject_from_filename(path: str | pathlib.Path, token: str = "") -> str:
    stem = pathlib.Path(path).stem
    s = stem
    if token:
        # remove common token suffix/prefix patterns only, not arbitrary internal letters
        s = re.sub(rf"(?i)(^|[_\-\s]){re.escape(token)}($|[_\-\s].*)", "", s).strip("_- ")
        s = re.sub(rf"(?i)([_\-\s]){re.escape(token)}$", "", s).strip("_- ")
    # common AVHI subject token pattern C1234_afa
    m = re.match(r"(?i)^(C\d+)[_\-\s]+(afa|ifi|ufu)", stem)
    if m:
        return m.group(1)
    return s or stem


def token_from_filename(path: str | pathlib.Path) -> Optional[str]:
    stem = pathlib.Path(path).stem.lower()
    # Prefer token delimited by separators, but fall back to contains.
    for tok in TOKENS:
        if re.search(rf"(^|[_\-\s]){tok}($|[_\-\s])", stem):
            return tok
    for tok in TOKENS:
        if tok in stem:
            return tok
    return None


def scan_token_files(root: str | pathlib.Path) -> List[Dict[str, Any]]:
    root = pathlib.Path(root)
    rows = []
    if not root.exists():
        return rows
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
            continue
        tok = token_from_filename(p)
        if tok is None:
            continue
        subj = subject_from_filename(p, tok)
        if not subj or subj.lower() in TOKENS:
            subj = subject_from_folder(p.parent)
        rows.append({
            "Subject": subj,
            "Token": tok,
            "Filename": p.name,
            "Path": str(p),
            "Folder": str(p.parent),
        })
    rows.sort(key=lambda r: (str(r["Subject"]).lower(), r["Token"], r["Filename"].lower()))
    return rows


def subject_from_folder(folder: str | pathlib.Path) -> str:
    """Return the patient/session folder name, e.g. GC01_H or GE02_H."""
    return pathlib.Path(folder).name.strip()


def subject_base_id(value: str | pathlib.Path) -> str:
    """Normalize GC01_H, GC01-H, fricative_locations_GC01 -> GC01 for matching."""
    text = pathlib.Path(str(value)).stem if any(ch in str(value) for ch in "\\/.") else str(value)
    text = text.strip()
    text = re.sub(r"(?i)^fricative[_\-\s]*locations?[_\-\s]*", "", text)
    text = re.sub(r"(?i)^fricative[_\-\s]*location[_\-\s]*", "", text)
    m = re.search(r"(?i)\b([A-Z]{1,3}\d{1,4})\b", text)
    if m:
        return m.group(1).upper()
    text = re.sub(r"(?i)[_\-\s]*(H|M|F)$", "", text)
    return text.upper()


def find_fricative_location_files(root: str | pathlib.Path) -> List[pathlib.Path]:
    """Find fricative location files in patient subfolders. Handles extensionless files too."""
    root = pathlib.Path(root)
    if not root.exists():
        return []
    hits: List[pathlib.Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if "fric" in name and "loc" in name:
            hits.append(p)
    hits.sort(key=lambda x: str(x).lower())
    return hits


def read_fricative_location_file(path: str | pathlib.Path) -> pd.DataFrame:
    """Read CSV/TXT/TSV/XLS/XLSX fricative-location files with tolerant separators.

    The AVHI folders may contain files such as fricative_locations_GC01. This
    reader intentionally accepts extensionless text files and common delimiter
    variants.
    """
    p = pathlib.Path(path)
    suf = p.suffix.lower()
    if suf in {".xlsx", ".xls"}:
        return pd.read_excel(p)
    # Try automatic delimiter detection first. Works for comma, semicolon, tab, and many text tables.
    try:
        return pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        pass
    # Retry common encodings/separators.
    for enc in ("utf-8-sig", "latin1", "cp1252"):
        for sep in (",", ";", "\t", r"\s+"):
            try:
                df = pd.read_csv(p, sep=sep, engine="python", encoding=enc)
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue
    raise RuntimeError(f"Could not read fricative-location file: {p}")


def _column_lookup(df: pd.DataFrame) -> Dict[str, str]:
    return {str(c).strip().lower().replace(" ", "").replace("_", "").replace("-", ""): c for c in df.columns}


def _pick_column(df: pd.DataFrame, *names: str) -> Optional[str]:
    cmap = _column_lookup(df)
    for name in names:
        key = str(name).strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        if key in cmap:
            return cmap[key]
    return None


def _token_files_by_folder(files: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, List[Mapping[str, Any]]]]:
    out: Dict[str, Dict[str, List[Mapping[str, Any]]]] = {}
    for r in files:
        folder = str(pathlib.Path(str(r.get("Path", ""))).parent)
        tok = str(r.get("Token", "")).lower()
        out.setdefault(folder, {}).setdefault(tok, []).append(r)
    return out


def _find_audio_for_location_row(
    row: Mapping[str, Any],
    folder: pathlib.Path,
    token: str,
    token_index: Dict[str, Dict[str, List[Mapping[str, Any]]]],
) -> Optional[Mapping[str, Any]]:
    """Match one fricative-location row to an audio file in the same patient folder."""
    folder_key = str(folder)
    candidates = list(token_index.get(folder_key, {}).get(token, []))
    if not candidates:
        # Some corpora place audio one level below. Try descendants of the patient folder.
        for fkey, bytok in token_index.items():
            try:
                if pathlib.Path(fkey).is_relative_to(folder):
                    candidates.extend(bytok.get(token, []))
            except Exception:
                if str(fkey).lower().startswith(str(folder).lower()):
                    candidates.extend(bytok.get(token, []))
    if not candidates:
        return None

    filename_val = None
    for key in ("Filename", "filename", "File", "file", "wav", "Wav", "Path", "path"):
        if key in row and str(row.get(key, "")).strip():
            filename_val = str(row.get(key)).strip()
            break
    if filename_val:
        stem = pathlib.Path(filename_val).stem.lower()
        exact = [c for c in candidates if pathlib.Path(str(c.get("Path", ""))).stem.lower() == stem or str(c.get("Filename", "")).lower() == pathlib.Path(filename_val).name.lower()]
        if exact:
            return exact[0]
        contains = [c for c in candidates if stem in pathlib.Path(str(c.get("Path", ""))).stem.lower() or pathlib.Path(str(c.get("Path", ""))).stem.lower() in stem]
        if contains:
            return contains[0]

    # If one token file exists in the patient folder, that is the expected AVHI layout.
    return candidates[0] if len(candidates) == 1 else candidates[0]


def normalize_fricative_locations_to_roi_rows(
    loc_file: str | pathlib.Path,
    token_files: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Convert one fricative_locations_* file into canonical ROI rows.

    Canonical output columns match the GUI ROI table:
    Subject, Filename, Path, Token, Rep, FricStart, FricEnd, FricLoc, SourceFricativeFile
    """
    p = pathlib.Path(loc_file)
    folder = p.parent
    warnings: List[str] = []
    try:
        raw = read_fricative_location_file(p)
    except Exception as exc:
        return [], [f"{p.name}: could not read ({exc})"]

    if raw is None or raw.empty:
        return [], [f"{p.name}: empty file"]

    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    cmap = _column_lookup(df)

    token_col = _pick_column(df, "Token", "token", "Vowel", "vowel", "Task", "task", "Syllable", "syllable")
    rep_col = _pick_column(df, "Rep", "rep", "Repetition", "repetition", "Trial", "trial", "ROI", "roi")
    file_col = _pick_column(df, "Filename", "File", "Wav", "Path", "Audio", "audiofile", "soundfile")
    subj_col = _pick_column(df, "Subject", "ID", "Participant", "Patient", "Speaker")

    start_col = _pick_column(df, "FricStart", "FricativeStart", "Start", "StartTime", "t_start", "xmin", "x1", "Begin", "FricStart_s")
    end_col = _pick_column(df, "FricEnd", "FricativeEnd", "End", "EndTime", "t_end", "xmax", "x2", "Finish", "FricEnd_s")
    loc_col = _pick_column(df, "FricLoc", "FricativeLocation", "Location", "FricativeLoc", "FricTime", "Time", "Center", "Centre", "Mid", "FricLoc_s")
    dur_col = _pick_column(df, "FricDur", "Duration", "Dur", "FricativeDuration")

    if start_col is None and end_col is None and loc_col is None:
        # Last-resort: use first two numeric columns as start/end if available.
        numeric_cols = []
        for c in df.columns:
            vals = pd.to_numeric(df[c], errors="coerce")
            if vals.notna().sum() >= max(1, len(df) // 2):
                numeric_cols.append(c)
        if len(numeric_cols) >= 2:
            start_col, end_col = numeric_cols[0], numeric_cols[1]
        elif len(numeric_cols) == 1:
            loc_col = numeric_cols[0]

    if start_col is None and end_col is None and loc_col is None:
        return [], [f"{p.name}: no recognizable time columns"]

    token_index = _token_files_by_folder(token_files)
    rows: List[Dict[str, Any]] = []
    inferred_subject = subject_from_folder(folder)
    file_base_subject = subject_base_id(p.name)
    folder_base_subject = subject_base_id(inferred_subject)

    # If no token column exists, try to infer token from filename column or repeat the file for all tokens only if rows group naturally.
    for ridx, r in df.iterrows():
        asdict_row = r.to_dict()
        token = ""
        if token_col:
            token = str(r.get(token_col, "")).strip().lower()
            token = token_from_filename(token) or token
        if not token and file_col:
            token = token_from_filename(str(r.get(file_col, ""))) or ""
        if token not in TOKENS:
            # Try row text fallback.
            joined = " ".join(str(v) for v in r.to_dict().values()).lower()
            for tok in TOKENS:
                if tok in joined:
                    token = tok
                    break
        if token not in TOKENS:
            warnings.append(f"{p.name}: row {ridx+1} skipped because token was not identifiable")
            continue

        fst = safe_float(r.get(start_col)) if start_col else np.nan
        fend = safe_float(r.get(end_col)) if end_col else np.nan
        floc = safe_float(r.get(loc_col)) if loc_col else np.nan
        fdur = safe_float(r.get(dur_col)) if dur_col else np.nan

        if not np.isfinite(fst) or not np.isfinite(fend):
            if np.isfinite(floc) and np.isfinite(fdur) and fdur > 0:
                fst = floc - 0.5 * fdur
                fend = floc + 0.5 * fdur
            elif np.isfinite(floc):
                # Conservative fallback if the file stores a single /f/ location only.
                # The window can be edited manually in the GUI if needed.
                half = 0.035
                fst = floc - half
                fend = floc + half
        if not (np.isfinite(fst) and np.isfinite(fend) and fend > fst):
            warnings.append(f"{p.name}: row {ridx+1} skipped because start/end were invalid")
            continue

        audio = _find_audio_for_location_row(asdict_row, folder, token, token_index)
        if audio is None:
            warnings.append(f"{p.name}: row {ridx+1} /{token}/ skipped because no matching audio file was found")
            continue

        # Time-unit safety: most AVHI ROI files store seconds, but this also
        # rescales millisecond or sample-index values when they are obvious.
        try:
            info = sf.info(str(audio.get("Path")))
            dur_s = float(info.duration)
            fs_audio = float(info.samplerate)
            if np.isfinite(dur_s) and dur_s > 0 and fend > (dur_s + 0.25):
                if (fend / 1000.0) <= (dur_s + 0.25):
                    fst, fend, floc = fst / 1000.0, fend / 1000.0, (floc / 1000.0 if np.isfinite(floc) else floc)
                    warnings.append(f"{p.name}: row {ridx+1} appeared to be in ms; converted to seconds")
                elif fs_audio > 0 and (fend / fs_audio) <= (dur_s + 0.25):
                    fst, fend, floc = fst / fs_audio, fend / fs_audio, (floc / fs_audio if np.isfinite(floc) else floc)
                    warnings.append(f"{p.name}: row {ridx+1} appeared to be in samples; converted to seconds")
        except Exception:
            pass

        subject = str(r.get(subj_col, "")).strip() if subj_col else ""
        if not subject or subject.lower() == "nan":
            # Prefer the patient/session folder name because your corpus folders are GC01_H, GE02_H, etc.
            subject = inferred_subject
        rep = safe_float(r.get(rep_col), np.nan) if rep_col else np.nan
        if not np.isfinite(rep):
            # Repetition is assigned after sorting by start within token/file below.
            rep = np.nan

        rows.append({
            "Subject": subject,
            "Filename": str(audio.get("Filename")),
            "Path": str(audio.get("Path")),
            "Token": token,
            "Rep": int(rep) if np.isfinite(rep) else np.nan,
            "FricStart": float(max(0.0, fst)),
            "FricEnd": float(max(0.0, fend)),
            "FricLoc": float(0.5 * (fst + fend)) if not np.isfinite(floc) else float(floc),
            "SourceFricativeFile": str(p),
            "SourceRow": int(ridx + 1),
            "FolderSubjectBase": folder_base_subject,
            "FileSubjectBase": file_base_subject,
        })

    if rows:
        tmp = pd.DataFrame(rows)
        # Assign missing/invalid Rep in chronological order within each audio file.
        for (_path, _tok), g in tmp.groupby(["Path", "Token"], sort=False):
            g = g.sort_values("FricStart")
            next_rep = 1
            for idx in g.index:
                rep_val = safe_float(tmp.at[idx, "Rep"], np.nan)
                if not np.isfinite(rep_val) or rep_val <= 0:
                    tmp.at[idx, "Rep"] = next_rep
                tmp.at[idx, "Rep"] = int(tmp.at[idx, "Rep"])
                next_rep += 1
        rows = tmp.to_dict(orient="records")

    return rows, warnings


def import_fricative_locations_from_root(
    root: str | pathlib.Path,
    token_files: Sequence[Mapping[str, Any]],
) -> Tuple[pd.DataFrame, List[str]]:
    """Scan all patient folders for fricative location files and build one ROI table."""
    all_rows: List[Dict[str, Any]] = []
    messages: List[str] = []
    loc_files = find_fricative_location_files(root)
    messages.append(f"Found {len(loc_files)} fricative-location files.")
    for loc in loc_files:
        rows, warnings = normalize_fricative_locations_to_roi_rows(loc, token_files)
        all_rows.extend(rows)
        messages.append(f"{loc.name}: imported {len(rows)} ROI rows")
        messages.extend(["  warning: " + w for w in warnings])
    df = pd.DataFrame(all_rows)
    if not df.empty:
        # Remove exact duplicates while preserving first occurrence.
        key_cols = ["Path", "Token", "Rep", "FricStart", "FricEnd"]
        for c in key_cols:
            if c not in df.columns:
                df[c] = np.nan
        df = df.drop_duplicates(subset=key_cols, keep="first")
        df = df.sort_values(["Subject", "Token", "Path", "Rep", "FricStart"]).reset_index(drop=True)
    return df, messages


# =============================================================================
# Praat / Parselmouth pulse extraction
# =============================================================================

def _write_praat_pulses_script(script_path: str | pathlib.Path) -> None:
    script = r'''form Voice_analysis
    text name ""
    real wst 0
    real wend 0
    real filtYN 0
    text outtxt ""
endform

clearinfo
Read from file... 'name$'
fileName$ = selected$("Sound")
select Sound 'fileName$'

if wend > wst
    Extract part: wst, wend, "rectangular", 1, "no"
    selectObject: "Sound " + fileName$ + "_part"
    Rename: fileName$
endif

if filtYN == 1
    Filter (pass Hann band): 60, 3000, 100
    selectObject: "Sound " + fileName$ + "_band"
    Rename: fileName$
endif

To PointProcess (periodic, cc)... 75 500
select PointProcess 'fileName$'
numberOfPulses = Get number of points
filedelete 'outtxt$'
for ii from 1 to numberOfPulses
    tt = Get time from index: ii
    fileappend 'outtxt$' 'tt' newline
endfor
'''
    pathlib.Path(script_path).write_text(script, encoding="utf-8")


def find_praat_executable(user_path: str = "") -> str:
    if user_path and pathlib.Path(user_path).exists():
        return user_path
    for name in ("praatcon.exe", "Praat.exe", "praat.exe", "praat"):
        found = shutil.which(name)
        if found:
            return found
    return user_path or ""


def get_praat_pulses(
    wav_path: str,
    config: RFFConfig,
    win: Optional[Tuple[float, float]] = None,
    debug: bool = False,
) -> np.ndarray:
    """Return absolute pulse times in seconds."""
    wst, wend = (win if (win and win[1] > win[0]) else (0.0, 0.0))

    if parselmouth is not None:
        try:
            snd = parselmouth.Sound(str(wav_path))
            if wend > wst:
                snd = praat_call(snd, "Extract part", float(wst), float(wend), "rectangular", 1.0, "no")
            if config.use_bandpass:
                snd = praat_call(snd, "Filter (pass Hann band)", 60, 3000, 100)
            pp = praat_call(
                snd,
                "To PointProcess (periodic, cc)",
                float(config.praat_min_pitch),
                float(config.praat_max_pitch),
            )
            n = int(praat_call(pp, "Get number of points"))
            if n <= 0:
                return np.asarray([], dtype=float)
            times = [praat_call(pp, "Get time from index", i + 1) for i in range(n)]
            return np.asarray(times, dtype=float) + (wst if wend > wst else 0.0)
        except Exception as exc:
            if debug:
                print("[Parselmouth pulse extraction failed]", repr(exc))

    praat_exe = find_praat_executable(config.praat_path)
    if not praat_exe:
        return np.asarray([], dtype=float)

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="avhi_rff_praat_"))
    script_path = tmpdir / "dump_pulses.praat"
    outtxt = tmpdir / "pulses.txt"
    try:
        _write_praat_pulses_script(script_path)
        args = [
            praat_exe,
            "--run",
            str(script_path),
            str(wav_path),
            f"{float(wst):.8f}",
            f"{float(wend):.8f}",
            str(int(config.use_bandpass)),
            str(outtxt),
        ]
        completed = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if debug and completed.stderr:
            print(completed.stderr[:800])
        vals = []
        if outtxt.exists():
            for line in outtxt.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    vals.append(float(line.strip()))
                except Exception:
                    pass
        return np.asarray(vals, dtype=float) if vals else np.asarray([], dtype=float)
    except Exception as exc:
        if debug:
            print("[Praat executable pulse extraction failed]", repr(exc))
        return np.asarray([], dtype=float)
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)


def refine_pulses_near_edge(
    wav_path: str,
    pulses_all: np.ndarray,
    split_at: float,
    side: str,
    config: RFFConfig,
) -> np.ndarray:
    """Return only pulses from the target side and near the manual boundary.

    v13 safety change: the previous fallback could return every pulse on the
    requested side when sliding-window voting failed. In a file with another
    voiced segment later in time, that allowed a distant segment to become the
    onset window. This function now never falls back outside the configured
    near-edge interval.
    """
    pulses_all = np.asarray(pulses_all, dtype=float)
    pulses_all = np.unique(np.sort(pulses_all[np.isfinite(pulses_all)]))
    if pulses_all.size == 0:
        return np.asarray([], dtype=float)

    off_all = pulses_all[pulses_all < split_at]
    on_all = pulses_all[pulses_all > split_at]
    off_near = off_all[(off_all >= split_at - float(config.near_off_s)) & (off_all < split_at)]
    on_near = on_all[(on_all > split_at) & (on_all <= split_at + float(config.near_on_s))]

    if side == "off":
        if off_near.size == 0:
            return np.asarray([], dtype=float)
    elif side == "on":
        if on_near.size == 0:
            return np.asarray([], dtype=float)
    else:
        raise ValueError("side must be 'off' or 'on'")

    # The voting logic needs pulses on both sides to define its windows. If
    # one side is absent, deterministic near-edge selection is safer.
    if off_all.size == 0 or on_all.size == 0:
        return np.asarray(off_near if side == "off" else on_near, dtype=float)

    info = sf.info(str(wav_path))
    fs = int(info.samplerate)
    file_len = int(info.frames)
    winsiz = float(config.window_vote_s)
    pp = 0
    acc: List[np.ndarray] = []

    if side == "off":
        x2 = int(math.ceil(on_all[0] * fs))
        x1 = 1
        if off_all.size > 20:
            xst = int(math.floor((off_all[-20] - (on_all[0] - off_all[-1])) * fs))
            if xst > 1:
                x1 = xst
        step = max(1, int(math.floor(winsiz * fs)))
        while (x2 / fs) <= on_all[0] + 1e-12:
            pp += 1
            tempp = get_praat_pulses(str(wav_path), config, win=(x1 / fs, x2 / fs))
            if tempp.size > 15:
                acc.append(tempp[-15:])
            x1 += step
            x2 += step
        if acc and pp > 0:
            rpa = np.round(np.concatenate(acc), 3)
            upa, counts = np.unique(rpa, return_counts=True)
            keep = upa[counts >= (config.vote_off_min * pp)]
            if keep.size > 0:
                idx_local = int(np.argmin(np.abs(off_near - keep[-1])))
                return np.asarray(off_near[: idx_local + 1], dtype=float)
        return np.asarray(off_near, dtype=float)

    x1 = int(math.floor(off_all[-1] * fs))
    x2 = int(math.ceil(on_all[19] * fs)) if on_all.size >= 20 else int(math.ceil(on_all[-1] * fs))
    step = max(1, int(math.floor(winsiz * fs)))
    while (x1 / fs) <= (on_all[0] - 0.02) + 1e-12:
        pp += 1
        tempp = get_praat_pulses(str(wav_path), config, win=(x1 / fs, x2 / fs))
        if tempp.size > 20:
            acc.append(tempp)
        x1 += step
        x2 = min(file_len, x2 + step)
    if acc and pp > 0:
        rpa = np.round(np.concatenate(acc), 3)
        upa, counts = np.unique(rpa, return_counts=True)
        keep = upa[counts >= (config.vote_on_min * pp)]
        if keep.size > 0:
            idx_local = int(np.argmin(np.abs(on_near - keep[0])))
            return np.asarray(on_near[idx_local:], dtype=float)
    return np.asarray(on_near, dtype=float)


def maybe_fix_subharmonic(pulses: np.ndarray, config: RFFConfig) -> Tuple[np.ndarray, bool]:
    """Light 2:1 alternation repair, useful when Praat misses every other pulse."""
    pulses = np.asarray(pulses, dtype=float)
    if pulses.size < 12:
        return pulses, False
    T = np.diff(pulses)
    if T.size < 10:
        return pulses, False
    Te = T[::2]
    To = T[1::2]
    if Te.size == 0 or To.size == 0:
        return pulses, False
    me = float(np.nanmedian(Te))
    mo = float(np.nanmedian(To))
    big, small = (me, mo) if me >= mo else (mo, me)
    ratio = big / max(small, 1e-9)
    if config.subharmonic_low <= ratio <= config.subharmonic_high:
        newp = [float(pulses[0])]
        for i, dt in enumerate(T):
            if dt >= 1.7 * small:
                newp.append(float(pulses[i] + 0.5 * dt))
            newp.append(float(pulses[i + 1]))
        return np.asarray(sorted(newp), dtype=float), True
    return pulses, False


# =============================================================================
# RFF from pulse/cycle landmark arrays
# =============================================================================

def rff_from_landmarks(
    landmarks_s: np.ndarray,
    side: str,
    config: RFFConfig,
    strict: bool = True,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """
    Compute 10 RFF values from an ordered set of landmarks around one edge.

    Offset: last 11 landmarks before /f/ -> 10 periods; reference is OFF1.
    Onset : first 11 landmarks after /f/ -> 10 periods; reference is ON10.
    """
    landmarks_s = np.asarray(landmarks_s, dtype=float)
    landmarks_s = landmarks_s[np.isfinite(landmarks_s)]
    landmarks_s = np.unique(np.sort(landmarks_s))
    details: Dict[str, Any] = {
        "side": side,
        "all_landmarks_s": landmarks_s.tolist(),
        "strict": bool(strict),
    }
    if landmarks_s.size < 11:
        details["reject"] = "not enough landmarks"
        return None, "not enough landmarks", details

    if side == "off":
        sel = landmarks_s[-11:]
    else:
        sel = landmarks_s[:11]
    periods = np.diff(sel)
    freqs = periods_to_freq(periods)
    details.update({
        "selected_landmarks_s": sel.tolist(),
        "periods_s": periods.tolist(),
        "freqs_hz": freqs.tolist(),
    })

    if periods.size != 10 or not np.all(np.isfinite(periods)) or np.any(periods <= 0):
        details["reject"] = "invalid periods"
        return None, "invalid periods", details

    # Plausibility gate by F0 bounds. Keep mild tolerance because edge cycles can be perturbed.
    lo = 1.0 / max(config.f0_ceiling * 1.35, 1.0)
    hi = 1.0 / max(config.f0_floor * 0.60, 1.0)
    if np.any((periods < lo) | (periods > hi)):
        details["period_plausibility_warning"] = True
        if strict:
            details["reject"] = "period outside plausible F0 range"
            return None, "period outside plausible F0 range", details

    # Outlier and variance gates copied from the AVHI/aRFF-B-like logic.
    if strict:
        if side == "off":
            thr = np.percentile(periods, config.percentile) * config.outlier_mult
            if periods[-1] > thr:
                details["reject"] = "offset period is an outlier"
                return None, "offset period is an outlier", details
            if np.var(periods) > config.var_threshold_s2:
                details["reject"] = "high variance in periods"
                return None, "high variance in periods", details
            if np.sum(periods > np.percentile(periods, config.percentile) * config.outlier_mult) > 0:
                details["reject"] = "periods contain an outlier"
                return None, "periods contain an outlier", details
            base = freqs[0]
            rff = hz_to_st(freqs, base)
            if not np.isfinite(base) or base <= 0:
                details["reject"] = "invalid reference frequency"
                return None, "invalid reference frequency", details
            if np.abs(rff[1]) > config.steady_off_abs_st:
                details["reject"] = "failure to reach offset steady-state"
                return None, "failure to reach offset steady-state", details
        else:
            thr = np.percentile(periods, config.percentile) * config.outlier_mult
            if periods[0] > thr:
                details["reject"] = "onset period is an outlier"
                return None, "onset period is an outlier", details
            if np.var(periods) > config.var_threshold_s2:
                details["reject"] = "high variance in periods"
                return None, "high variance in periods", details
            if np.sum(periods[1:] > np.percentile(periods, config.percentile) * config.outlier_mult) > 0:
                details["reject"] = "periods contain an outlier"
                return None, "periods contain an outlier", details
            base = freqs[9]
            rff = hz_to_st(freqs, base)
            if not np.isfinite(base) or base <= 0:
                details["reject"] = "invalid reference frequency"
                return None, "invalid reference frequency", details
            if np.abs(rff[8]) > config.steady_on_abs_st:
                details["reject"] = "failure to reach onset steady-state"
                return None, "failure to reach onset steady-state", details
    else:
        base = freqs[0] if side == "off" else freqs[9]
        if not np.isfinite(base) or base <= 0:
            details["reject"] = "invalid reference frequency"
            return None, "invalid reference frequency", details
        rff = hz_to_st(freqs, base)

    if rff.shape != (10,) or not np.all(np.isfinite(rff)):
        details["reject"] = "non-finite RFF"
        return None, "non-finite RFF", details

    details["rff_st"] = rff.tolist()
    details["reject"] = ""
    return rff, "", details



def _boundary_candidate_skip_count(
    candidates: Sequence[float],
    final: Sequence[float],
    edge_time: float,
    side: str,
) -> int:
    """Count same-trace candidates closer to the ROI edge than the final window."""
    cand = np.asarray(candidates, dtype=float).ravel()
    cand = np.unique(np.sort(cand[np.isfinite(cand)]))
    sel = np.asarray(final, dtype=float).ravel()
    sel = np.unique(np.sort(sel[np.isfinite(sel)]))
    if cand.size == 0 or sel.size == 0 or not np.isfinite(edge_time):
        return 0
    tol = 1e-9
    if side.lower() == "off":
        return int(np.sum((cand > sel[-1] + tol) & (cand < edge_time - tol)))
    return int(np.sum((cand < sel[0] - tol) & (cand > edge_time + tol)))


def _period_ratio_metrics(periods: Sequence[float]) -> Tuple[float, float]:
    """Return max period/median ratio and true adjacent-period ratio."""
    per = np.asarray(periods, dtype=float).ravel()
    per = per[np.isfinite(per)]
    if per.size == 0 or np.any(per <= 0):
        return np.nan, np.nan
    med = float(np.nanmedian(per))
    if not np.isfinite(med) or med <= 0:
        return np.nan, np.nan
    median_ratio = float(np.nanmax(np.r_[per / med, med / per]))
    if per.size < 2:
        adjacent_ratio = 1.0
    else:
        adjacent_ratio = float(np.nanmax(np.r_[per[1:] / per[:-1], per[:-1] / per[1:]]))
    return median_ratio, adjacent_ratio


def _apply_hard_landmark_gate(
    rff: Optional[np.ndarray],
    reject: str,
    details: Dict[str, Any],
    edge_time: float,
    side: str,
    config: RFFConfig,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Reject final windows that are on the wrong ROI side or another segment.

    Small/medium edge gaps remain QC warnings. A wrong-side selection, a
    non-11-landmark window, a catastrophic adjacent-period jump, a gap above
    ``hard_max_edge_gap_s``, or a strict-adjacency violation is rejected here.
    """
    final = np.asarray(details.get("selected_landmarks_s", []), dtype=float)
    final = final[np.isfinite(final)]
    final = np.unique(np.sort(final))
    details["final_landmarks_s"] = final.tolist()
    details["n_final_landmarks"] = int(final.size)
    details["edge_time_s"] = float(edge_time)
    candidates = np.asarray(details.get("candidate_landmarks_s", []), dtype=float)
    candidates = np.unique(np.sort(candidates[np.isfinite(candidates)]))
    skipped = _boundary_candidate_skip_count(candidates, final, edge_time, side)
    enforce_adjacency = bool(details.get("enforce_boundary_adjacency", False))
    adjustment_reason = str(details.get("boundary_adjustment_reason", "") or "")
    if skipped > 0 and not adjustment_reason:
        adjustment_reason = "selected_window_not_edge_adjacent"

    if final.size:
        periods = np.diff(final)
        med = float(np.nanmedian(periods)) if periods.size else np.nan
        if side.lower() == "off":
            wrong = int(np.sum(final >= edge_time))
            gap = float(edge_time - final[-1])
        else:
            wrong = int(np.sum(final <= edge_time))
            gap = float(final[0] - edge_time)
        cv = float(np.nanstd(periods) / med) if periods.size and np.isfinite(med) and med > 0 else np.nan
        max_median_ratio, max_adjacent_ratio = _period_ratio_metrics(periods)
        edge_cycles = float(gap / med) if np.isfinite(gap) and np.isfinite(med) and med > 0 else np.nan
    else:
        periods = np.asarray([], dtype=float)
        med = cv = max_median_ratio = max_adjacent_ratio = edge_cycles = gap = np.nan
        wrong = 0

    details.update({
        "periods_s": periods.tolist(),
        "median_period_s": med,
        "period_cv": cv,
        "max_period_to_median_ratio": max_median_ratio,
        "max_adjacent_period_ratio": max_adjacent_ratio,
        "wrong_side_count": wrong,
        "skipped_boundary_candidates": int(skipped),
        "boundary_adjustment_reason": adjustment_reason,
        "enforce_boundary_adjacency": enforce_adjacency,
        "edge_gap_s": gap,
        "edge_gap_ms": 1000.0 * gap if np.isfinite(gap) else np.nan,
        "edge_gap_cycles": edge_cycles,
        "contiguous": bool(final.size == 11 and periods.size == 10 and np.all(periods > 0) and (not np.isfinite(max_adjacent_ratio) or max_adjacent_ratio <= 2.5)),
    })

    if rff is None:
        return rff, reject, details
    if final.size != 11:
        details["reject"] = "insufficient_contiguous_cycles"
        return None, "insufficient_contiguous_cycles", details
    if wrong > 0:
        details["reject"] = "wrong_side_of_roi"
        return None, "wrong_side_of_roi", details
    if enforce_adjacency and skipped > int(config.max_skipped_boundary_candidates):
        details["reject"] = "skipped_boundary_candidates"
        return None, "skipped_boundary_candidates", details
    if np.isfinite(max_adjacent_ratio) and max_adjacent_ratio > 2.5:
        details["reject"] = "cycle_period_outlier"
        return None, "cycle_period_outlier", details
    if not np.isfinite(gap) or gap > float(config.hard_max_edge_gap_s):
        details["reject"] = "selected_window_too_far"
        return None, "selected_window_too_far", details
    return rff, reject, details

# =============================================================================
# Method 1 and 2: Praat / B-mode / AVHI mode
# =============================================================================

def compute_praat_based_rff(
    wav_path: str,
    subject: str,
    token: str,
    rep: int,
    fric_start: float,
    fric_end: float,
    config: RFFConfig,
    method: str,
    strict: bool = True,
    subharmonic_repair: bool = False,
) -> TraceResult:
    pulses_all = get_praat_pulses(wav_path, config)
    if pulses_all.size == 0:
        return TraceResult(
            method=method, subject=subject, filename=os.path.basename(wav_path), filepath=wav_path,
            token=token, rep=rep, fric_start=fric_start, fric_end=fric_end,
            off_rff=None, on_rff=None, off_valid=False, on_valid=False,
            off_reject="no Praat pulses", on_reject="no Praat pulses", debug={"pulses_all": []},
        )
    off_p = refine_pulses_near_edge(wav_path, pulses_all, fric_start, "off", config)
    on_p = refine_pulses_near_edge(wav_path, pulses_all, fric_end, "on", config)
    off_candidates = np.asarray(pulses_all, dtype=float)
    off_candidates = off_candidates[
        (off_candidates < fric_start) & (off_candidates >= fric_start - float(config.near_off_s))
    ]
    on_candidates = np.asarray(pulses_all, dtype=float)
    on_candidates = on_candidates[
        (on_candidates > fric_end) & (on_candidates <= fric_end + float(config.near_on_s))
    ]
    off_fixed = on_fixed = False
    if subharmonic_repair:
        off_p, off_fixed = maybe_fix_subharmonic(off_p, config)
        on_p, on_fixed = maybe_fix_subharmonic(on_p, config)

    off_rff, off_rej, off_details = rff_from_landmarks(off_p, "off", config, strict=strict)
    on_rff, on_rej, on_details = rff_from_landmarks(on_p, "on", config, strict=strict)
    off_details["candidate_landmarks_s"] = np.asarray(off_candidates, dtype=float).tolist()
    on_details["candidate_landmarks_s"] = np.asarray(on_candidates, dtype=float).tolist()
    off_details["enforce_boundary_adjacency"] = False
    on_details["enforce_boundary_adjacency"] = False
    if _boundary_candidate_skip_count(off_candidates, off_details.get("selected_landmarks_s", []), fric_start, "off") > 0:
        off_details["boundary_adjustment_reason"] = "praat_voting_or_refinement"
    if _boundary_candidate_skip_count(on_candidates, on_details.get("selected_landmarks_s", []), fric_end, "on") > 0:
        on_details["boundary_adjustment_reason"] = "praat_voting_or_refinement"
    off_rff, off_rej, off_details = _apply_hard_landmark_gate(
        off_rff, off_rej, off_details, fric_start, "off", config
    )
    on_rff, on_rej, on_details = _apply_hard_landmark_gate(
        on_rff, on_rej, on_details, fric_end, "on", config
    )
    off_details["pulse_source"] = "Praat/Parselmouth"
    on_details["pulse_source"] = "Praat/Parselmouth"
    if off_fixed and off_rej:
        off_rej += "; subharmonic repair attempted"
    if on_fixed and on_rej:
        on_rej += "; subharmonic repair attempted"
    return TraceResult(
        method=method,
        subject=subject,
        filename=os.path.basename(wav_path),
        filepath=wav_path,
        token=token,
        rep=rep,
        fric_start=fric_start,
        fric_end=fric_end,
        off_rff=off_rff,
        on_rff=on_rff,
        off_valid=off_rff is not None,
        on_valid=on_rff is not None,
        off_reject=off_rej,
        on_reject=on_rej,
        n_off_landmarks=int(len(off_details.get("selected_landmarks_s", []))) if off_rff is not None else 0,
        n_on_landmarks=int(len(on_details.get("selected_landmarks_s", []))) if on_rff is not None else 0,
        debug={
            "implementation_stamp": SCRIPT_VERSION,
            "algorithm_family": "Praat pulse-based AVHI strict",
            "pitch_source": "Praat/Parselmouth PointProcess",
            "n_global_pulses": int(pulses_all.size),
            "global_pulses_s": np.asarray(pulses_all, dtype=float).tolist(),
            "off_subharmonic_repair": bool(off_fixed),
            "on_subharmonic_repair": bool(on_fixed),
            "off_details": off_details,
            "on_details": on_details,
        },
    )


# =============================================================================
# Method 3: AP-style waveform peak/trough extraction
# =============================================================================

def pitch_track_praat(y: np.ndarray, fs: int, config: RFFConfig) -> Tuple[np.ndarray, np.ndarray]:
    if parselmouth is not None:
        try:
            snd = parselmouth.Sound(np.asarray(y, dtype=float), sampling_frequency=float(fs))
            pitch = snd.to_pitch_ac(
                time_step=0.005,
                pitch_floor=float(config.f0_floor),
                pitch_ceiling=float(config.f0_ceiling),
                voicing_threshold=0.30,
                silence_threshold=0.01,
                octave_cost=0.01,
                octave_jump_cost=0.35,
                voiced_unvoiced_cost=0.10,
                very_accurate=True,
            )
            t = np.asarray(pitch.xs(), dtype=float)
            f0 = np.asarray(pitch.selected_array["frequency"], dtype=float)
            f0[~np.isfinite(f0)] = np.nan
            f0[f0 <= 0] = np.nan
            return t, f0
        except Exception:
            pass
    return autocorr_pitch_track(y, fs, config)


def autocorr_pitch_track(y: np.ndarray, fs: int, config: RFFConfig, frame_s: float = 0.040, hop_s: float = 0.005) -> Tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y, dtype=float).reshape(-1)
    n = max(16, int(round(frame_s * fs)))
    h = max(1, int(round(hop_s * fs)))
    if y.size < n:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    win = np.hanning(n)
    lag_min = max(1, int(fs / max(config.f0_ceiling, 1.0)))
    lag_max = max(lag_min + 1, int(fs / max(config.f0_floor, 1.0)))
    t_out = []
    f_out = []
    for i0 in range(0, y.size - n + 1, h):
        seg = y[i0:i0 + n]
        seg = (seg - np.mean(seg)) * win
        ac = np.correlate(seg, seg, mode="full")[n - 1:]
        if lag_max >= ac.size:
            lag_max2 = ac.size - 1
        else:
            lag_max2 = lag_max
        if lag_max2 <= lag_min:
            f = np.nan
        else:
            lag = lag_min + int(np.argmax(ac[lag_min:lag_max2]))
            f = fs / lag if lag > 0 else np.nan
            if not (config.f0_floor <= f <= config.f0_ceiling):
                f = np.nan
        t_out.append((i0 + n / 2) / fs)
        f_out.append(f)
    return np.asarray(t_out, dtype=float), np.asarray(f_out, dtype=float)


def local_median_f0(y: np.ndarray, fs: int, t0: float, t1: float, config: RFFConfig) -> float:
    t, f = pitch_track_praat(y, fs, config)
    if t.size and f.size:
        mask = (t >= t0) & (t <= t1) & np.isfinite(f) & (f > 0)
        if np.any(mask):
            return float(np.nanmedian(f[mask]))
    # fallback to broad median
    t, f = autocorr_pitch_track(y, fs, config)
    mask = np.isfinite(f) & (f > 0)
    return float(np.nanmedian(f[mask])) if np.any(mask) else np.nan


def find_cycle_landmarks_waveform(
    y: np.ndarray,
    fs: int,
    edge_time: float,
    side: str,
    f0_med: float,
    config: RFFConfig,
    kind: str,
) -> np.ndarray:
    """Find peak or trough landmarks around an edge using waveform extrema."""
    y = normalize_audio_for_display(y)
    if not (np.isfinite(f0_med) and f0_med > 0):
        return np.asarray([], dtype=float)
    T = 1.0 / float(f0_med)
    pad_before = max(0.18, 13.0 * T + 0.05)
    pad_after = max(0.18, 13.0 * T + 0.05)
    if side == "off":
        t0 = max(0.0, edge_time - pad_before)
        t1 = max(t0, edge_time - 0.002)
    else:
        t0 = min(edge_time + 0.002, len(y) / fs)
        t1 = min(len(y) / fs, edge_time + pad_after)
    i0 = max(0, int(round(t0 * fs)))
    i1 = min(y.size, int(round(t1 * fs)))
    if i1 - i0 < max(8, int(3.0 * T * fs)):
        return np.asarray([], dtype=float)

    seg = y[i0:i1].copy()
    # High-pass / detrend so DC drift does not dominate extrema.
    seg = sp_signal.detrend(seg, type="linear") if seg.size > 4 else seg
    target = seg if kind == "peak" else -seg
    min_dist = max(1, int(round(0.45 * T * fs)))
    prom = max(0.005, 0.05 * (np.nanpercentile(target, 95) - np.nanpercentile(target, 5)))
    peaks, props = sp_signal.find_peaks(target, distance=min_dist, prominence=prom)
    if peaks.size < 11:
        # retry with lower prominence
        peaks, props = sp_signal.find_peaks(target, distance=min_dist, prominence=max(0.002, prom * 0.35))
    times = (i0 + peaks.astype(float)) / fs
    times = times[np.isfinite(times)]
    if side == "off":
        times = times[times < edge_time]
        if times.size > 11:
            times = times[-11:]
    else:
        times = times[times > edge_time]
        if times.size > 11:
            times = times[:11]
    return np.asarray(np.sort(times), dtype=float)


def combine_peak_trough_rff(
    peak_rff: Optional[np.ndarray],
    trough_rff: Optional[np.ndarray],
) -> Optional[np.ndarray]:
    parts = []
    if peak_rff is not None and np.asarray(peak_rff).shape == (10,) and np.all(np.isfinite(peak_rff)):
        parts.append(np.asarray(peak_rff, dtype=float))
    if trough_rff is not None and np.asarray(trough_rff).shape == (10,) and np.all(np.isfinite(trough_rff)):
        parts.append(np.asarray(trough_rff, dtype=float))
    if not parts:
        return None
    return np.nanmean(np.vstack(parts), axis=0)


# =============================================================================
# aRFF-AP-like and adjusted cepstral-assisted extraction
# =============================================================================

ARFF_OFF_DIFF_THRESH_ST = np.asarray([0.5, 0.5, 0.5, 0.5, 0.8, 1.0, 1.5, 2.5, 3.5], dtype=float)
ARFF_ON_DIFF_THRESH_ST = np.asarray([6.0, 4.0, 3.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=float)


def _moving_median_1d(x: np.ndarray, samples: int) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    k = int(max(1, samples))
    if k % 2 == 0:
        k += 1
    if x.size < 3 or k <= 1:
        return x.copy()
    try:
        return pd.Series(x).rolling(k, center=True, min_periods=1).median().to_numpy(dtype=float)
    except Exception:
        return x.copy()


def _safe_bandpass_filter(x: np.ndarray, fs: int, f_lo: float, f_hi: float, order: int = 2) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    nyq = 0.5 * float(fs)
    f_lo = max(1.0, float(f_lo))
    f_hi = min(float(f_hi), nyq * 0.98)
    if not (0 < f_lo < f_hi < nyq) or x.size < max(64, int(0.03 * fs)):
        return sp_signal.detrend(x, type="constant") if x.size else x
    try:
        sos = sp_signal.ellip(int(order), 0.5, 100, [f_lo / nyq, f_hi / nyq], btype="bandpass", output="sos")
        return sp_signal.sosfiltfilt(sos, x)
    except Exception:
        try:
            sos = sp_signal.butter(4, [f_lo / nyq, f_hi / nyq], btype="bandpass", output="sos")
            return sp_signal.sosfiltfilt(sos, x)
        except Exception:
            return sp_signal.detrend(x, type="constant") if x.size else x


def _arff_pitch_track(y: np.ndarray, fs: int, config: RFFConfig, use_cepstral: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return time, F0, and confidence/pitch-strength-like support."""
    if use_cepstral:
        t, f0, prom = cepstral_f0_track(y, fs, config)
        return t, f0, prom

    if parselmouth is not None:
        try:
            snd = parselmouth.Sound(np.asarray(y, dtype=float), sampling_frequency=float(fs))
            pitch = snd.to_pitch_ac(
                time_step=float(config.ap_pitch_step_s),
                pitch_floor=float(config.ap_min_pitch),
                pitch_ceiling=float(config.ap_max_pitch),
                voicing_threshold=0.25,
                silence_threshold=0.01,
                octave_cost=0.01,
                octave_jump_cost=0.35,
                voiced_unvoiced_cost=0.10,
                very_accurate=True,
            )
            t = np.asarray(pitch.xs(), dtype=float)
            f0 = np.asarray(pitch.selected_array["frequency"], dtype=float)
            f0[~np.isfinite(f0)] = np.nan
            f0[f0 <= 0] = np.nan
            # Parselmouth does not expose A-SWIPE pitch strength here. Use finite voicing as support.
            support = np.where(np.isfinite(f0) & (f0 > 0), 1.0, 0.0)
            return t, f0, support
        except Exception:
            pass

    # Fallback AC tracker using AP pitch limits.
    y = np.asarray(y, dtype=float).reshape(-1)
    frame_s = 0.040
    hop_s = max(float(config.ap_pitch_step_s), 0.002)
    n = max(16, int(round(frame_s * fs)))
    h = max(1, int(round(hop_s * fs)))
    if y.size < n:
        return np.asarray([], dtype=float), np.asarray([], dtype=float), np.asarray([], dtype=float)
    win = np.hanning(n)
    lag_min = max(1, int(fs / max(config.ap_max_pitch, 1.0)))
    lag_max = max(lag_min + 1, int(fs / max(config.ap_min_pitch, 1.0)))
    t_out, f_out, s_out = [], [], []
    for i0 in range(0, y.size - n + 1, h):
        seg = (y[i0:i0 + n] - np.mean(y[i0:i0 + n])) * win
        ac = np.correlate(seg, seg, mode="full")[n - 1:]
        denom = max(float(ac[0]), 1e-12)
        lag_max2 = min(lag_max, ac.size - 1)
        if lag_max2 <= lag_min:
            f, strength = np.nan, 0.0
        else:
            loc = lag_min + int(np.argmax(ac[lag_min:lag_max2]))
            strength = float(ac[loc] / denom)
            f = fs / loc if loc > 0 and strength > 0.25 else np.nan
            if not (config.ap_min_pitch <= f <= config.ap_max_pitch):
                f = np.nan
        t_out.append((i0 + n / 2) / fs)
        f_out.append(f)
        s_out.append(max(0.0, strength))
    return np.asarray(t_out, dtype=float), np.asarray(f_out, dtype=float), np.asarray(s_out, dtype=float)


def _median_f0_in_window(t: np.ndarray, f0: np.ndarray, t0: float, t1: float) -> float:
    t = np.asarray(t, dtype=float)
    f0 = np.asarray(f0, dtype=float)
    mask = (t >= float(t0)) & (t <= float(t1)) & np.isfinite(f0) & (f0 > 0)
    vals = f0[mask]
    return float(np.nanmedian(vals)) if vals.size else np.nan


def _arff_make_f0y(y: np.ndarray, fs: int, f0_track: np.ndarray, config: RFFConfig) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Create MATLAB-style F0-focused filtered waveform aRFF.f0y."""
    y = np.asarray(y, dtype=float).reshape(-1)
    peak = float(np.nanmax(np.abs(y))) if y.size else 0.0
    y_norm = y / max(peak, 1e-12)
    valid = np.asarray(f0_track, dtype=float)
    valid = valid[np.isfinite(valid) & (valid > 0)]
    if valid.size:
        qlo = float(np.nanpercentile(valid, 10))
        qhi = float(np.nanpercentile(valid, 90))
        med = float(np.nanmedian(valid))
    else:
        med = 180.0
        qlo = med / 1.2
        qhi = med * 1.2
    band_factor = 2.0 ** (float(config.ap_band_st) / 12.0)
    f_lo = max(float(config.ap_min_pitch), qlo / band_factor)
    f_hi = min(float(config.ap_max_pitch), qhi * band_factor)
    if not (np.isfinite(f_lo) and np.isfinite(f_hi) and f_hi > f_lo):
        f_lo = max(float(config.ap_min_pitch), med / band_factor)
        f_hi = min(float(config.ap_max_pitch), med * band_factor)
    if f_hi <= f_lo:
        f_lo = max(20.0, med * 0.70)
        f_hi = min(0.48 * fs, med * 1.45)
    f0y = _safe_bandpass_filter(y_norm, fs, f_lo, f_hi, order=2)
    return f0y, {"f0y_band_lo_hz": f_lo, "f0y_band_hi_hz": f_hi, "f0_median_hz": med}


def _local_extremum_with_edge_extension(f0y: np.ndarray, start: int, end: int, kind: str, side: str, lower: int, upper: int) -> int:
    f0y = np.asarray(f0y, dtype=float).reshape(-1)
    n = f0y.size
    start = int(max(0, min(n - 1, start)))
    end = int(max(0, min(n - 1, end)))
    lower = int(max(0, min(n - 1, lower)))
    upper = int(max(0, min(n - 1, upper)))
    if end < start:
        start, end = end, start
    if end <= start:
        return start
    seg = f0y[start:end + 1]
    if kind == "peak":
        loc = int(np.nanargmax(seg)) + start
        if loc == start and side == "off":
            while loc - 1 >= lower and f0y[loc - 1] >= f0y[loc]:
                loc -= 1
        elif loc == end and side == "on":
            while loc + 1 <= upper and f0y[loc + 1] >= f0y[loc]:
                loc += 1
    else:
        loc = int(np.nanargmin(seg)) + start
        if loc == start and side == "off":
            while loc - 1 >= lower and f0y[loc - 1] <= f0y[loc]:
                loc -= 1
        elif loc == end and side == "on":
            while loc + 1 <= upper and f0y[loc + 1] <= f0y[loc]:
                loc += 1
    return int(max(lower, min(upper, loc)))


def _repair_landmarks_with_local_extrema(landmarks: np.ndarray, f0y: np.ndarray, fs: int, t0_samp: float, kind: str) -> np.ndarray:
    """Approximate MATLAB checking_cycles: fill long cycles and remove very short cycles."""
    if landmarks is None:
        return np.asarray([], dtype=int)
    arr = np.unique(np.asarray(landmarks, dtype=int))
    arr = arr[(arr >= 0) & (arr < len(f0y))]
    if arr.size < 2 or not np.isfinite(t0_samp) or t0_samp <= 0:
        return arr

    # Fill gaps longer than about 4/3 T0 using local extrema, as in checking_cycles.m.
    changed = True
    for _ in range(3):
        if not changed:
            break
        changed = False
        arr = np.unique(np.sort(arr))
        additions = []
        for a, b in zip(arr[:-1], arr[1:]):
            gap = b - a
            if gap > (4.0 / 3.0) * t0_samp:
                n_add = int(round(gap / t0_samp)) - 1
                n_add = max(1, min(n_add, 3))
                cuts = np.linspace(a, b, n_add + 2, dtype=int)
                for j in range(n_add):
                    s = int(cuts[j])
                    e = int(cuts[j + 2]) if (j + 2) < len(cuts) else int(b)
                    if e <= s:
                        continue
                    loc = _local_extremum_with_edge_extension(f0y, s, e, kind, "on", s, e)
                    if a < loc < b:
                        additions.append(loc)
        if additions:
            arr = np.unique(np.r_[arr, additions])
            changed = True

    # Remove cycles shorter than about 2/3 T0. Keep the stronger extremum.
    arr = np.unique(np.sort(arr))
    keep = np.ones(arr.size, dtype=bool)
    i = 0
    while i < arr.size - 1:
        if not keep[i]:
            i += 1
            continue
        j = i + 1
        while j < arr.size and not keep[j]:
            j += 1
        if j >= arr.size:
            break
        if (arr[j] - arr[i]) < (2.0 / 3.0) * t0_samp:
            vi = f0y[arr[i]]
            vj = f0y[arr[j]]
            if kind == "peak":
                # drop lower peak
                keep[i if vi < vj else j] = False
            else:
                # drop shallower trough
                keep[i if vi > vj else j] = False
        i += 1
    return arr[keep]


def _collect_arff_landmarks(f0y: np.ndarray, fs: int, edge_time: float, side: str, f0_hz: float, config: RFFConfig, kind: str) -> np.ndarray:
    """Cycle-by-cycle peak/trough search on F0-filtered waveform, AP-style."""
    if not (np.isfinite(f0_hz) and f0_hz > 0):
        return np.asarray([], dtype=float)
    n = len(f0y)
    edge = int(round(float(edge_time) * fs))
    edge = int(max(0, min(n - 1, edge)))
    t0 = float(fs) / float(f0_hz)
    step = int(max(2, round(t0)))
    skip = int(max(1, round(float(config.ap_edge_skip_s) * fs)))
    search_n = int(max(12, config.ap_search_cycles))
    pad = int(round(max(0.50, (search_n + 4) / max(f0_hz, 1.0)) * fs))
    lower = max(0, edge - pad)
    upper = min(n - 1, edge + pad)
    out: List[int] = []

    if side == "off":
        right = max(lower + 1, edge - skip)
        for _ in range(search_n + 4):
            left = max(lower, right - step)
            if right <= left:
                break
            loc = _local_extremum_with_edge_extension(f0y, left, right, kind, side, lower, upper)
            if loc < edge:
                out.append(loc)
            right = loc - max(1, int(0.65 * step))
            if right <= lower + step // 2:
                break
    else:
        left = min(upper - 1, edge + skip)
        for _ in range(search_n + 4):
            right = min(upper, left + step)
            if right <= left:
                break
            loc = _local_extremum_with_edge_extension(f0y, left, right, kind, side, lower, upper)
            if loc > edge:
                out.append(loc)
            left = loc + max(1, int(0.65 * step))
            if left >= upper - step // 2:
                break

    arr = _repair_landmarks_with_local_extrema(np.asarray(out, dtype=int), f0y, fs, t0, kind)
    times = np.asarray(arr, dtype=float) / float(fs)
    if side == "off":
        times = times[times < edge_time]
    else:
        times = times[times > edge_time]
    return np.asarray(np.unique(np.sort(times)), dtype=float)


def _window_autocorr_quality(y: np.ndarray, fs: int, landmarks: np.ndarray, config: RFFConfig) -> Tuple[float, float, float]:
    """Return max autocorrelation, dominant pitch, and mean F0 for selected cycles."""
    landmarks = np.asarray(landmarks, dtype=float)
    if landmarks.size < 2:
        return np.nan, np.nan, np.nan
    idx = np.asarray(np.round(landmarks * fs), dtype=int)
    idx = idx[(idx >= 0) & (idx < len(y))]
    if idx.size < 2 or idx[-1] <= idx[0]:
        return np.nan, np.nan, np.nan
    seg = np.asarray(y[idx[0]:idx[-1] + 1], dtype=float)
    if seg.size < 8:
        return np.nan, np.nan, np.nan
    seg = seg - np.mean(seg)
    if np.max(np.abs(seg)) <= 1e-12:
        return np.nan, np.nan, np.nan
    ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
    ac = ac / max(abs(ac[0]), 1e-12)
    lag_min = max(1, int(np.floor(fs / max(config.ap_max_pitch, 1.0))))
    lag_max = min(len(ac) - 1, int(np.ceil(fs / max(config.ap_min_pitch, 1.0))))
    if lag_max <= lag_min:
        return np.nan, np.nan, np.nan
    local = ac[lag_min:lag_max + 1]
    k = int(np.argmax(local)) + lag_min
    maxacf = float(ac[k])
    dompitch = float(fs / k) if k > 0 else np.nan
    periods = np.diff(landmarks)
    freqs = periods_to_freq(periods)
    meanf0 = float(np.nanmean(freqs)) if np.any(np.isfinite(freqs)) else np.nan
    return maxacf, dompitch, meanf0


def _apply_arff_output_rejections(rff: Optional[np.ndarray], landmarks: np.ndarray, y: np.ndarray, fs: int, side: str, config: RFFConfig) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Apply AP/aRFF-style QC with v4 soft sharp-transition handling.

    MATLAB aRFF-AP rejects sharp transitions as a hard rule. In this ROI-guided
    microphone implementation, the same rule over-rejected the corpus because
    manual ROI boundaries and filtered-waveform landmarks are not bit-for-bit
    MATLAB/Auditory-SWIPE. Therefore v4 keeps the sharp-transition test as a
    QC warning by default and rejects only catastrophic excursions.
    """
    details: Dict[str, Any] = {}
    if rff is None or np.asarray(rff).shape != (10,) or not np.all(np.isfinite(rff)):
        return None, "too few periodic cycles", details

    rff = np.asarray(rff, dtype=float)
    diffs = np.abs(np.diff(rff))
    thresh = ARFF_OFF_DIFF_THRESH_ST if side == "off" else ARFF_ON_DIFF_THRESH_ST
    sharp_mask = diffs > thresh
    hard_mask = diffs > (float(config.ap_sharp_hard_mult) * thresh)
    abs_hard = np.nanmax(np.abs(rff)) > float(config.ap_rff_abs_hard_limit_st)
    warning_parts: List[str] = []
    details.update({
        "rff_diffs_st": diffs.tolist(),
        "sharp_transition_thresholds_st": thresh.tolist(),
        "sharp_transition_cycles": np.where(sharp_mask)[0].astype(int).tolist(),
        "sharp_transition_soft_qc": bool(np.any(sharp_mask)),
        "sharp_transition_hard_qc": bool(np.any(hard_mask) or abs_hard),
        "ap_sharp_reject": bool(config.ap_sharp_reject),
        "ap_sharp_hard_mult": float(config.ap_sharp_hard_mult),
        "ap_rff_abs_hard_limit_st": float(config.ap_rff_abs_hard_limit_st),
    })

    if np.any(hard_mask) or abs_hard:
        return None, "catastrophic sharp transition", details
    if np.any(sharp_mask):
        if bool(config.ap_sharp_reject):
            return None, "sharp transition", details
        warning_parts.append("sharp transition warning")

    maxacf, dompitch, meanf0 = _window_autocorr_quality(y, fs, landmarks, config)
    details.update({"autocorr_max": maxacf, "dompitch_hz": dompitch, "meanf0_hz": meanf0})
    if np.isfinite(dompitch) and np.isfinite(meanf0) and meanf0 > 0:
        if (dompitch > (2.0 ** (6.0 / 12.0)) * meanf0) or (dompitch < (2.0 ** (-6.0 / 12.0)) * meanf0):
            return None, "glottalized / wrong dominant pitch", details
    if np.isfinite(maxacf) and maxacf <= float(config.ap_autocorr_min):
        return None, "aperiodic or irregular", details

    return rff, "; ".join(warning_parts), details


def _score_arff_candidate_window(w: np.ndarray, f0y: np.ndarray, fs: int, side: str, edge: float, config: RFFConfig) -> Tuple[float, Dict[str, Any]]:
    """Score a candidate 11-landmark AP window.

    v5 selected the 11 landmarks closest to the /f/ edge and then merely warned
    about sharp transitions. In this corpus that retained many transition-
    contaminated ON1/OFF10 values. v6 scores all possible 11-cycle windows and
    prefers the earliest/nearest window that is also internally periodic and has
    a smooth RFF trajectory. This is still ROI-guided and does not force values
    toward Vojtech norms; it only avoids obviously unstable cycle windows.
    """
    w = np.asarray(w, dtype=float)
    per = np.diff(w)
    med = float(np.nanmedian(per)) if per.size else np.nan
    details: Dict[str, Any] = {}
    if not (np.isfinite(med) and med > 0):
        return 1e9, {"reason": "invalid median period"}

    freqs = periods_to_freq(per)
    base = freqs[0] if side == "off" else freqs[-1]
    rff = hz_to_st(freqs, base) if np.isfinite(base) and base > 0 else np.full(10, np.nan)
    if rff.shape != (10,) or not np.all(np.isfinite(rff)):
        return 1e9, {"reason": "invalid RFF"}

    thresh = ARFF_OFF_DIFF_THRESH_ST if side == "off" else ARFF_ON_DIFF_THRESH_ST
    diffs = np.abs(np.diff(rff))
    sharp_excess = np.maximum(0.0, diffs / np.maximum(thresh, 1e-9) - 1.0)
    max_abs = float(np.nanmax(np.abs(rff)))
    plausible = float(np.mean((per >= config.ap_period_tol_low * med) & (per <= config.ap_period_tol_high * med)))
    period_cv = float(np.nanstd(per) / med) if med > 0 else 999.0
    idx = np.asarray(np.clip(np.round(w * fs), 0, len(f0y) - 1), dtype=int)
    amp = float(np.nanmedian(np.abs(f0y[idx]))) if idx.size else 0.0
    edge_dist = abs(edge - w[-1]) if side == "off" else abs(w[0] - edge)
    edge_cycles = float(edge_dist / med)

    # Transition-cycle penalty: detects the common failure mode found in v5.
    # For onset, a very long first period makes ON1 strongly negative.
    # For offset, a very long final period makes OFF10 extremely negative.
    if side == "on":
        edge_period_ratio = per[0] / med
        early_rff_penalty = max(0.0, -float(rff[0]) - 1.5) / 3.0
    else:
        edge_period_ratio = per[-1] / med
        early_rff_penalty = max(0.0, -float(rff[-1]) - 3.0) / 3.0
    edge_period_penalty = max(0.0, edge_period_ratio - 1.25)

    # Candidate score. The edge-distance term is deliberately small: v6 prefers
    # the nearest stable window, not the nearest unstable window.
    score = (
        0.15 * edge_cycles
        + 2.00 * period_cv
        + 4.00 * float(np.sum(sharp_excess))
        + 3.00 * max(0.0, 1.0 - plausible)
        + 2.50 * edge_period_penalty
        + 2.00 * early_rff_penalty
        + 0.40 * max(0.0, max_abs - 8.0)
        - 0.05 * amp
    )
    details.update({
        "score": float(score),
        "edge_cycles": edge_cycles,
        "period_cv": period_cv,
        "period_plausible_fraction": plausible,
        "sharp_excess_sum": float(np.sum(sharp_excess)),
        "edge_period_ratio": float(edge_period_ratio),
        "edge_period_penalty": float(edge_period_penalty),
        "early_rff_penalty": float(early_rff_penalty),
        "max_abs_rff_st": max_abs,
        "median_abs_f0y_amp": amp,
        "candidate_rff_st": rff.tolist(),
        "candidate_periods_s": per.tolist(),
    })
    return float(score), details


def _select_plausible_landmark_window(landmarks: np.ndarray, f0y: np.ndarray, fs: int, side: str, edge_time: float, config: RFFConfig) -> np.ndarray:
    """Choose an exact 11-landmark window with optional strict adjacency.

    v14/v15 default to the edge-most eligible window: the last 11 OFF landmarks
    or first 11 ON landmarks. Adaptive scoring remains available only when
    strict boundary adjacency is explicitly disabled.
    """
    lm = np.asarray(landmarks, dtype=float)
    lm = np.unique(np.sort(lm[np.isfinite(lm)]))
    if lm.size < 11:
        return lm
    edge = float(edge_time)
    candidates: List[Tuple[float, float, float, np.ndarray, Dict[str, Any]]] = []
    eligible_windows: List[np.ndarray] = []
    for i in range(0, lm.size - 10):
        w = lm[i:i + 11]
        if side == "off" and not np.all(w < edge):
            continue
        if side == "on" and not np.all(w > edge):
            continue
        eligible_windows.append(np.asarray(w, dtype=float))
        score, details = _score_arff_candidate_window(w, f0y, fs, side, edge, config)
        if not np.isfinite(score):
            continue
        per = np.diff(w)
        med = float(np.nanmedian(per)) if per.size else np.nan
        edge_dist = abs(edge - w[-1]) if side == "off" else abs(w[0] - edge)
        edge_cycles = float(edge_dist / med) if np.isfinite(med) and med > 0 else 999.0
        candidates.append((score, edge_cycles, -float(details.get("period_plausible_fraction", 0.0)), w, details))
    if not eligible_windows:
        return lm[-11:] if side == "off" else lm[:11]
    if bool(config.strict_boundary_adjacency):
        return np.asarray(eligible_windows[-1] if side == "off" else eligible_windows[0], dtype=float)
    if not candidates:
        return np.asarray(eligible_windows[-1] if side == "off" else eligible_windows[0], dtype=float)
    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    return np.asarray(candidates[0][3], dtype=float)


def _rff_from_selected_landmarks(selected: np.ndarray, side: str, config: RFFConfig) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    selected = np.asarray(selected, dtype=float)
    details: Dict[str, Any] = {"selected_landmarks_s": selected.tolist()}
    if selected.size < 11:
        return None, details
    selected = np.unique(np.sort(selected))
    if side == "off":
        selected = selected[-11:]
    else:
        selected = selected[:11]
    periods = np.diff(selected)
    freqs = periods_to_freq(periods)
    details.update({"periods_s": periods.tolist(), "freqs_hz": freqs.tolist(), "selected_landmarks_s": selected.tolist()})
    if periods.size != 10 or not np.all(np.isfinite(freqs)):
        return None, details
    base = freqs[0] if side == "off" else freqs[9]
    if not (np.isfinite(base) and base > 0):
        return None, details
    rff = hz_to_st(freqs, base)
    details["rff_st"] = rff.tolist()
    return rff if rff.shape == (10,) and np.all(np.isfinite(rff)) else None, details


def _arff_trace_for_kind(y: np.ndarray, f0y: np.ndarray, fs: int, edge_time: float, side: str, f0_hz: float, kind: str, config: RFFConfig) -> Dict[str, Any]:
    raw_landmarks = _collect_arff_landmarks(f0y, fs, edge_time, side, f0_hz, config, kind)
    selected = _select_plausible_landmark_window(raw_landmarks, f0y, fs, side, edge_time, config)
    rff, calc_details = _rff_from_selected_landmarks(selected, side, config)
    rff, reject, rej_details = _apply_arff_output_rejections(rff, selected, y, fs, side, config)
    return {
        "kind": kind,
        "rff": rff,
        "valid": rff is not None,
        "reject": reject,
        "raw_landmarks_s": raw_landmarks.tolist(),
        "selected_landmarks_s": np.asarray(selected, dtype=float).tolist(),
        "calc_details": calc_details,
        "rejection_details": rej_details,
    }


def _choose_arff_peak_or_trough(peak: Dict[str, Any], trough: Dict[str, Any], side: str) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    peak_valid = bool(peak.get("valid"))
    trough_valid = bool(trough.get("valid"))
    chosen = None
    reason = ""
    if trough_valid and not peak_valid:
        chosen = trough
        reason = "trough valid, peak invalid"
    elif peak_valid and not trough_valid:
        chosen = peak
        reason = "peak valid, trough invalid"
    elif peak_valid and trough_valid:
        # v4: if one trace is clean and the other only passed with a QC warning,
        # prefer the clean trace. If both are clean/warned, fall back to the
        # MATLAB RFFoutput endpoint-order logic.
        p_warn = bool(str(peak.get("reject", "")).strip())
        t_warn = bool(str(trough.get("reject", "")).strip())
        if p_warn and not t_warn:
            chosen = trough
            reason = "trough clean, peak has QC warning"
        elif t_warn and not p_warn:
            chosen = peak
            reason = "peak clean, trough has QC warning"
        else:
            p_lm = np.asarray(peak.get("selected_landmarks_s", []), dtype=float)
            t_lm = np.asarray(trough.get("selected_landmarks_s", []), dtype=float)
            if side == "off":
                # MATLAB RFFoutput chooses trough if the final trough is closer to /f/ than the final peak.
                if t_lm.size and p_lm.size and t_lm[-1] > p_lm[-1]:
                    chosen = trough
                    reason = "trough endpoint closer to offset edge"
                else:
                    chosen = peak
                    reason = "peak endpoint closer/equal to offset edge"
            else:
                # MATLAB RFFoutput chooses trough if the first trough occurs before the first peak.
                if t_lm.size and p_lm.size and t_lm[0] < p_lm[0]:
                    chosen = trough
                    reason = "trough starts before peak at onset"
                else:
                    chosen = peak
                    reason = "peak starts before/equal to trough at onset"
    else:
        return None, "; ".join([x for x in [peak.get("reject", ""), trough.get("reject", "")] if x]) or "too few periodic cycles", {"peak": peak, "trough": trough, "chosen": "none"}
    return np.asarray(chosen.get("rff"), dtype=float), str(chosen.get("reject", "")), {"peak": peak, "trough": trough, "chosen": chosen.get("kind"), "choice_reason": reason}


def _compute_arff_like_rff(
    wav_path: str,
    subject: str,
    token: str,
    rep: int,
    fric_start: float,
    fric_end: float,
    config: RFFConfig,
    method_name: str,
    use_cepstral_pitch: bool = False,
) -> TraceResult:
    y, fs = read_audio(wav_path)
    y = normalize_audio_for_display(y)
    dur = len(y) / fs
    fric_start = float(max(0.0, min(dur, fric_start)))
    fric_end = float(max(fric_start, min(dur, fric_end)))

    t_pitch, f0_track, support = _arff_pitch_track(y, fs, config, use_cepstral=use_cepstral_pitch)
    off_f0 = _median_f0_in_window(t_pitch, f0_track, max(0.0, fric_start - 0.25), max(0.0, fric_start - 0.025))
    on_f0 = _median_f0_in_window(t_pitch, f0_track, min(dur, fric_end + 0.025), min(dur, fric_end + 0.25))
    global_f0 = float(np.nanmedian(f0_track[np.isfinite(f0_track) & (f0_track > 0)])) if np.any(np.isfinite(f0_track) & (f0_track > 0)) else np.nan
    if not np.isfinite(off_f0):
        off_f0 = global_f0
    if not np.isfinite(on_f0):
        on_f0 = global_f0

    f0y, f0y_details = _arff_make_f0y(y, fs, f0_track, config)
    # MATLAB shifts the fricative midpoint to a local minimum in smoothed |f0y|.
    roi_i0 = max(0, int(round(fric_start * fs)))
    roi_i1 = min(len(f0y), int(round(fric_end * fs)))
    if roi_i1 > roi_i0 + 2:
        sm_abs = _moving_median_1d(np.abs(f0y), max(3, int(round(fs / 20))))
        center_idx = roi_i0 + int(np.nanargmin(sm_abs[roi_i0:roi_i1]))
    else:
        center_idx = int(round(0.5 * (fric_start + fric_end) * fs))
    fric_center = center_idx / float(fs)

    # Use manually supplied ROI edges for the actual offset/onset boundaries.
    off_peak = _arff_trace_for_kind(y, f0y, fs, fric_start, "off", off_f0, "peak", config)
    off_trough = _arff_trace_for_kind(y, f0y, fs, fric_start, "off", off_f0, "trough", config)
    on_peak = _arff_trace_for_kind(y, f0y, fs, fric_end, "on", on_f0, "peak", config)
    on_trough = _arff_trace_for_kind(y, f0y, fs, fric_end, "on", on_f0, "trough", config)

    off_rff, off_rej, off_debug = _choose_arff_peak_or_trough(off_peak, off_trough, "off")
    on_rff, on_rej, on_debug = _choose_arff_peak_or_trough(on_peak, on_trough, "on")

    off_chosen = str(off_debug.get("chosen", "") or "")
    on_chosen = str(on_debug.get("chosen", "") or "")
    off_trace = off_debug.get(off_chosen, {}) if off_chosen in {"peak", "trough"} else {}
    on_trace = on_debug.get(on_chosen, {}) if on_chosen in {"peak", "trough"} else {}
    off_lm = np.asarray(off_trace.get("selected_landmarks_s", []), dtype=float)
    on_lm = np.asarray(on_trace.get("selected_landmarks_s", []), dtype=float)

    off_gate = {
        "selected_landmarks_s": off_lm.tolist(),
        "candidate_landmarks_s": np.asarray(off_trace.get("raw_landmarks_s", []), dtype=float).tolist(),
        "enforce_boundary_adjacency": bool(config.strict_boundary_adjacency),
    }
    on_gate = {
        "selected_landmarks_s": on_lm.tolist(),
        "candidate_landmarks_s": np.asarray(on_trace.get("raw_landmarks_s", []), dtype=float).tolist(),
        "enforce_boundary_adjacency": bool(config.strict_boundary_adjacency),
    }
    off_rff, off_rej, off_gate = _apply_hard_landmark_gate(
        off_rff, off_rej, off_gate, fric_start, "off", config
    )
    on_rff, on_rej, on_gate = _apply_hard_landmark_gate(
        on_rff, on_rej, on_gate, fric_end, "on", config
    )
    off_debug["cycle_qc"] = off_gate
    on_debug["cycle_qc"] = on_gate

    return TraceResult(
        method=method_name,
        subject=subject,
        filename=os.path.basename(wav_path),
        filepath=wav_path,
        token=token,
        rep=rep,
        fric_start=fric_start,
        fric_end=fric_end,
        off_rff=off_rff,
        on_rff=on_rff,
        off_valid=off_rff is not None,
        on_valid=on_rff is not None,
        off_reject=off_rej,
        on_reject=on_rej,
        n_off_landmarks=int(off_lm.size) if off_rff is not None else 0,
        n_on_landmarks=int(on_lm.size) if on_rff is not None else 0,
        debug={
            "implementation_stamp": SCRIPT_VERSION,
            "algorithm_family": "arff_ap_like_f0_filtered_peak_trough_strict_boundary_v14_frozen_in_v15",
            "pitch_source": "cepstral" if use_cepstral_pitch else "praat_ac_or_ac_fallback",
            "off_f0_hz": off_f0,
            "on_f0_hz": on_f0,
            "global_f0_hz": global_f0,
            "fric_center_local_min_f0y_s": fric_center,
            "f0y_details": f0y_details,
            "off_debug": off_debug,
            "on_debug": on_debug,
        },
    )


def compute_ap_roi_rff(
    wav_path: str,
    subject: str,
    token: str,
    rep: int,
    fric_start: float,
    fric_end: float,
    config: RFFConfig,
) -> TraceResult:
    """ROI-guided aRFF-AP-like method, using F0-filtered acoustic peak/trough landmarks."""
    return _compute_arff_like_rff(
        wav_path=wav_path,
        subject=subject,
        token=token,
        rep=rep,
        fric_start=fric_start,
        fric_end=fric_end,
        config=config,
        method_name="RFF_AP_ROI",
        use_cepstral_pitch=False,
    )


# =============================================================================
# Method 4: robust cepstral-assisted classical RFF (v21; tracker inherited from v17)
# =============================================================================

def median_filter_nan(x: np.ndarray, k: int = 3) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if k <= 1 or x.size == 0:
        return x.copy()
    out = x.copy()
    pad = k // 2
    for i in range(x.size):
        finite = x[max(0, i - pad):min(x.size, i + pad + 1)]
        finite = finite[np.isfinite(finite)]
        out[i] = float(np.median(finite)) if finite.size else np.nan
    return out


def parabolic_interp(y: np.ndarray, i: int) -> float:
    if i <= 0 or i >= len(y) - 1:
        return float(i)
    a, b, c = float(y[i - 1]), float(y[i]), float(y[i + 1])
    denom = a - 2.0 * b + c
    if not np.isfinite(denom) or abs(denom) < 1e-12:
        return float(i)
    return float(i + np.clip(0.5 * (a - c) / denom, -0.5, 0.5))


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + math.exp(-float(np.clip(x, -30.0, 30.0)))))


def _local_maxima_1d(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size < 3:
        return np.asarray([], dtype=int)
    return np.where(np.isfinite(x[1:-1]) & (x[1:-1] >= x[:-2]) & (x[1:-1] > x[2:]))[0] + 1


def _cepstral_frame_candidates(seg: np.ndarray, fs: int, config: RFFConfig) -> List[Dict[str, float]]:
    """Return several F0 hypotheses with scale-free cepstral/AC support.

    v16 gated a single cepstral peak by its raw amplitude. Raw cepstral values
    depend on frame length and signal scaling, so clean periodic frames could be
    rejected while noisy frames passed. v17 uses regression-normalized peak
    height, normalized autocorrelation, octave evidence and multiple candidates.
    """
    raw = np.asarray(seg, dtype=float).reshape(-1)
    if raw.size < 64:
        return []
    raw = raw - float(np.mean(raw))
    rms = float(np.sqrt(np.mean(raw * raw)))
    if not np.isfinite(rms) or rms < 1e-5:
        return []
    x_ac = (raw / max(rms, 1e-12)) * np.hanning(raw.size)
    x = raw / max(rms, 1e-12)
    if x.size >= 2:
        x = np.r_[x[0], x[1:] - 0.97 * x[:-1]]
    x = x * np.hanning(x.size)

    nfft = 1 << int(math.ceil(math.log2(max(512, 4 * x.size))))
    eps = 1e-12
    spectrum_power = np.square(np.abs(np.fft.rfft(x_ac, n=nfft)))
    positive_power = spectrum_power[1:]
    spectral_flatness = float(
        np.exp(np.mean(np.log(positive_power + eps))) / max(float(np.mean(positive_power)), eps)
    ) if positive_power.size else 1.0
    spectral_tonality = float(np.clip((0.78 - spectral_flatness) / 0.68, 0.0, 1.0))
    cep = np.fft.irfft(np.log(np.abs(np.fft.rfft(x, n=nfft)) + eps), n=nfft)
    q_lo = max(2, int(math.floor(fs / max(config.f0_ceiling, 1.0))))
    q_hi = min(nfft // 2 - 2, int(math.ceil(fs / max(config.f0_floor, 1.0))))
    if q_hi <= q_lo + 3:
        return []
    q = np.arange(q_lo, q_hi + 1, dtype=float)
    c = np.asarray(cep[q_lo:q_hi + 1], dtype=float)
    try:
        base = np.polyval(np.polyfit(q, c, 1), q)
    except Exception:
        base = np.full_like(c, float(np.nanmedian(c)))
    resid = c - base
    med = float(np.nanmedian(resid))
    mad = float(np.nanmedian(np.abs(resid - med)))
    scale = max(1.4826 * mad, float(np.nanstd(resid)) * 0.35, 1e-8)
    z = (resid - med) / scale

    # AC is intentionally calculated from the non-pre-emphasized frame. Using
    # the differentiated signal (as v16 effectively did) suppresses low-F0
    # periodicity and favors higher harmonics, especially around 75--100 Hz.
    # FFT autocorrelation is mathematically equivalent for the non-negative
    # lags used here and avoids an O(N^2) cost at every frame/resolution.
    ac = np.fft.irfft(np.square(np.abs(np.fft.rfft(x_ac, n=nfft))), n=nfft)[:x_ac.size]
    ac = ac / max(float(ac[0]), 1e-12)
    overlap = np.maximum(1.0, x_ac.size - np.arange(ac.size, dtype=float))
    ac = np.clip(ac * (x_ac.size / overlap), -1.0, 1.0)
    ac_slice = np.asarray(ac[q_lo:min(q_hi + 1, ac.size)], dtype=float)

    cep_idx = _local_maxima_1d(z)
    ac_idx = _local_maxima_1d(ac_slice)
    pool: List[int] = []
    if cep_idx.size:
        pool.extend(cep_idx[np.argsort(z[cep_idx])[-max(8, config.cep_max_candidates * 2):]].tolist())
    if ac_idx.size:
        pool.extend(ac_idx[np.argsort(ac_slice[ac_idx])[-max(6, config.cep_max_candidates):]].tolist())
    if not pool:
        pool = [int(np.nanargmax(z))]

    power_db = 10.0 * np.log10(np.square(c) + eps)
    try:
        power_base = np.polyval(np.polyfit(q, power_db, 1), q)
    except Exception:
        power_base = np.full_like(power_db, float(np.nanmedian(power_db)))

    out: List[Dict[str, float]] = []
    for j in sorted(set(int(v) for v in pool if 0 <= int(v) < c.size)):
        lag_index = q_lo + j
        lag_refined = q_lo + parabolic_interp(z, j)
        f0 = float(fs / max(lag_refined, 1e-9))
        if not (config.f0_floor <= f0 <= config.f0_ceiling):
            continue
        ac_strength = float(ac[lag_index]) if lag_index < ac.size else 0.0
        peak_z = float(z[j])
        cpp_like_db = float(power_db[j] - power_base[j])
        cep_support = _sigmoid((peak_z - 1.25) / 0.90)
        ac_support = float(np.clip((ac_strength - 0.05) / 0.80, 0.0, 1.0))
        quality = 0.46 * cep_support + 0.34 * ac_support + 0.20 * spectral_tonality

        # A periodic signal naturally has strong AC peaks at 2T, 3T, ... . A
        # longer-lag candidate must therefore beat its half-lag alternative,
        # rather than winning merely because overlap correction made 2T a few
        # percent higher. This is the explicit subharmonic/octave guard.
        octave_ambiguity = 0.0
        half = int(round(lag_index / 2.0))
        if half >= q_lo and half < ac.size:
            half_strength = float(ac[half])
            if half_strength >= 0.90 * max(ac_strength, 1e-6):
                octave_ambiguity = float(np.clip(half_strength / max(ac_strength, 1e-6), 0.0, 1.5))
                quality *= 0.76
        # Conversely, reject an upper harmonic when a valid integer-multiple
        # lag carries clearly stronger periodic support. The >12% margin avoids
        # punishing a correct F0 merely because 2T is also an AC maximum.
        harmonic_evidence = 0.0
        for multiple in (2, 3, 4, 5):
            longer = multiple * lag_index
            if longer > q_hi or longer >= ac.size:
                break
            ratio = float(ac[longer] / max(ac_strength, 1e-6))
            if ratio > harmonic_evidence:
                harmonic_evidence = ratio
        if harmonic_evidence > 1.12:
            quality *= 0.55
        harmonic_sum = 0.0
        harmonic_weight = 0.0
        for harmonic in range(1, 9):
            hz = harmonic * f0
            if hz >= 0.48 * fs:
                break
            bin_pos = hz * nfft / fs
            b = int(round(bin_pos))
            if 1 <= b < spectrum_power.size - 1:
                weight = 1.0 / math.sqrt(harmonic)
                harmonic_sum += weight * float(np.sum(spectrum_power[b - 1:b + 2]))
                harmonic_weight += weight
        harmonic_score = harmonic_sum / max(harmonic_weight, 1e-12)
        out.append({
            "f0_hz": f0,
            "quality": float(np.clip(quality, 0.0, 1.0)),
            "cep_peak_z": peak_z,
            "cpp_like_db": cpp_like_db,
            "ac_strength": ac_strength,
            "octave_ambiguity": octave_ambiguity,
            "upper_harmonic_evidence": harmonic_evidence,
            "spectral_harmonic_score": harmonic_score,
            "frame_rms": rms,
            "spectral_flatness": spectral_flatness,
        })

    if out:
        max_harmonic_score = max(float(d.get("spectral_harmonic_score", 0.0)) for d in out)
        for cand in out:
            relative_harmonic = float(cand.get("spectral_harmonic_score", 0.0)) / max(max_harmonic_score, 1e-12)
            cand["spectral_harmonic_support"] = relative_harmonic
            cand["quality"] = float(np.clip(0.82 * cand["quality"] + 0.18 * relative_harmonic, 0.0, 1.0))
    out.sort(key=lambda d: (d["quality"], d["cep_peak_z"], d["ac_strength"]), reverse=True)
    merged: List[Dict[str, float]] = []
    for cand in out:
        if any(abs(math.log2(cand["f0_hz"] / old["f0_hz"])) < 0.045 for old in merged):
            continue
        merged.append(cand)
        if len(merged) >= int(config.cep_max_candidates):
            break
    return merged


def _merge_multiresolution_candidates(groups: Sequence[Sequence[Mapping[str, float]]], max_n: int) -> List[Dict[str, float]]:
    merged: List[Dict[str, float]] = []
    for group in groups:
        for src in group:
            cand = dict(src)
            match = next((m for m in merged if abs(math.log2(cand["f0_hz"] / m["f0_hz"])) < 0.055), None)
            if match is None:
                cand["resolution_votes"] = 1.0
                merged.append(cand)
            else:
                w0 = max(float(match.get("quality", 0.0)), 0.05)
                w1 = max(float(cand.get("quality", 0.0)), 0.05)
                match["f0_hz"] = float((w0 * match["f0_hz"] + w1 * cand["f0_hz"]) / (w0 + w1))
                for key in ("quality", "cep_peak_z", "cpp_like_db", "ac_strength", "frame_rms"):
                    match[key] = max(float(match.get(key, -np.inf)), float(cand.get(key, -np.inf)))
                match["resolution_votes"] = float(match.get("resolution_votes", 1.0) + 1.0)
    for cand in merged:
        votes = float(cand.get("resolution_votes", 1.0))
        cand["quality"] = float(np.clip(cand["quality"] + 0.035 * (votes - 1.0), 0.0, 1.0))
    merged.sort(key=lambda d: (d["quality"], d.get("resolution_votes", 1.0)), reverse=True)
    return merged[:max(1, int(max_n))]


def _viterbi_cepstral_path(frames: Sequence[Sequence[Mapping[str, float]]], config: RFFConfig) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, float]]]:
    if not frames:
        return np.asarray([], dtype=float), np.asarray([], dtype=float), []
    states: List[List[Optional[Dict[str, float]]]] = [list(map(dict, fr)) + [None] for fr in frames]
    costs: List[np.ndarray] = []
    backs: List[np.ndarray] = []

    def emission(state: Optional[Mapping[str, float]], strongest: float) -> float:
        if state is None:
            # Let the path become unvoiced when only weak random cepstral peaks
            # are available (e.g. inside /f/). v16 effectively forced a pitch
            # estimate through the fricative because every frame had a maximum.
            return 0.20 + 2.00 * strongest
        return 2.20 * (1.0 - float(state.get("quality", 0.0)))

    for i, cur_states in enumerate(states):
        strongest = max([float(x.get("quality", 0.0)) for x in cur_states if x is not None] + [0.0])
        cur_cost = np.full(len(cur_states), np.inf, dtype=float)
        cur_back = np.full(len(cur_states), -1, dtype=int)
        if i == 0:
            for j, state in enumerate(cur_states):
                cur_cost[j] = emission(state, strongest)
        else:
            for j, state in enumerate(cur_states):
                e = emission(state, strongest)
                for k, prev in enumerate(states[i - 1]):
                    if prev is None and state is None:
                        trans = 0.10
                    elif prev is None:
                        trans = 0.55
                    elif state is None:
                        trans = 0.70
                    else:
                        delta = abs(math.log2(float(state["f0_hz"]) / float(prev["f0_hz"])))
                        trans = 7.0 * delta * delta + 2.0 * max(0.0, delta - 0.20)
                        if 0.72 <= delta <= 1.28:
                            trans += 2.50
                    value = float(costs[i - 1][k] + trans + e)
                    if value < cur_cost[j]:
                        cur_cost[j] = value
                        cur_back[j] = k
        costs.append(cur_cost)
        backs.append(cur_back)

    path_idx = [int(np.argmin(costs[-1]))]
    for i in range(len(states) - 1, 0, -1):
        path_idx.append(int(backs[i][path_idx[-1]]))
    path_idx.reverse()
    selected: List[Dict[str, float]] = []
    f0 = np.full(len(states), np.nan, dtype=float)
    confidence = np.zeros(len(states), dtype=float)
    for i, j in enumerate(path_idx):
        state = states[i][j] if 0 <= j < len(states[i]) else None
        if state is None:
            selected.append({})
            continue
        state = dict(state)
        q = float(state.get("quality", 0.0))
        q *= 1.0 - 0.35 * float(np.clip(state.get("octave_ambiguity", 0.0), 0.0, 1.0))
        ac = float(state.get("ac_strength", 0.0))
        z = float(state.get("cep_peak_z", 0.0))
        if q >= float(config.cep_min_confidence) and (ac >= float(config.cep_min_ac_strength) or z >= 2.0):
            f0[i] = float(state["f0_hz"])
            confidence[i] = q
            state["quality_after_octave_ambiguity"] = q
            selected.append(state)
        else:
            selected.append({})

    # Correct isolated octave slips against the local path, then smooth only in
    # log-frequency. This does not force an RFF contour or normative sign.
    for i in range(f0.size):
        if not np.isfinite(f0[i]):
            continue
        neighborhood = f0[max(0, i - 2):min(f0.size, i + 3)]
        neighborhood = neighborhood[np.isfinite(neighborhood)]
        if neighborhood.size < 2:
            continue
        ref = float(np.nanmedian(neighborhood))
        ratio = f0[i] / max(ref, 1e-9)
        if 1.80 <= ratio <= 2.20 and config.f0_floor <= f0[i] / 2.0:
            f0[i] /= 2.0
        elif 0.45 <= ratio <= 0.56 and f0[i] * 2.0 <= config.f0_ceiling:
            f0[i] *= 2.0
    mask = np.isfinite(f0) & (f0 > 0)
    logf = np.full_like(f0, np.nan)
    logf[mask] = np.log2(f0[mask])
    logf = median_filter_nan(logf, 3)
    f0[np.isfinite(logf)] = np.power(2.0, logf[np.isfinite(logf)])

    max_gap = max(0, int(config.cep_max_interp_gap_frames))
    i = 0
    while i < f0.size:
        if np.isfinite(f0[i]):
            i += 1
            continue
        j = i
        while j < f0.size and not np.isfinite(f0[j]):
            j += 1
        gap = j - i
        if i > 0 and j < f0.size and gap <= max_gap and abs(math.log2(f0[j] / f0[i - 1])) <= 0.35:
            f0[i:j] = np.exp2(np.linspace(math.log2(f0[i - 1]), math.log2(f0[j]), gap + 2)[1:-1])
            confidence[i:j] = 0.80 * min(confidence[i - 1], confidence[j])
        i = j
    return f0, confidence, selected


def cepstral_f0_track_detailed(y: np.ndarray, fs: int, config: RFFConfig) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    y = np.asarray(y, dtype=float).reshape(-1)
    if y.size < 64 or fs <= 0:
        empty = np.asarray([], dtype=float)
        return empty, empty, empty, {"reason": "audio too short"}
    peak = float(np.nanmax(np.abs(y))) if y.size else 0.0
    y_norm = y / max(peak, 1e-12)
    hop = max(1, int(round(float(config.cep_hop_s) * fs)))
    centers = np.arange(0, y_norm.size, hop, dtype=int)
    frame_sizes = sorted(set(max(64, int(round(v * fs))) for v in (
        config.cep_frame_short_s, config.cep_frame_medium_s, config.cep_frame_long_s
    )))
    pad = max(frame_sizes) // 2 + 2
    y_pad = np.pad(y_norm, (pad, pad), mode="reflect" if y_norm.size > 2 else "constant")
    frames: List[List[Dict[str, float]]] = []
    for center in centers:
        groups: List[List[Dict[str, float]]] = []
        cp = int(center + pad)
        for n in frame_sizes:
            a = cp - n // 2
            seg = y_pad[a:a + n]
            groups.append(_cepstral_frame_candidates(seg, fs, config))
        frames.append(_merge_multiresolution_candidates(groups, config.cep_max_candidates))
    f0, confidence, selected = _viterbi_cepstral_path(frames, config)
    t = centers.astype(float) / float(fs)
    selected_cpp = [safe_float(v.get("cpp_like_db"), np.nan) if v else np.nan for v in selected]
    selected_ac = [safe_float(v.get("ac_strength"), np.nan) if v else np.nan for v in selected]
    selected_octave = [safe_float(v.get("octave_ambiguity"), np.nan) if v else np.nan for v in selected]
    details = {
        "tracker": "multiresolution_real_cepstrum_plus_normalized_ac_viterbi_v17",
        "frame_durations_s": [float(v / fs) for v in frame_sizes],
        "hop_s": float(hop / fs),
        "raw_prominence_gate_used": False,
        "voiced_frame_fraction": float(np.mean(np.isfinite(f0))) if f0.size else 0.0,
        "median_confidence": float(np.nanmedian(confidence[np.isfinite(f0)])) if np.any(np.isfinite(f0)) else np.nan,
        "median_selected_cpp_like_db": float(np.nanmedian(selected_cpp)) if np.any(np.isfinite(selected_cpp)) else np.nan,
        "median_selected_ac_strength": float(np.nanmedian(selected_ac)) if np.any(np.isfinite(selected_ac)) else np.nan,
        "octave_ambiguous_frame_fraction": float(np.mean(np.asarray(selected_octave, dtype=float) >= 0.90)) if selected_octave else 0.0,
        "median_candidate_count": float(np.median([len(v) for v in frames])) if frames else 0.0,
        "max_candidate_count": int(max([len(v) for v in frames] + [0])),
    }
    return t, f0, confidence, details


def cepstral_f0_track(y: np.ndarray, fs: int, config: RFFConfig) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compatibility wrapper used by legacy development helpers."""
    t, f0, confidence, _ = cepstral_f0_track_detailed(y, fs, config)
    return t, f0, confidence


def _interp_valid(t: np.ndarray, values: np.ndarray, query: np.ndarray, default: float = np.nan) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    values = np.asarray(values, dtype=float)
    query = np.asarray(query, dtype=float)
    mask = np.isfinite(t) & np.isfinite(values)
    if np.sum(mask) < 2:
        return np.full(query.shape, default, dtype=float)
    return np.interp(query, t[mask], values[mask], left=default, right=default)


def _phase_crossings(phase: np.ndarray, fs: int, phase_offset: float) -> np.ndarray:
    phase = np.asarray(phase, dtype=float).reshape(-1)
    if phase.size < 2:
        return np.asarray([], dtype=float)
    cycle = np.floor((phase - float(phase_offset)) / (2.0 * np.pi)).astype(np.int64)
    out: List[float] = []
    for i in np.where(np.diff(cycle) > 0)[0]:
        for level in range(int(cycle[i] + 1), int(cycle[i + 1] + 1)):
            target = float(phase_offset + 2.0 * np.pi * level)
            denom = float(phase[i + 1] - phase[i])
            if denom <= 0:
                continue
            frac = float(np.clip((target - phase[i]) / denom, 0.0, 1.0))
            out.append((i + frac) / float(fs))
    return np.unique(np.asarray(out, dtype=float))


def _cepstral_phase_window(
    selected: np.ndarray,
    candidate_pool: np.ndarray,
    all_crossings: np.ndarray,
    envelope: np.ndarray,
    fs: int,
    edge: float,
    side: str,
    t_pitch: np.ndarray,
    f0_track: np.ndarray,
    confidence: np.ndarray,
    config: RFFConfig,
    pool_name: str,
    window_rank: int,
) -> Dict[str, Any]:
    """Evaluate one contiguous 11-landmark window without a sign target."""
    selected = np.asarray(selected, dtype=float)
    cand = np.asarray(candidate_pool, dtype=float)
    all_local = np.asarray(all_crossings, dtype=float)
    dbg: Dict[str, Any] = {
        "raw_landmarks_s": cand.tolist(),
        "all_phase_crossings_s": all_local.tolist(),
        "selected_landmarks_s": selected.tolist(),
        "phase_cycle_detector": "narrow_band_hilbert_crossings_v21_boundary_adjacent",
        "window_pool": str(pool_name),
        "window_rank_from_edge": int(window_rank),
    }
    if selected.size != 11:
        dbg["reject"] = "fewer than 10 cepstral-guided phase cycles"
        dbg["score"] = 1e9
        return {"rff": None, "reject": dbg["reject"], "score": 1e9, "debug": dbg}

    periods = np.diff(selected)
    freqs = periods_to_freq(periods)
    mids = 0.5 * (selected[:-1] + selected[1:])
    predicted = _interp_valid(t_pitch, f0_track, mids)
    conf = _interp_valid(t_pitch, confidence, mids, default=0.0)
    valid_pred = np.isfinite(predicted) & (predicted > 0) & np.isfinite(freqs) & (freqs > 0)
    per_cycle_track_error_st = np.full(periods.shape, np.nan, dtype=float)
    per_cycle_track_error_st[valid_pred] = np.abs(12.0 * np.log2(freqs[valid_pred] / predicted[valid_pred]))
    log_error = float(np.nanmedian(np.abs(np.log2(freqs[valid_pred] / predicted[valid_pred])))) if np.any(valid_pred) else np.inf

    med_period = float(np.nanmedian(periods)) if periods.size else np.nan
    interior_periods = periods[:-1] if side == "off" else periods[1:]
    interior_period = float(np.nanmedian(interior_periods)) if interior_periods.size else med_period
    period_cv = float(np.nanstd(periods) / med_period) if np.isfinite(med_period) and med_period > 0 else np.inf
    _, adjacent_ratio = _period_ratio_metrics(periods)
    adjacent_ratio = float(adjacent_ratio) if np.isfinite(adjacent_ratio) else np.inf

    boundary_index = 9 if side == "off" else 0
    boundary_period = float(periods[boundary_index])
    boundary_freq = float(freqs[boundary_index]) if freqs.size == 10 else np.nan
    boundary_mid = float(mids[boundary_index]) if mids.size == 10 else np.nan
    boundary_predicted_f0 = float(predicted[boundary_index]) if predicted.size == 10 and np.isfinite(predicted[boundary_index]) else np.nan
    boundary_confidence = float(conf[boundary_index]) if conf.size == 10 and np.isfinite(conf[boundary_index]) else 0.0
    boundary_track_deviation_st = (
        float(abs(12.0 * math.log2(boundary_freq / boundary_predicted_f0)))
        if np.isfinite(boundary_freq) and boundary_freq > 0 and np.isfinite(boundary_predicted_f0) and boundary_predicted_f0 > 0
        else np.nan
    )
    boundary_signed_ratio = (
        float(boundary_period / interior_period)
        if np.isfinite(boundary_period) and boundary_period > 0 and np.isfinite(interior_period) and interior_period > 0
        else np.nan
    )
    boundary_period_ratio = (
        float(max(boundary_signed_ratio, 1.0 / boundary_signed_ratio))
        if np.isfinite(boundary_signed_ratio) and boundary_signed_ratio > 0 else np.inf
    )
    edge_gap = float(edge - selected[-1]) if side == "off" else float(selected[0] - edge)
    edge_cycles = float(edge_gap / med_period) if np.isfinite(med_period) and med_period > 0 else np.inf

    env_idx = np.asarray(np.clip(np.round(selected * fs), 0, envelope.size - 1), dtype=int)
    selected_env = np.asarray(envelope[env_idx], dtype=float) if envelope.size else np.asarray([], dtype=float)
    if side == "off":
        ref_mask = (np.arange(envelope.size) / fs >= max(0.0, edge - 0.30)) & (np.arange(envelope.size) / fs < edge)
    else:
        ref_mask = (np.arange(envelope.size) / fs > edge) & (np.arange(envelope.size) / fs <= edge + 0.30)
    ref_env = float(np.nanmedian(envelope[ref_mask])) if np.any(ref_mask) else float(np.nanmedian(envelope))
    env_ratio = float(np.nanmedian(selected_env) / max(ref_env, 1e-12)) if selected_env.size else 0.0
    if envelope.size and np.isfinite(boundary_mid):
        bi0 = max(0, int(round(selected[boundary_index] * fs)))
        bi1 = min(envelope.size, int(round(selected[boundary_index + 1] * fs)) + 1)
        boundary_env = float(np.nanmedian(envelope[bi0:bi1])) if bi1 > bi0 else np.nan
        interior_env = float(np.nanmedian(selected_env[1:-1])) if selected_env.size > 3 else float(np.nanmedian(selected_env))
        boundary_envelope_ratio = float(boundary_env / max(interior_env, 1e-12)) if np.isfinite(boundary_env) else np.nan
    else:
        boundary_envelope_ratio = np.nan
    median_conf = float(np.nanmedian(conf)) if conf.size else 0.0

    base = freqs[0] if side == "off" else freqs[-1]
    rff = hz_to_st(freqs, base) if np.isfinite(base) and base > 0 else None
    boundary_rff_st = float(rff[boundary_index]) if rff is not None and np.asarray(rff).shape == (10,) and np.isfinite(rff[boundary_index]) else np.nan
    reasons: List[str] = []
    if rff is None or np.asarray(rff).shape != (10,) or not np.all(np.isfinite(rff)):
        reasons.append("invalid 10-cycle RFF")
    if not np.all((freqs >= config.f0_floor) & (freqs <= config.f0_ceiling)):
        reasons.append("phase-cycle F0 outside cepstral range")
    if not np.isfinite(log_error) or log_error > float(config.cep_max_period_log2_error):
        reasons.append("phase periods disagree with cepstral path")
    if period_cv > float(config.cep_max_period_cv):
        reasons.append("phase-period variability too high")
    if adjacent_ratio > float(config.cep_max_adjacent_period_ratio):
        reasons.append("adjacent phase-period ratio too high")
    if boundary_period_ratio > float(config.cep_max_boundary_period_ratio):
        reasons.append("boundary phase period catastrophically inconsistent with the 10-cycle window")
    if median_conf < float(config.cep_min_confidence):
        reasons.append("low cepstral path confidence")
    if env_ratio < float(config.cep_phase_min_envelope_ratio):
        reasons.append("insufficient vowel envelope at phase cycles")

    boundary_support_penalty = 0.0
    if np.isfinite(boundary_period_ratio):
        boundary_support_penalty += 2.0 * max(0.0, boundary_period_ratio - 1.0)
    if np.isfinite(boundary_track_deviation_st):
        boundary_support_penalty += 0.20 * max(0.0, boundary_track_deviation_st - 1.0)
    if np.isfinite(boundary_envelope_ratio):
        boundary_support_penalty += 1.5 * max(0.0, float(config.cep_boundary_min_envelope_ratio) - boundary_envelope_ratio)

    score = (
        4.0 * min(log_error, 2.0)
        + 2.0 * min(period_cv, 2.0)
        + 1.2 * max(0.0, adjacent_ratio - 1.0)
        + 0.20 * max(0.0, edge_cycles)
        + 1.5 * max(0.0, float(config.cep_min_confidence) - median_conf)
        + boundary_support_penalty
        + float(config.cep_window_reoptimization_penalty) * max(0, int(window_rank))
    )
    dbg.update({
        "periods_s": periods.tolist(), "freqs_hz": freqs.tolist(),
        "period_midpoints_s": mids.tolist(),
        "predicted_f0_hz": predicted.tolist(),
        "per_cycle_confidence": conf.tolist(),
        "rff_st": np.asarray(rff, dtype=float).tolist() if rff is not None else [],
        "median_track_log2_error": log_error,
        "per_cycle_track_error_st": per_cycle_track_error_st.tolist(),
        "period_cv": period_cv, "max_adjacent_period_ratio": adjacent_ratio,
        "edge_gap_s": edge_gap, "boundary_period_s": boundary_period,
        "boundary_frequency_hz": boundary_freq,
        "boundary_interior_median_period_s": interior_period,
        "boundary_period_signed_ratio": boundary_signed_ratio,
        "boundary_period_ratio": boundary_period_ratio,
        "boundary_midpoint_s": boundary_mid,
        "boundary_predicted_f0_hz": boundary_predicted_f0,
        "boundary_track_deviation_st": boundary_track_deviation_st,
        "boundary_confidence": boundary_confidence,
        "boundary_envelope_ratio": boundary_envelope_ratio,
        "boundary_rff_st": boundary_rff_st,
        "boundary_support_penalty": boundary_support_penalty,
        "edge_gap_cycles": edge_cycles,
        "median_cepstral_confidence": median_conf,
        "median_envelope_ratio": env_ratio,
        "score": float(score), "reject": "; ".join(reasons),
    })
    return {"rff": None if reasons else np.asarray(rff, dtype=float), "reject": "; ".join(reasons), "score": float(score), "debug": dbg}


def _enumerate_cepstral_windows(
    candidates: np.ndarray,
    all_crossings: np.ndarray,
    edge: float,
    side: str,
    config: RFFConfig,
) -> List[Tuple[np.ndarray, str, int]]:
    """Return only boundary-adjacent 11-landmark windows.

    Classical RFF requires the ten cycles immediately adjacent to the
    voicing offset/onset. v20 searched progressively deeper windows and could
    select smooth steady-state cycles several periods away from the ROI,
    attenuating the transition that RFF is intended to measure. v21 may switch
    between qualified and all-phase pools, and between peak and trough phase,
    but it never skips a valid boundary candidate merely to obtain a smoother
    trajectory. If the boundary-adjacent window fails QC, the side is rejected.
    """
    windows: List[Tuple[float, np.ndarray, str, int]] = []
    seen: set[Tuple[int, ...]] = set()
    lower = max(0.0, edge - config.edge_pad_s)
    upper = edge + config.edge_pad_s
    for pool_name, source in (("qualified", candidates), ("all_phase", all_crossings)):
        pool = np.asarray(source, dtype=float)
        pool = np.unique(np.sort(pool[np.isfinite(pool)]))
        if side == "off":
            pool = pool[(pool < edge) & (pool >= lower)]
        else:
            pool = pool[(pool > edge) & (pool <= upper)]
        if pool.size < 11:
            continue
        # Exactly the edge-adjacent window for this phase/pool.
        w = pool[-11:] if side == "off" else pool[:11]
        gap = float(edge - w[-1]) if side == "off" else float(w[0] - edge)
        if gap < 0:
            continue
        key = tuple(np.round(w * 1e7).astype(int).tolist())
        if key in seen:
            continue
        seen.add(key)
        windows.append((gap, w, pool_name, 0))
    windows.sort(key=lambda x: (x[0], 0 if x[2] == "qualified" else 1))
    return [(w, pool_name, rank) for _, w, pool_name, rank in windows]

def _cepstral_phase_trace(
    candidates: np.ndarray,
    all_crossings: np.ndarray,
    envelope: np.ndarray,
    fs: int,
    edge: float,
    side: str,
    t_pitch: np.ndarray,
    f0_track: np.ndarray,
    confidence: np.ndarray,
    config: RFFConfig,
) -> Dict[str, Any]:
    """Create and score alternative contiguous 11-landmark phase windows."""
    cand = np.asarray(candidates, dtype=float)
    all_local = np.asarray(all_crossings, dtype=float)
    if side == "off":
        cand = cand[(cand < edge) & (cand >= max(0.0, edge - config.edge_pad_s))]
        all_local = all_local[(all_local < edge) & (all_local >= max(0.0, edge - config.edge_pad_s))]
    else:
        cand = cand[(cand > edge) & (cand <= edge + config.edge_pad_s)]
        all_local = all_local[(all_local > edge) & (all_local <= edge + config.edge_pad_s)]
    windows = _enumerate_cepstral_windows(cand, all_local, edge, side, config)
    evaluated = [
        _cepstral_phase_window(w, cand, all_local, envelope, fs, edge, side,
                                t_pitch, f0_track, confidence, config, pool, rank)
        for w, pool, rank in windows
    ]
    if not evaluated:
        dbg = {
            "raw_landmarks_s": cand.tolist(), "all_phase_crossings_s": all_local.tolist(),
            "selected_landmarks_s": [], "phase_cycle_detector": "narrow_band_hilbert_crossings_v21_boundary_adjacent",
            "reject": "fewer than 10 cepstral-guided phase cycles", "score": 1e9,
        }
        return {"rff": None, "reject": dbg["reject"], "score": 1e9, "debug": dbg, "windows": []}
    evaluated.sort(key=lambda item: float(item.get("score", 1e9)))
    best = dict(evaluated[0])
    best["windows"] = evaluated
    best["debug"] = dict(best.get("debug", {}))
    best["debug"]["window_candidate_count"] = int(len(evaluated))
    best["debug"]["window_search_rule"] = "boundary-adjacent qualified/all-phase 11-landmark windows only; final selection occurs after v21 all-cycle QC"
    return best

def _choose_cepstral_phase_trace(peak: Mapping[str, Any], trough: Mapping[str, Any]) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    valid = [(name, item) for name, item in (("peak", peak), ("trough", trough)) if item.get("rff") is not None]
    if valid:
        chosen, item = min(valid, key=lambda x: float(x[1].get("score", 1e9)))
    else:
        chosen, item = min((("peak", peak), ("trough", trough)), key=lambda x: float(x[1].get("score", 1e9)))
    debug = {
        "chosen": chosen,
        "selection_rule": "lowest cepstral-path/phase-period error; no normative-shape or sign target",
        "peak": dict(peak.get("debug", {})),
        "trough": dict(trough.get("debug", {})),
    }
    return item.get("rff"), str(item.get("reject", "")), debug


def _join_reject_reasons(existing: str, new_reason: str) -> str:
    parts = [str(v).strip() for v in (existing, new_reason) if str(v).strip()]
    return "; ".join(dict.fromkeys(parts))


def _cepstral_multihypothesis_candidates(
    y: np.ndarray,
    fs: int,
    landmarks: np.ndarray,
    edge: Optional[float],
    side: str,
    reference_f0: float,
    config: RFFConfig,
) -> Tuple[List[Dict[str, float]], Dict[str, Any]]:
    """Estimate several independent periodicity hypotheses with AC and YIN.

    The segment is extended away from the fricative so that the decision is not
    driven only by the ten already-selected phase cycles. Both T and 2T/0.5T
    hypotheses are retained. This function does not change the RFF cycles.
    """
    lm = np.asarray(landmarks, dtype=float)
    lm = np.unique(np.sort(lm[np.isfinite(lm)]))
    details: Dict[str, Any] = {"PeriodicCandidateEstimator": "raw_waveform_AC_plus_YIN_v21"}
    if lm.size != 11:
        return [], details
    periods = np.diff(lm)
    med_period = float(np.nanmedian(periods)) if periods.size else np.nan
    if not np.isfinite(med_period) or med_period <= 0:
        return [], details
    dur = len(y) / float(fs)
    extend = max(float(config.cep_periodicity_window_s), 4.0 * med_period)
    if str(side).lower() == "off":
        t0 = max(0.0, lm[0] - extend)
        t1 = min(float(edge) if edge is not None and np.isfinite(edge) else lm[-1] + med_period, lm[-1] + 0.5 * med_period)
    else:
        t0 = max(float(edge) if edge is not None and np.isfinite(edge) else lm[0] - med_period, lm[0] - 0.5 * med_period)
        t1 = min(dur, lm[-1] + extend)
    i0 = max(0, int(math.floor(t0 * fs)))
    i1 = min(len(y), int(math.ceil(t1 * fs)))
    seg = np.asarray(y[i0:i1], dtype=float)
    details.update({"IndependentWindowStart_s": i0 / float(fs), "IndependentWindowEnd_s": i1 / float(fs), "IndependentWindowSamples": int(seg.size)})
    if seg.size < max(96, int(round(5.0 * med_period * fs))):
        return [], details
    seg = sp_signal.detrend(seg, type="linear")
    rms = float(np.sqrt(np.mean(seg * seg)))
    if not np.isfinite(rms) or rms <= 1e-8:
        return [], details
    x = (seg / rms) * np.hanning(seg.size)
    lag_min = max(2, int(math.floor(fs / max(config.f0_ceiling, 1.0))))
    lag_max = min(seg.size // 2 - 2, int(math.ceil(fs / max(config.f0_floor, 1.0))))
    if lag_max <= lag_min + 3:
        return [], details

    nfft = 1 << int(math.ceil(math.log2(max(512, 2 * x.size))))
    ac = np.fft.irfft(np.square(np.abs(np.fft.rfft(x, n=nfft))), n=nfft)[:lag_max + 2]
    ac = ac / max(float(ac[0]), 1e-12)
    overlap = np.maximum(1.0, x.size - np.arange(ac.size, dtype=float))
    ac = np.clip(ac * (x.size / overlap), -1.0, 1.0)

    diff = np.zeros(lag_max + 2, dtype=float)
    for tau in range(1, lag_max + 2):
        delta = x[:-tau] - x[tau:]
        diff[tau] = float(np.dot(delta, delta))
    cmnd = np.ones_like(diff)
    cumulative = np.cumsum(diff[1:])
    taus = np.arange(1, diff.size, dtype=float)
    cmnd[1:] = diff[1:] * taus / np.maximum(cumulative, 1e-12)
    yin_strength = np.clip(1.0 - cmnd, 0.0, 1.0)

    ac_slice = ac[lag_min:lag_max + 1]
    ac_peaks = _local_maxima_1d(ac_slice) + lag_min
    yin_slice = yin_strength[lag_min:lag_max + 1]
    yin_peaks = _local_maxima_1d(yin_slice) + lag_min
    lag_pool: set[int] = set()
    if ac_peaks.size:
        for k in ac_peaks[np.argsort(ac[ac_peaks])[-10:]]:
            lag_pool.add(int(k))
    if yin_peaks.size:
        for k in yin_peaks[np.argsort(yin_strength[yin_peaks])[-10:]]:
            lag_pool.add(int(k))
    lag_pool.add(int(lag_min + np.argmax(ac_slice)))
    lag_pool.add(int(lag_min + np.argmax(yin_slice)))
    for f in (reference_f0, float(1.0 / med_period)):
        if np.isfinite(f) and f > 0:
            base_lag = int(round(fs / f))
            for mult in (0.5, 1.0, 2.0):
                lag = int(round(base_lag * mult))
                if lag_min <= lag <= lag_max:
                    lag_pool.add(lag)

    # Explicitly retain harmonic-family neighbours of every strong candidate.
    seed_lags = list(lag_pool)
    for lag in seed_lags:
        for mult in (0.5, 2.0):
            other = int(round(lag * mult))
            if lag_min <= other <= lag_max:
                lag_pool.add(other)

    first_strong_yin_lag = np.nan
    threshold = float(config.cep_yin_candidate_threshold)
    for lag in range(lag_min, lag_max + 1):
        if yin_strength[lag] >= threshold:
            first_strong_yin_lag = float(lag)
            break

    raw_candidates: List[Dict[str, float]] = []
    for lag in sorted(lag_pool):
        if not (lag_min <= lag <= lag_max):
            continue
        refined = parabolic_interp(ac, lag) if 0 < lag < ac.size - 1 else float(lag)
        refined = float(np.clip(refined, lag_min, lag_max))
        f0 = float(fs / refined)
        if not (config.f0_floor <= f0 <= config.f0_ceiling):
            continue
        ac_strength = float(np.clip(ac[lag], 0.0, 1.0))
        yin = float(np.clip(yin_strength[lag], 0.0, 1.0))
        reference_bonus = 0.0
        if np.isfinite(reference_f0) and reference_f0 > 0:
            dev = abs(12.0 * math.log2(f0 / reference_f0))
            reference_bonus = 0.07 * math.exp(-0.5 * (dev / 3.0) ** 2)
        first_yin_bonus = 0.0
        if np.isfinite(first_strong_yin_lag):
            first_yin_bonus = 0.05 * math.exp(-0.5 * ((lag - first_strong_yin_lag) / max(2.0, 0.12 * first_strong_yin_lag)) ** 2)
        score = 0.52 * ac_strength + 0.36 * yin + reference_bonus + first_yin_bonus
        raw_candidates.append({
            "f0_hz": f0,
            "lag_samples": refined,
            "ac_strength": ac_strength,
            "yin_strength": yin,
            "score": float(score),
        })

    raw_candidates.sort(key=lambda d: d["score"], reverse=True)
    merged: List[Dict[str, float]] = []
    for cand in raw_candidates:
        if any(abs(12.0 * math.log2(cand["f0_hz"] / old["f0_hz"])) < 0.35 for old in merged):
            continue
        merged.append(cand)
        if len(merged) >= 10:
            break
    # Alternating half-cycle evidence: when the selected phase frequency is
    # one octave too high, adjacent P-length waveform cycles often alternate,
    # whereas cycles two periods apart are similar. A true high-F0 tone does
    # not show this odd/even pattern merely because AC is also high at 2P.
    phase_f0 = float(1.0 / med_period)
    phase_period_samples = int(round(fs / phase_f0)) if np.isfinite(phase_f0) and phase_f0 > 0 else 0
    adjacent_corrs: List[float] = []
    two_apart_corrs: List[float] = []
    if phase_period_samples >= 4:
        n_cycles = min(20, x.size // phase_period_samples)
        cycles: List[np.ndarray] = []
        for ci in range(n_cycles):
            c = np.asarray(x[ci * phase_period_samples:(ci + 1) * phase_period_samples], dtype=float)
            if c.size != phase_period_samples:
                continue
            c = c - np.mean(c)
            norm = float(np.linalg.norm(c))
            if norm > 1e-9:
                cycles.append(c / norm)
        for ci in range(len(cycles) - 1):
            adjacent_corrs.append(float(np.dot(cycles[ci], cycles[ci + 1])))
        for ci in range(len(cycles) - 2):
            two_apart_corrs.append(float(np.dot(cycles[ci], cycles[ci + 2])))
    adjacent_corr = float(np.nanmedian(adjacent_corrs)) if adjacent_corrs else np.nan
    two_apart_corr = float(np.nanmedian(two_apart_corrs)) if two_apart_corrs else np.nan
    alternation_score = float(two_apart_corr - adjacent_corr) if np.isfinite(adjacent_corr) and np.isfinite(two_apart_corr) else np.nan
    details.update({
        "FirstStrongYINLag_samples": first_strong_yin_lag,
        "HalfPeriodAdjacentCycleCorrelation": adjacent_corr,
        "HalfPeriodTwoApartCycleCorrelation": two_apart_corr,
        "HalfPeriodAlternationScore": alternation_score,
        "PeriodicityCandidates": merged,
    })
    return merged, details


def _nearest_periodicity_candidate(candidates: Sequence[Mapping[str, Any]], f0: float) -> Optional[Dict[str, float]]:
    if not np.isfinite(f0) or f0 <= 0 or not candidates:
        return None
    valid = [dict(c) for c in candidates if safe_float(c.get("f0_hz"), np.nan) > 0]
    if not valid:
        return None
    return min(valid, key=lambda c: abs(12.0 * math.log2(float(c["f0_hz"]) / f0)))


def _apply_cepstral_independent_periodicity_guard(
    rff: Optional[np.ndarray],
    reject: str,
    landmarks: np.ndarray,
    y: np.ndarray,
    fs: int,
    config: RFFConfig,
    edge: Optional[float] = None,
    side: str = "",
    reference_f0: float = np.nan,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Confirm phase cycles with independent multi-hypothesis AC/YIN evidence.

    Unlike v18, the guard keeps several harmonic-family hypotheses rather than
    trusting the single largest autocorrelation peak. It rejects ambiguity; it
    never shifts, doubles or halves the selected cycles silently.
    """
    lm = np.asarray(landmarks, dtype=float)
    details: Dict[str, Any] = {
        "IndependentPeriodicityGate": "raw_waveform_AC_YIN_multihypothesis_v21",
        "IndependentAutocorrMin": float(config.cep_independent_autocorr_min),
        "IndependentPitchMaxDeviationST": float(config.cep_independent_pitch_max_deviation_st),
        "OctaveCompetitorRatio": float(config.cep_periodicity_octave_competitor_ratio),
    }
    if rff is None or lm.size != 11:
        return rff, reject, details
    periods = np.diff(lm)
    phase_f0_values = periods_to_freq(periods)
    phase_f0_values = phase_f0_values[np.isfinite(phase_f0_values) & (phase_f0_values > 0)]
    phase_f0 = float(np.nanmedian(phase_f0_values)) if phase_f0_values.size else np.nan
    candidates, candidate_details = _cepstral_multihypothesis_candidates(
        y, fs, lm, edge, side, reference_f0, config,
    )
    details.update(candidate_details)
    details["PhaseMedianF0_Hz"] = phase_f0
    details["ReferenceF0_Hz"] = reference_f0
    if not candidates:
        return None, _join_reject_reasons(reject, "insufficient independent waveform periodicity hypotheses"), details

    best = dict(candidates[0])
    phase_candidate = _nearest_periodicity_candidate(candidates, phase_f0)
    details["IndependentBestCandidate"] = best
    details["PhaseNearestCandidate"] = phase_candidate or {}
    best_dev = (
        float(abs(12.0 * math.log2(float(best["f0_hz"]) / phase_f0)))
        if np.isfinite(phase_f0) and phase_f0 > 0 else np.nan
    )
    phase_candidate_dev = (
        float(abs(12.0 * math.log2(float(phase_candidate["f0_hz"]) / phase_f0)))
        if phase_candidate and np.isfinite(phase_f0) and phase_f0 > 0 else np.nan
    )
    details["IndependentBestDeviationST"] = best_dev
    details["PhaseCandidateDeviationST"] = phase_candidate_dev

    if float(best.get("ac_strength", 0.0)) < float(config.cep_independent_autocorr_min) and float(best.get("yin_strength", 0.0)) < 0.55:
        return None, _join_reject_reasons(reject, "insufficient independent waveform periodicity"), details

    phase_score = float(phase_candidate.get("score", 0.0)) if phase_candidate else 0.0
    octave_competitors: List[Dict[str, float]] = []
    for cand in candidates:
        if not np.isfinite(phase_f0) or phase_f0 <= 0:
            continue
        separation = abs(12.0 * math.log2(float(cand["f0_hz"]) / phase_f0))
        if 8.5 <= separation <= 15.5:
            item = dict(cand)
            item["separation_from_phase_st"] = float(separation)
            item["score_ratio_to_phase"] = float(item.get("score", 0.0) / max(phase_score, 1e-9))
            octave_competitors.append(item)
    details["OctaveCompetitors"] = octave_competitors

    strong_competitor = None
    if octave_competitors:
        strong_competitor = max(octave_competitors, key=lambda c: float(c.get("score", 0.0)))
    ambiguous = False
    if strong_competitor is not None and float(strong_competitor.get("score", 0.0)) >= float(config.cep_periodicity_min_candidate_score):
        ratio = float(strong_competitor.get("score_ratio_to_phase", 0.0))
        competitor_f0 = float(strong_competitor["f0_hz"])
        reference_prefers_competitor = False
        if np.isfinite(reference_f0) and reference_f0 > 0 and np.isfinite(phase_f0) and phase_f0 > 0:
            ref_phase = abs(12.0 * math.log2(reference_f0 / phase_f0))
            ref_comp = abs(12.0 * math.log2(reference_f0 / competitor_f0))
            reference_prefers_competitor = ref_comp + 2.0 < ref_phase
        competitor_is_best = abs(12.0 * math.log2(float(best["f0_hz"]) / competitor_f0)) < 0.75
        first_yin_lag = safe_float(details.get("FirstStrongYINLag_samples"), np.nan)
        phase_lag = fs / phase_f0 if np.isfinite(phase_f0) and phase_f0 > 0 else np.nan
        competitor_lag = fs / competitor_f0 if competitor_f0 > 0 else np.nan
        first_yin_prefers_competitor = (
            np.isfinite(first_yin_lag) and np.isfinite(phase_lag) and np.isfinite(competitor_lag)
            and abs(first_yin_lag - competitor_lag) + 0.10 * competitor_lag < abs(first_yin_lag - phase_lag)
        )
        lower_octave_competitor = competitor_f0 < 0.75 * phase_f0 if np.isfinite(phase_f0) and phase_f0 > 0 else False
        alternation_score = safe_float(details.get("HalfPeriodAlternationScore"), np.nan)
        alternating_half_cycles = bool(lower_octave_competitor and np.isfinite(alternation_score) and alternation_score >= 0.12)
        details["FirstYINPrefersOctaveCompetitor"] = bool(first_yin_prefers_competitor)
        details["AlternatingHalfCyclesSupportLowerOctave"] = alternating_half_cycles
        # A high score at 2T is expected even for a true high-F0 periodic tone.
        # It becomes a hard ambiguity only when corroborated by continuity,
        # the first YIN minimum, or odd/even half-cycle alternation.
        ambiguous = (
            ratio >= float(config.cep_periodicity_octave_competitor_ratio)
            and (
                reference_prefers_competitor
                or first_yin_prefers_competitor
                or alternating_half_cycles
                or (competitor_is_best and float(best.get("score", 0.0)) >= phase_score + float(config.cep_periodicity_strong_margin))
            )
        )
    details["OctaveAmbiguityDetected"] = bool(ambiguous)
    if ambiguous:
        return None, _join_reject_reasons(reject, "independent multi-hypothesis periodicity is octave/subharmonic ambiguous"), details

    if (
        np.isfinite(best_dev)
        and best_dev > float(config.cep_independent_pitch_max_deviation_st)
        and float(best.get("score", 0.0)) >= phase_score + float(config.cep_periodicity_strong_margin)
    ):
        return None, _join_reject_reasons(reject, "independent periodicity consensus disagrees with phase-cycle period"), details
    return np.asarray(rff, dtype=float), reject, details


def _boundary_same_phase_extrema_count(
    phase_wave: np.ndarray,
    fs: int,
    landmarks: np.ndarray,
    side: str,
    kind: str,
    config: RFFConfig,
) -> Tuple[int, Dict[str, Any]]:
    lm = np.asarray(landmarks, dtype=float)
    info: Dict[str, Any] = {}
    if lm.size != 11:
        return 0, info
    idx = 9 if str(side).lower() == "off" else 0
    t0, t1 = float(lm[idx]), float(lm[idx + 1])
    i0 = max(0, int(math.floor(t0 * fs)))
    i1 = min(len(phase_wave), int(math.ceil(t1 * fs)) + 1)
    if i1 - i0 < 6:
        return 0, info
    seg = np.asarray(phase_wave[i0:i1], dtype=float)
    target = seg if str(kind).lower() == "peak" else -seg
    span = float(np.nanpercentile(target, 95) - np.nanpercentile(target, 5)) if target.size else 0.0
    prominence = max(1e-8, float(config.cep_boundary_extremum_prominence_ratio) * span)
    periods = np.diff(lm)
    interior = periods[:-1] if str(side).lower() == "off" else periods[1:]
    med = float(np.nanmedian(interior)) if interior.size else float(np.nanmedian(periods))
    distance = max(1, int(round(0.35 * med * fs))) if np.isfinite(med) and med > 0 else 1
    peaks, _ = sp_signal.find_peaks(target, prominence=prominence, distance=distance)
    margin = max(1, int(round(0.15 * med * fs))) if np.isfinite(med) and med > 0 else 1
    internal = peaks[(peaks > margin) & (peaks < len(seg) - margin)]
    info.update({
        "BoundaryCycleStart_s": t0,
        "BoundaryCycleEnd_s": t1,
        "BoundarySamePhaseInternalExtrema": int(internal.size),
        "BoundarySamePhaseExtremaSamples": (internal + i0).astype(int).tolist(),
        "BoundaryExtremumProminence": prominence,
    })
    return int(internal.size), info


def _local_cycle_periodicity_evidence(
    y: np.ndarray,
    fs: int,
    midpoint: float,
    target_f0: float,
    config: RFFConfig,
    cache: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Independent short-window AC/YIN evidence for one selected period."""
    if not np.isfinite(target_f0) or target_f0 <= 0:
        return {"valid": False}
    key = (int(round(midpoint * fs)), int(round(target_f0 * 10.0)))
    if cache is not None and key in cache:
        return dict(cache[key])
    half = max(0.035, 3.5 / float(target_f0))
    i0 = max(0, int(math.floor((midpoint - half) * fs)))
    i1 = min(len(y), int(math.ceil((midpoint + half) * fs)))
    seg = np.asarray(y[i0:i1], dtype=float)
    out: Dict[str, Any] = {"valid": False, "window_start_s": i0 / float(fs), "window_end_s": i1 / float(fs)}
    if seg.size < 96:
        if cache is not None: cache[key] = out
        return out
    seg = sp_signal.detrend(seg, type="linear")
    rms = float(np.sqrt(np.mean(seg * seg)))
    if not np.isfinite(rms) or rms < 1e-8:
        if cache is not None: cache[key] = out
        return out
    x = (seg / rms) * np.hanning(seg.size)
    lag_min = max(2, int(math.floor(fs / max(config.f0_ceiling, 1.0))))
    lag_max = min(seg.size // 2 - 2, int(math.ceil(fs / max(config.f0_floor, 1.0))))
    if lag_max <= lag_min + 3:
        if cache is not None: cache[key] = out
        return out
    nfft = 1 << int(math.ceil(math.log2(max(512, 2 * x.size))))
    ac = np.fft.irfft(np.square(np.abs(np.fft.rfft(x, n=nfft))), n=nfft)[:lag_max + 2]
    ac = ac / max(float(ac[0]), 1e-12)
    overlap = np.maximum(1.0, x.size - np.arange(ac.size, dtype=float))
    ac = np.clip(ac * (x.size / overlap), -1.0, 1.0)
    diff = np.zeros(lag_max + 2, dtype=float)
    for tau in range(1, lag_max + 2):
        delta = x[:-tau] - x[tau:]
        diff[tau] = float(np.dot(delta, delta))
    cmnd = np.ones_like(diff)
    cumulative = np.cumsum(diff[1:])
    cmnd[1:] = diff[1:] * np.arange(1, diff.size, dtype=float) / np.maximum(cumulative, 1e-12)
    yin = np.clip(1.0 - cmnd, 0.0, 1.0)
    lag_pool: set[int] = set()
    ac_peaks = _local_maxima_1d(ac[lag_min:lag_max + 1]) + lag_min
    yin_peaks = _local_maxima_1d(yin[lag_min:lag_max + 1]) + lag_min
    for arr, values in ((ac_peaks, ac), (yin_peaks, yin)):
        if arr.size:
            for lag in arr[np.argsort(values[arr])[-6:]]:
                lag_pool.add(int(lag))
    target_lag = int(round(fs / target_f0))
    for mult in (0.5, 1.0, 2.0):
        lag = int(round(target_lag * mult))
        if lag_min <= lag <= lag_max:
            lag_pool.add(lag)
    candidates: List[Dict[str, float]] = []
    for lag in sorted(lag_pool):
        f0 = float(fs / max(float(lag), 1e-9))
        acs = float(np.clip(ac[lag], 0.0, 1.0))
        ys = float(np.clip(yin[lag], 0.0, 1.0))
        score = 0.58 * acs + 0.42 * ys
        candidates.append({"f0_hz": f0, "lag_samples": float(lag), "ac_strength": acs, "yin_strength": ys, "score": score})
    candidates.sort(key=lambda d: d["score"], reverse=True)
    best = dict(candidates[0]) if candidates else {}
    nearest = _nearest_periodicity_candidate(candidates, target_f0) or {}
    best_dev = float(abs(12.0 * math.log2(float(best["f0_hz"]) / target_f0))) if best else np.nan
    nearest_dev = float(abs(12.0 * math.log2(float(nearest["f0_hz"]) / target_f0))) if nearest else np.nan
    out = {
        "valid": bool(candidates), "target_f0_hz": float(target_f0),
        "best_candidate": best, "nearest_candidate": nearest,
        "best_deviation_st": best_dev, "nearest_deviation_st": nearest_dev,
        "best_score": safe_float(best.get("score"), 0.0),
        "nearest_score": safe_float(nearest.get("score"), 0.0),
    }
    if cache is not None: cache[key] = out
    return out


def _apply_cepstral_all_cycle_guard(
    rff: Optional[np.ndarray],
    reject: str,
    landmarks: np.ndarray,
    trace_debug: Mapping[str, Any],
    periodicity_qc: Mapping[str, Any],
    y: np.ndarray,
    phase_wave: np.ndarray,
    envelope: np.ndarray,
    fs: int,
    edge: float,
    side: str,
    kind: str,
    t_pitch: np.ndarray,
    f0_track: np.ndarray,
    confidence: np.ndarray,
    config: RFFConfig,
    local_cache: Optional[Dict[Tuple[int, int], Dict[str, Any]]] = None,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Validate all ten periods and detect interior phase slips/crossing errors."""
    lm = np.asarray(landmarks, dtype=float)
    details: Dict[str, Any] = {"AllCycleGate": "per_period_track_AC_YIN_phase_continuity_v22_boundary_adjacent"}
    if rff is None or lm.size != 11:
        return rff, reject, details
    periods = np.diff(lm)
    freqs = periods_to_freq(periods)
    mids = 0.5 * (lm[:-1] + lm[1:])
    track_f0 = _interp_valid(t_pitch, f0_track, mids)
    track_conf = _interp_valid(t_pitch, confidence, mids, default=0.0)
    track_dev = np.full(10, np.nan, dtype=float)
    valid_track = np.isfinite(track_f0) & (track_f0 > 0) & np.isfinite(freqs) & (freqs > 0)
    track_dev[valid_track] = np.abs(12.0 * np.log2(freqs[valid_track] / track_f0[valid_track]))

    all_crossings = np.asarray(trace_debug.get("all_phase_crossings_s", []), dtype=float)
    skipped = []
    for a, b in zip(lm[:-1], lm[1:]):
        skipped.append(int(np.sum((all_crossings > a + 1e-8) & (all_crossings < b - 1e-8))))
    skipped = np.asarray(skipped, dtype=int)

    med = float(np.nanmedian(periods)) if periods.size else np.nan
    neighbor_ratio = np.ones(10, dtype=float)
    for i in range(10):
        peers = []
        if i > 0: peers.append(periods[i - 1])
        if i < 9: peers.append(periods[i + 1])
        peer = float(np.nanmedian(peers)) if peers else med
        ratio = periods[i] / peer if peer > 0 else np.nan
        neighbor_ratio[i] = max(ratio, 1.0 / ratio) if np.isfinite(ratio) and ratio > 0 else np.inf
    period_cv = float(np.nanstd(periods) / med) if np.isfinite(med) and med > 0 else np.inf
    logp = np.log2(periods / med) if np.isfinite(med) and med > 0 else np.full(10, np.nan)
    alternating = np.asarray([1.0 if i % 2 == 0 else -1.0 for i in range(10)])
    alternation_amplitude = float(abs(np.nanmean(logp * alternating))) if np.any(np.isfinite(logp)) else np.inf

    env_ratios = np.full(10, np.nan, dtype=float)
    if envelope.size:
        selected_idx = np.asarray(np.clip(np.round(lm * fs), 0, envelope.size - 1), dtype=int)
        interior_ref = float(np.nanmedian(envelope[selected_idx]))
        for i in range(10):
            a = max(0, int(math.floor(lm[i] * fs)))
            b = min(envelope.size, int(math.ceil(lm[i + 1] * fs)) + 1)
            val = float(np.nanmedian(envelope[a:b])) if b > a else np.nan
            env_ratios[i] = val / max(interior_ref, 1e-12) if np.isfinite(val) else np.nan

    independent_dev = np.full(10, np.nan, dtype=float)
    independent_score = np.zeros(10, dtype=float)
    independent_disagree = np.zeros(10, dtype=bool)
    local_details: List[Dict[str, Any]] = []
    for i in range(10):
        ev = _local_cycle_periodicity_evidence(y, fs, float(mids[i]), float(freqs[i]), config, local_cache)
        local_details.append(ev)
        if not ev.get("valid"):
            continue
        independent_dev[i] = safe_float(ev.get("best_deviation_st"), np.nan)
        independent_score[i] = safe_float(ev.get("best_score"), 0.0)
        nearest_score = safe_float(ev.get("nearest_score"), 0.0)
        independent_disagree[i] = bool(
            np.isfinite(independent_dev[i])
            and independent_dev[i] > float(config.cep_cycle_independent_warn_st)
            and independent_score[i] >= float(config.cep_cycle_independent_min_score)
            and independent_score[i] >= nearest_score + 0.06
        )

    track_warn = (track_dev > float(config.cep_cycle_track_warn_st)) & (track_conf >= float(config.cep_cycle_min_track_confidence))
    track_hard = (track_dev > float(config.cep_cycle_track_hard_st)) & (track_conf >= float(config.cep_cycle_min_track_confidence))
    adjacent_warn = neighbor_ratio > float(config.cep_cycle_adjacent_warn_ratio)
    adjacent_hard = neighbor_ratio > float(config.cep_cycle_adjacent_hard_ratio)
    independent_hard = independent_disagree & (independent_dev > float(config.cep_cycle_independent_hard_st))
    low_envelope = np.isfinite(env_ratios) & (env_ratios < float(config.cep_cycle_min_envelope_ratio))
    skipped_crossing = skipped > 0
    evidence_count = (
        track_warn.astype(int) + adjacent_warn.astype(int) + independent_disagree.astype(int)
        + low_envelope.astype(int) + skipped_crossing.astype(int)
    )
    hard_cycle = skipped_crossing | (track_hard & (independent_disagree | adjacent_warn)) | (independent_hard & adjacent_warn)
    if period_cv > float(config.cep_cycle_cv_hard) and int(np.sum(evidence_count >= 2)) >= 2:
        hard_cycle |= evidence_count >= 2
    if alternation_amplitude > float(config.cep_cycle_alternation_hard_log2) and int(np.sum(adjacent_warn)) >= 2:
        hard_cycle |= adjacent_warn & (track_warn | independent_disagree)

    # v22: low envelope is expected near a voiceless fricative and is therefore
    # supportive evidence only. It cannot, by itself, create a review flag.
    structural_evidence_count = (
        track_warn.astype(int) + adjacent_warn.astype(int) + independent_disagree.astype(int)
        + skipped_crossing.astype(int)
    )
    manual_review = bool(
        np.any(structural_evidence_count > 0)
        or period_cv > float(config.cep_cycle_cv_warn)
        or alternation_amplitude > float(config.cep_cycle_alternation_warn_log2)
    )
    penalty = (
        0.12 * float(np.nansum(np.maximum(0.0, track_dev - float(config.cep_cycle_track_warn_st))))
        + 0.80 * float(np.sum(adjacent_warn))
        + 0.80 * float(np.sum(independent_disagree))
        + 2.00 * float(np.sum(skipped_crossing))
        + 2.00 * max(0.0, period_cv - float(config.cep_cycle_cv_warn))
        + 2.00 * max(0.0, alternation_amplitude - float(config.cep_cycle_alternation_warn_log2))
    )
    details.update({
        "CyclePeriods_s": periods.tolist(), "CycleFrequencies_Hz": freqs.tolist(),
        "CycleMidpoints_s": mids.tolist(), "CycleTrackF0_Hz": track_f0.tolist(),
        "CycleTrackConfidence": track_conf.tolist(), "CycleTrackDeviationST": track_dev.tolist(),
        "CycleIndependentDeviationST": independent_dev.tolist(),
        "CycleIndependentScore": independent_score.tolist(),
        "CycleIndependentDisagreement": independent_disagree.tolist(),
        "CycleNeighborPeriodRatio": neighbor_ratio.tolist(),
        "CycleSkippedSamePhaseCrossings": skipped.tolist(),
        "CycleEnvelopeRatio": env_ratios.tolist(),
        "CycleEvidenceCount": evidence_count.tolist(),
        "CycleStructuralEvidenceCount": structural_evidence_count.tolist(),
        "CycleLowEnvelopeSupport": low_envelope.tolist(),
        "CycleHardFailure": hard_cycle.tolist(),
        "PeriodCV": period_cv, "AlternationAmplitudeLog2": alternation_amplitude,
        "AllCycleManualReview": manual_review,
        "AllCyclePenalty": float(penalty),
        "AllCycleLocalIndependentEvidence": local_details,
    })
    review_reasons = []
    if np.any(skipped_crossing): review_reasons.append("selected period skips an exported same-phase crossing")
    if np.any(track_warn): review_reasons.append("one or more cycles disagree with the local cepstral path")
    if np.any(independent_disagree): review_reasons.append("one or more cycles disagree with local AC/YIN periodicity")
    if np.any(adjacent_warn): review_reasons.append("one or more cycles have an abrupt adjacent-period ratio")
    if period_cv > float(config.cep_cycle_cv_warn): review_reasons.append("10-cycle period CV is elevated")
    if alternation_amplitude > float(config.cep_cycle_alternation_warn_log2): review_reasons.append("short-long period alternation detected")
    details["AllCycleReviewReason"] = "; ".join(review_reasons)
    if np.any(hard_cycle):
        indices = (np.where(hard_cycle)[0] + 1).astype(int).tolist()
        reason = f"interior/all-cycle phase trajectory not supported at cycle(s) {indices}"
        return None, _join_reject_reasons(reject, reason), details
    return np.asarray(rff, dtype=float), reject, details


def _apply_cepstral_boundary_cycle_guard(
    rff: Optional[np.ndarray],
    reject: str,
    landmarks: np.ndarray,
    trace_debug: Mapping[str, Any],
    peer_debug: Mapping[str, Any],
    periodicity_qc: Mapping[str, Any],
    phase_wave: np.ndarray,
    envelope: np.ndarray,
    fs: int,
    edge: float,
    side: str,
    kind: str,
    t_pitch: np.ndarray,
    f0_track: np.ndarray,
    confidence: np.ndarray,
    config: RFFConfig,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Validate OFF10/ON1 without imposing a desired sign or normative value."""
    lm = np.asarray(landmarks, dtype=float)
    details: Dict[str, Any] = {"BoundaryCycleGate": "multi_evidence_boundary_validation_v23"}
    if rff is None or lm.size != 11:
        return rff, reject, details
    periods = np.diff(lm)
    idx = 9 if str(side).lower() == "off" else 0
    interior = periods[:-1] if str(side).lower() == "off" else periods[1:]
    med = float(np.nanmedian(interior)) if interior.size else np.nan
    boundary_period = float(periods[idx])
    signed_ratio = float(boundary_period / med) if np.isfinite(med) and med > 0 else np.nan
    symmetric_ratio = float(max(signed_ratio, 1.0 / signed_ratio)) if np.isfinite(signed_ratio) and signed_ratio > 0 else np.inf
    boundary_f0 = float(1.0 / boundary_period) if boundary_period > 0 else np.nan
    midpoint = float(0.5 * (lm[idx] + lm[idx + 1]))
    track_f0 = safe_float(_interp_valid(t_pitch, f0_track, np.asarray([midpoint]))[0], np.nan)
    track_conf = safe_float(_interp_valid(t_pitch, confidence, np.asarray([midpoint]), default=0.0)[0], 0.0)
    track_dev = float(abs(12.0 * math.log2(boundary_f0 / track_f0))) if np.isfinite(track_f0) and track_f0 > 0 and np.isfinite(boundary_f0) and boundary_f0 > 0 else np.nan

    peer_periods = np.asarray(peer_debug.get("periods_s", []), dtype=float)
    if peer_periods.size == 10:
        peer_boundary = float(peer_periods[idx])
        pair_dev = float(abs(12.0 * math.log2(boundary_period / peer_boundary))) if peer_boundary > 0 else np.nan
    else:
        pair_dev = np.nan

    best = periodicity_qc.get("IndependentBestCandidate", {}) if isinstance(periodicity_qc, Mapping) else {}
    best_f0 = safe_float(best.get("f0_hz"), np.nan) if isinstance(best, Mapping) else np.nan
    best_score = safe_float(best.get("score"), 0.0) if isinstance(best, Mapping) else 0.0
    independent_dev = float(abs(12.0 * math.log2(boundary_f0 / best_f0))) if np.isfinite(best_f0) and best_f0 > 0 and np.isfinite(boundary_f0) and boundary_f0 > 0 else np.nan

    extrema_count, extrema_info = _boundary_same_phase_extrema_count(phase_wave, fs, lm, side, kind, config)
    details.update(extrema_info)
    bi0 = max(0, int(math.floor(lm[idx] * fs)))
    bi1 = min(len(envelope), int(math.ceil(lm[idx + 1] * fs)) + 1)
    boundary_env = float(np.nanmedian(envelope[bi0:bi1])) if bi1 > bi0 and len(envelope) else np.nan
    selected_idx = np.asarray(np.clip(np.round(lm * fs), 0, max(0, len(envelope) - 1)), dtype=int)
    interior_env = float(np.nanmedian(envelope[selected_idx[1:-1]])) if len(envelope) and selected_idx.size > 3 else np.nan
    envelope_ratio = float(boundary_env / max(interior_env, 1e-12)) if np.isfinite(boundary_env) and np.isfinite(interior_env) else np.nan

    extreme = bool(np.isfinite(symmetric_ratio) and symmetric_ratio > float(config.cep_boundary_warn_ratio))
    track_disagree = bool(
        np.isfinite(track_dev)
        and track_dev > float(config.cep_boundary_track_warn_st)
        and track_conf >= float(config.cep_boundary_min_track_confidence)
    )
    independent_disagree = bool(
        np.isfinite(independent_dev)
        and independent_dev > float(config.cep_boundary_independent_warn_st)
        and best_score >= float(config.cep_periodicity_min_candidate_score)
    )
    pair_disagree = bool(np.isfinite(pair_dev) and pair_dev > float(config.cep_boundary_pair_warn_st))
    extra_extremum = extrema_count > 0
    low_envelope = bool(np.isfinite(envelope_ratio) and envelope_ratio < float(config.cep_boundary_min_envelope_ratio))
    strong_evidence = [track_disagree, independent_disagree, pair_disagree, extra_extremum]
    strong_evidence_count = int(sum(bool(v) for v in strong_evidence))
    evidence = strong_evidence + [low_envelope]
    evidence_count = int(sum(bool(v) for v in evidence))

    details.update({
        "BoundaryPeriod_s": boundary_period,
        "BoundaryInteriorMedianPeriod_s": med,
        "BoundaryPeriodSignedRatio": signed_ratio,
        "BoundaryPeriodRatio": symmetric_ratio,
        "BoundaryF0_Hz": boundary_f0,
        "BoundaryTrackF0_Hz": track_f0,
        "BoundaryTrackConfidence": track_conf,
        "BoundaryTrackDeviationST": track_dev,
        "BoundaryPeerDeviationST": pair_dev,
        "BoundaryIndependentBestF0_Hz": best_f0,
        "BoundaryIndependentDeviationST": independent_dev,
        "BoundaryEnvelopeRatio": envelope_ratio,
        "BoundaryEvidenceCount": evidence_count,
        "BoundaryStrongEvidenceCount": strong_evidence_count,
        "BoundaryLowEnvelopeSupportOnly": bool(low_envelope and strong_evidence_count == 0 and not extreme),
        "BoundaryEvidence": {
            "large_period_ratio": extreme,
            "track_disagreement": track_disagree,
            "independent_periodicity_disagreement": independent_disagree,
            "peak_trough_disagreement": pair_disagree,
            "extra_same_phase_extremum": extra_extremum,
            "low_boundary_envelope": low_envelope,
        },
    })

    hard_reasons: List[str] = []
    if np.isfinite(symmetric_ratio) and symmetric_ratio > float(config.cep_boundary_hard_ratio):
        hard_reasons.append("boundary period exceeds catastrophic ratio")
    if extreme and extra_extremum:
        hard_reasons.append("boundary cycle contains an additional same-phase extremum")
    if extreme and evidence_count >= 2:
        hard_reasons.append("boundary period is not supported by multiple independent checks")
    if (
        np.isfinite(track_dev) and track_dev > float(config.cep_boundary_track_hard_st)
        and track_conf >= float(config.cep_boundary_min_track_confidence)
        and independent_disagree
    ):
        hard_reasons.append("boundary cycle disagrees strongly with local and independent periodicity")
    # v22 additional severe-convergence rule: two independent pitch checks that
    # both disagree strongly are sufficient to withhold classical RFF, even when
    # the boundary-period ratio itself is not extreme.
    if (
        track_disagree and independent_disagree
        and np.isfinite(track_dev) and track_dev > 4.5
        and np.isfinite(independent_dev) and independent_dev > 4.0
    ):
        hard_reasons.append("boundary cycle fails convergent local and independent pitch checks")
    if strong_evidence_count >= 3:
        hard_reasons.append("boundary cycle has three or more independent warning sources")
    details["BoundaryManualReview"] = bool(extreme or strong_evidence_count > 0)
    details["BoundaryReviewReason"] = "; ".join([
        name for name, value in (
            ("large boundary-period ratio", extreme),
            ("local pitch-path disagreement", track_disagree),
            ("independent periodicity disagreement", independent_disagree),
            ("peak/trough disagreement", pair_disagree),
            ("extra same-phase extremum", extra_extremum),
            ("low boundary envelope", low_envelope),
        ) if value
    ])
    if hard_reasons:
        reason = "boundary cycle not independently supported: " + "; ".join(dict.fromkeys(hard_reasons))
        return None, _join_reject_reasons(reject, reason), details
    return np.asarray(rff, dtype=float), reject, details


def _finalize_cepstral_side(
    peak: Mapping[str, Any],
    trough: Mapping[str, Any],
    edge: float,
    side: str,
    y: np.ndarray,
    phase_wave: np.ndarray,
    envelope: np.ndarray,
    fs: int,
    t_pitch: np.ndarray,
    f0_track: np.ndarray,
    confidence: np.ndarray,
    reference_f0: float,
    config: RFFConfig,
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """Choose the boundary-adjacent peak/trough window using complete v21 QC."""
    source = {"peak": peak, "trough": trough}
    local_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}
    all_evaluated: List[Dict[str, Any]] = []
    best_by_phase: Dict[str, Dict[str, Any]] = {}

    for name in ("peak", "trough"):
        source_windows = list(source[name].get("windows", [])) or [source[name]]
        windows = [
            item for item in source_windows
            if int(dict(item.get("debug", {})).get("window_rank_from_edge", 0)) == 0
        ]
        if not windows:
            windows = [source[name]]
        phase_results: List[Dict[str, Any]] = []
        for window_index, item in enumerate(windows):
            trace_dbg = dict(item.get("debug", {}))
            peer_windows = list(source["trough" if name == "peak" else "peak"].get("windows", [])) or [source["trough" if name == "peak" else "peak"]]
            peer_item = min(peer_windows, key=lambda x: float(x.get("score", 1e9))) if peer_windows else {}
            peer_dbg = dict(peer_item.get("debug", {}))
            rff = item.get("rff")
            reject = str(item.get("reject", ""))
            lm = np.asarray(trace_dbg.get("selected_landmarks_s", []), dtype=float)
            gate = {
                "selected_landmarks_s": lm.tolist(),
                "candidate_landmarks_s": trace_dbg.get("raw_landmarks_s", []),
                "enforce_boundary_adjacency": True,
                "boundary_adjustment_reason": "",
            }
            rff, reject, hard_qc = _apply_hard_landmark_gate(rff, reject, gate, edge, side, config)
            rff, reject, periodicity_qc = _apply_cepstral_independent_periodicity_guard(
                rff, reject, lm, y, fs, config, edge=edge, side=side, reference_f0=reference_f0,
            )
            rff, reject, boundary_qc = _apply_cepstral_boundary_cycle_guard(
                rff, reject, lm, trace_dbg, peer_dbg, periodicity_qc,
                phase_wave, envelope, fs, edge, side, name,
                t_pitch, f0_track, confidence, config,
            )
            rff, reject, all_cycle_qc = _apply_cepstral_all_cycle_guard(
                rff, reject, lm, trace_dbg, periodicity_qc, y, phase_wave,
                envelope, fs, edge, side, name, t_pitch, f0_track,
                confidence, config, local_cache,
            )
            cycle_qc = {**hard_qc, **periodicity_qc, **boundary_qc, **all_cycle_qc}
            trace_dbg["cycle_qc"] = cycle_qc
            trace_dbg["final_valid_v23"] = rff is not None
            trace_dbg["final_reject_v23"] = reject
            base_score = float(item.get("score", 1e9))
            boundary_penalty = safe_float(trace_dbg.get("boundary_support_penalty"), 0.0)
            review_penalty = 0.20 * safe_float(cycle_qc.get("BoundaryEvidenceCount"), 0.0)
            all_cycle_penalty = safe_float(cycle_qc.get("AllCyclePenalty"), 0.0)
            final_score = base_score + boundary_penalty + review_penalty + all_cycle_penalty
            trace_dbg["final_selection_score_v23"] = final_score
            boundary_review = bool(cycle_qc.get("BoundaryManualReview", False))
            all_cycle_review = bool(cycle_qc.get("AllCycleManualReview", False))
            qc_tier = 2 if rff is None else (1 if (boundary_review or all_cycle_review) else 0)
            cycle_qc["CepstralQCStatus"] = "FAIL" if qc_tier == 2 else ("REVIEW" if qc_tier == 1 else "PASS")
            result = {
                "phase": name, "window_index": int(window_index), "rff": rff,
                "reject": reject, "score": final_score, "qc_tier": qc_tier,
                "debug": trace_dbg, "cycle_qc": cycle_qc,
            }
            phase_results.append(result)
            all_evaluated.append(result)
        best_by_phase[name] = min(phase_results, key=lambda x: float(x["score"])) if phase_results else {
            "phase": name, "window_index": -1, "rff": None,
            "reject": "no 11-landmark window", "score": 1e9,
            "debug": {"selected_landmarks_s": [], "raw_landmarks_s": [], "final_valid_v23": False},
            "cycle_qc": {},
        }

    accepted = [r for r in all_evaluated if r.get("rff") is not None]
    if accepted:
        chosen_result = min(accepted, key=lambda x: (int(x.get("qc_tier", 1)), float(x["score"])))
    else:
        chosen_result = min(all_evaluated, key=lambda x: float(x["score"])) if all_evaluated else best_by_phase["peak"]
    chosen = str(chosen_result.get("phase", "peak"))
    rff = chosen_result.get("rff")
    reject = str(chosen_result.get("reject", "")) or ("no boundary-adjacent cepstral phase trace passed v21 QC" if rff is None else "")
    cycle_qc = dict(chosen_result.get("cycle_qc", {}))

    # Direct peak/trough fields remain compatible with plotting/QC readers.
    # v23: choose the representative of each phase with the same tier-first
    # rule used for the final result. v22 used score alone here, which could
    # make debug plots/landmark exports point to a REVIEW window while the
    # numerical RFF came from a PASS window of the same phase.
    for name in ("peak", "trough"):
        phase_accepted = [r for r in all_evaluated if r["phase"] == name and r.get("rff") is not None]
        if phase_accepted:
            best_by_phase[name] = min(
                phase_accepted,
                key=lambda x: (int(x.get("qc_tier", 1)), float(x["score"])),
            )
    # The chosen phase must always expose the exact chosen window.
    if chosen in best_by_phase:
        best_by_phase[chosen] = chosen_result

    original_phase = min(("peak", "trough"), key=lambda n: float(source[n].get("score", 1e9)))
    original_window = 0
    chosen_window = int(chosen_result.get("window_index", -1))

    final_debug = dict(chosen_result.get("debug", {}))
    final_landmarks = np.asarray(final_debug.get("selected_landmarks_s", []), dtype=float)
    final_rff = None if rff is None else np.asarray(rff, dtype=float)
    consistency_error = np.nan
    consistency_ok = rff is None
    if final_rff is not None and final_rff.shape == (10,) and final_landmarks.size == 11:
        final_periods = np.diff(final_landmarks)
        if np.all(np.isfinite(final_periods)) and np.all(final_periods > 0):
            final_freqs = periods_to_freq(final_periods)
            final_base = final_freqs[0] if str(side).lower() == "off" else final_freqs[-1]
            if np.isfinite(final_base) and final_base > 0:
                recomputed_rff = hz_to_st(final_freqs, final_base)
                consistency_error = float(np.nanmax(np.abs(recomputed_rff - final_rff)))
                consistency_ok = bool(np.isfinite(consistency_error) and consistency_error <= 1e-6)
    if final_rff is not None and not consistency_ok:
        reject = _join_reject_reasons(reject, "internal final-selection RFF/landmark consistency failure")
        rff = None
        final_rff = None
        cycle_qc["CepstralQCStatus"] = "FAIL"

    cycle_qc["FinalSelectionConsistent"] = bool(consistency_ok)
    cycle_qc["FinalSelectionConsistencyErrorST"] = consistency_error
    cycle_qc["FinalChosenTrace"] = chosen
    cycle_qc["FinalChosenWindowIndex"] = chosen_window
    window_summary = [{
        "phase": r["phase"], "window_index": r["window_index"],
        "window_pool": r["debug"].get("window_pool", ""),
        "window_rank_from_edge": r["debug"].get("window_rank_from_edge", -1),
        "selected_landmarks_s": r["debug"].get("selected_landmarks_s", []),
        "valid": r.get("rff") is not None, "reject": r.get("reject", ""),
        "final_score": r.get("score", 1e9),
        "all_cycle_review": r.get("cycle_qc", {}).get("AllCycleManualReview", False),
        "all_cycle_reason": r.get("cycle_qc", {}).get("AllCycleReviewReason", ""),
    } for r in all_evaluated]
    debug = {
        "chosen": chosen,
        "chosen_window_index": chosen_window,
        "final_chosen_trace": chosen,
        "final_chosen_window_index": chosen_window,
        "final_selected_landmarks_s": final_landmarks.tolist(),
        "final_rff_st": (np.asarray(rff, dtype=float).tolist() if rff is not None else []),
        "final_selection_consistent": bool(consistency_ok),
        "final_selection_consistency_error_st": consistency_error,
        "original_lowest_score_trace": original_phase,
        "alternate_trace_reselected": bool(chosen != original_phase and rff is not None),
        "alternate_window_reselected": bool((chosen != original_phase or chosen_window != original_window) and rff is not None),
        "selection_rule": "v23 preserves v22 tier-first boundary-adjacent selection and synchronizes the exact final window across RFF, landmarks, plots, QC and debug",
        "peak": dict(best_by_phase["peak"].get("debug", {})),
        "trough": dict(best_by_phase["trough"].get("debug", {})),
        "cycle_qc": cycle_qc,
        "window_search": window_summary,
        "window_candidate_count": int(len(all_evaluated)),
    }
    return None if rff is None else np.asarray(rff, dtype=float), reject, debug

def _cepstral_transition_proxy(t: np.ndarray, f0: np.ndarray, confidence: np.ndarray, edge: float, side: str, f_ref: float) -> Dict[str, Any]:
    """Exploratory framewise transition index; deliberately not labelled RFF."""
    if not np.isfinite(f_ref) or f_ref <= 0:
        return {"valid": False, "reason": "no reference F0", "exploratory_not_classical_rff": True}
    period = 1.0 / float(f_ref)
    if side == "off":
        times = edge - (np.arange(10, dtype=float)[::-1] + 0.5) * period
    else:
        times = edge + (np.arange(10, dtype=float) + 0.5) * period
    sampled_f0 = _interp_valid(t, f0, times)
    sampled_conf = _interp_valid(t, confidence, times, default=0.0)
    sampled_f0[sampled_conf < 0.15] = np.nan
    finite = np.isfinite(sampled_f0) & (sampled_f0 > 0)
    if np.sum(finite) < 6:
        values = np.full(10, np.nan)
        valid = False
        reason = "fewer than 6 confident framewise F0 samples"
    else:
        base_idx = int(np.where(finite)[0][0] if side == "off" else np.where(finite)[0][-1])
        values = 12.0 * np.log2(sampled_f0 / sampled_f0[base_idx])
        valid = True
        reason = ""
    return {
        "valid": valid, "reason": reason, "exploratory_not_classical_rff": True,
        "name": "Cepstral Transition F0 Index (cTFI)", "side": side.upper(),
        "sample_times_s": times.tolist(), "sampled_f0_hz": sampled_f0.tolist(),
        "sampled_confidence": sampled_conf.tolist(), "values_st": values.tolist(),
        "reference_rule": "OFF=earliest confident frame; ON=latest confident frame",
    }


_CEPSTRAL_TRACK_CACHE: Dict[Tuple[Any, ...], Tuple[np.ndarray, int, np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]] = {}


def _cached_cepstral_track(wav_path: str, config: RFFConfig) -> Tuple[np.ndarray, int, np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    """Reuse the expensive pitch path for the three ROIs in the same WAV."""
    path = pathlib.Path(wav_path).resolve()
    stat = path.stat()
    settings = (
        config.f0_floor, config.f0_ceiling, config.cep_hop_s,
        config.cep_frame_short_s, config.cep_frame_medium_s, config.cep_frame_long_s,
        config.cep_max_candidates, config.cep_min_confidence, config.cep_min_ac_strength,
        config.cep_max_interp_gap_frames,
    )
    key = (str(path).lower(), int(stat.st_size), int(stat.st_mtime_ns), settings)
    cached = _CEPSTRAL_TRACK_CACHE.get(key)
    if cached is not None:
        return cached
    y, fs = read_audio(str(path))
    y = normalize_audio_for_display(y)
    t_pitch, f0_track, confidence, tracker_debug = cepstral_f0_track_detailed(y, fs, config)
    value = (y, fs, t_pitch, f0_track, confidence, tracker_debug)
    _CEPSTRAL_TRACK_CACHE[key] = value
    while len(_CEPSTRAL_TRACK_CACHE) > 8:
        _CEPSTRAL_TRACK_CACHE.pop(next(iter(_CEPSTRAL_TRACK_CACHE)))
    return value


def compute_cepstral_rff(
    wav_path: str,
    subject: str,
    token: str,
    rep: int,
    fric_start: float,
    fric_end: float,
    config: RFFConfig,
) -> TraceResult:
    """Robust cepstral-assisted *classical* 10-cycle RFF.

    The cepstrum does not create RFF when no periodic cycles exist. It supplies a
    confidence-bearing, octave-aware F0 path. Final RFF is calculated only from
    ten analytic-phase periods that pass boundary and all-cycle agreement/QC gates. A separate
    cTFI framewise proxy is saved for exploratory work in irregular voices.
    """
    y, fs, t_pitch, f0_track, confidence, tracker_debug = _cached_cepstral_track(wav_path, config)
    dur = len(y) / float(fs)
    fric_start = float(max(0.0, min(dur, fric_start)))
    fric_end = float(max(fric_start, min(dur, fric_end)))
    off_mask = (t_pitch >= max(0.0, fric_start - 0.35)) & (t_pitch <= max(0.0, fric_start - 0.02)) & np.isfinite(f0_track)
    on_mask = (t_pitch >= min(dur, fric_end + 0.02)) & (t_pitch <= min(dur, fric_end + 0.35)) & np.isfinite(f0_track)
    all_voiced = f0_track[np.isfinite(f0_track) & (f0_track > 0)]
    global_f0 = float(np.nanmedian(all_voiced)) if all_voiced.size else np.nan
    off_f0 = float(np.nanmedian(f0_track[off_mask])) if np.any(off_mask) else global_f0
    on_f0 = float(np.nanmedian(f0_track[on_mask])) if np.any(on_mask) else global_f0
    band_ref = float(np.nanmedian([v for v in (off_f0, on_f0, global_f0) if np.isfinite(v) and v > 0])) if any(np.isfinite(v) and v > 0 for v in (off_f0, on_f0, global_f0)) else np.nan

    if np.isfinite(band_ref) and band_ref > 0:
        band_lo = max(30.0, config.f0_floor * 0.55, band_ref * config.cep_phase_band_low_ratio)
        band_hi = min(0.45 * fs, config.f0_ceiling * 1.20, band_ref * config.cep_phase_band_high_ratio)
        phase_wave = _safe_bandpass_filter(y, fs, band_lo, band_hi, order=3)
        analytic = sp_signal.hilbert(phase_wave)
        phase = np.unwrap(np.angle(analytic))
        envelope = np.abs(analytic)
        peak_all = _phase_crossings(phase, fs, 0.0)
        trough_all = _phase_crossings(phase, fs, np.pi)
    else:
        band_lo = np.nan
        band_hi = np.nan
        phase_wave = np.zeros_like(y)
        envelope = np.zeros_like(y)
        peak_all = np.asarray([], dtype=float)
        trough_all = np.asarray([], dtype=float)

    # Retain only crossings with local vowel energy and at least weak pitch-path
    # support. These are candidates, not automatically accepted cycles.
    def qualified(crossings: np.ndarray, edge: float, side: str, ref_f0: float) -> np.ndarray:
        if crossings.size == 0 or not np.isfinite(ref_f0):
            return np.asarray([], dtype=float)
        if side == "off":
            side_mask = (crossings < edge) & (crossings >= max(0.0, edge - config.edge_pad_s))
            env_ref_mask = (np.arange(envelope.size) / fs >= max(0.0, edge - 0.30)) & (np.arange(envelope.size) / fs < edge)
        else:
            side_mask = (crossings > edge) & (crossings <= min(dur, edge + config.edge_pad_s))
            env_ref_mask = (np.arange(envelope.size) / fs > edge) & (np.arange(envelope.size) / fs <= min(dur, edge + 0.30))
        c = crossings[side_mask]
        if c.size == 0:
            return c
        idx = np.asarray(np.clip(np.round(c * fs), 0, envelope.size - 1), dtype=int)
        ref_env = float(np.nanmedian(envelope[env_ref_mask])) if np.any(env_ref_mask) else float(np.nanmedian(envelope))
        local_conf = _interp_valid(t_pitch, confidence, c, default=0.0)
        keep = (envelope[idx] >= config.cep_phase_min_envelope_ratio * max(ref_env, 1e-12)) & (local_conf >= 0.50 * config.cep_min_confidence)
        return c[keep]

    off_peak_c = qualified(peak_all, fric_start, "off", off_f0)
    off_trough_c = qualified(trough_all, fric_start, "off", off_f0)
    on_peak_c = qualified(peak_all, fric_end, "on", on_f0)
    on_trough_c = qualified(trough_all, fric_end, "on", on_f0)
    off_peak = _cepstral_phase_trace(off_peak_c, peak_all, envelope, fs, fric_start, "off", t_pitch, f0_track, confidence, config)
    off_trough = _cepstral_phase_trace(off_trough_c, trough_all, envelope, fs, fric_start, "off", t_pitch, f0_track, confidence, config)
    on_peak = _cepstral_phase_trace(on_peak_c, peak_all, envelope, fs, fric_end, "on", t_pitch, f0_track, confidence, config)
    on_trough = _cepstral_phase_trace(on_trough_c, trough_all, envelope, fs, fric_end, "on", t_pitch, f0_track, confidence, config)
    off_rff, off_rej, off_debug = _finalize_cepstral_side(
        off_peak, off_trough, fric_start, "off", y, phase_wave, envelope, fs,
        t_pitch, f0_track, confidence, off_f0, config,
    )
    on_rff, on_rej, on_debug = _finalize_cepstral_side(
        on_peak, on_trough, fric_end, "on", y, phase_wave, envelope, fs,
        t_pitch, f0_track, confidence, on_f0, config,
    )

    def chosen_landmarks(side_debug: Mapping[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
        chosen = str(side_debug.get("chosen", ""))
        trace = side_debug.get(chosen, {}) if chosen in {"peak", "trough"} else {}
        final = np.asarray(side_debug.get("final_selected_landmarks_s", []), dtype=float)
        if final.size != 11:
            final = np.asarray(trace.get("selected_landmarks_s", []), dtype=float)
        return final, np.asarray(trace.get("raw_landmarks_s", []), dtype=float)

    off_lm, off_candidates = chosen_landmarks(off_debug)
    on_lm, on_candidates = chosen_landmarks(on_debug)

    return TraceResult(
        method="RFF_CEPSTRAL", subject=subject, filename=os.path.basename(wav_path), filepath=wav_path,
        token=token, rep=rep, fric_start=fric_start, fric_end=fric_end,
        off_rff=off_rff, on_rff=on_rff, off_valid=off_rff is not None, on_valid=on_rff is not None,
        off_reject=off_rej, on_reject=on_rej,
        n_off_landmarks=int(off_lm.size) if off_rff is not None else 0,
        n_on_landmarks=int(on_lm.size) if on_rff is not None else 0,
        debug={
            "implementation_stamp": SCRIPT_VERSION,
            "algorithm_family": "robust_cepstral_ac_viterbi_plus_analytic_phase_classical_10_cycle_rff_v23_final_selection_sync",
            "pitch_source": "multiresolution_cepstrum_plus_normalized_autocorrelation",
            "scientific_scope": "classical RFF requires accepted cycles; cTFI is exploratory and is not RFF",
            "off_f0_hz": off_f0, "on_f0_hz": on_f0, "global_f0_hz": global_f0,
            "phase_band_hz": [band_lo, band_hi], "tracker_debug": tracker_debug,
            "cepstral_transition_proxy": {
                "OFF": _cepstral_transition_proxy(t_pitch, f0_track, confidence, fric_start, "off", off_f0),
                "ON": _cepstral_transition_proxy(t_pitch, f0_track, confidence, fric_end, "on", on_f0),
            },
            "off_debug": off_debug, "on_debug": on_debug,
        },
    )



# =============================================================================
# External MATLAB ROI bridge integration (MB and aRFF-AP)
# =============================================================================

def matlab_quote(text: str) -> str:
    """Quote a string for use inside MATLAB single-quoted string literals."""
    return str(text).replace("'", "''")


def bool_from_any(value: Any) -> bool:
    """Robustly convert MATLAB/Python/CSV boolean-like values to bool."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None:
        return False
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(value):
            return bool(int(value))
    except Exception:
        pass
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y", "sim", "valid"}


def package_default_dir(folder_name: str) -> str:
    try:
        return str((pathlib.Path(__file__).resolve().parent / folder_name).resolve())
    except Exception:
        return folder_name


def prepare_matlab_manifest(roi_df: pd.DataFrame, out_dir: str | pathlib.Path, cfg: Optional[RFFConfig] = None) -> str:
    """Write a manifest with the column names expected by both MATLAB bridges.

    v16 deliberately does not precompute MB pulses in Python. The original MB
    MATLAB -> Praat extraction and sliding-window voting path is authoritative.
    """
    out = pathlib.Path(out_dir)
    ensure_dir(out)
    df = roi_df.copy()
    if "Filepath" not in df.columns:
        if "Path" in df.columns:
            df["Filepath"] = df["Path"]
        elif "filepath" in df.columns:
            df["Filepath"] = df["filepath"]
    if "Filename" not in df.columns and "Filepath" in df.columns:
        df["Filename"] = df["Filepath"].apply(lambda x: pathlib.Path(str(x)).name)
    if "FricLoc" not in df.columns and {"FricStart", "FricEnd"}.issubset(df.columns):
        df["FricLoc"] = (pd.to_numeric(df["FricStart"], errors="coerce") + pd.to_numeric(df["FricEnd"], errors="coerce")) / 2.0
    # Keep the legacy column empty for bridge-schema compatibility. The v16
    # MB bridge ignores it and always calls Praat from MATLAB.
    df["PrecomputedPulsesJSON"] = "[]"

    # Keep Path too, for traceability, but ensure Filepath is present for AP.
    preferred = ["Subject", "Filename", "Token", "Rep", "Path", "Filepath", "FricStart", "FricEnd", "FricLoc", "AgeGroup", "Sex", "PrecomputedPulsesJSON"]
    ordered = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[ordered]
    manifest = out / "rff_roi_marks_MATLAB_MANIFEST.csv"
    df.to_csv(manifest, index=False, encoding="utf-8-sig")
    return str(manifest)


def _terminate_process_tree(proc: Optional[subprocess.Popen]) -> None:
    """Terminate MATLAB and any child process created by the batch run."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, text=True, timeout=10,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass


def run_matlab_batch_command(
    matlab_exe: str,
    command_text: str,
    timeout_s: int = 7200,
    stop_event: Optional[threading.Event] = None,
    process_callback: Optional[Any] = None,
) -> Tuple[int, str, str, List[str]]:
    """Run MATLAB with cooperative cancellation and return command output."""
    matlab_exe = str(matlab_exe or "matlab").strip() or "matlab"
    cmd = [matlab_exe, "-batch", command_text]
    proc: Optional[subprocess.Popen] = None
    try:
        _raise_if_stopped(stop_event)
        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **popen_kwargs)
        if process_callback is not None:
            process_callback(proc)
        started = time.time()
        while True:
            if stop_event is not None and stop_event.is_set():
                _terminate_process_tree(proc)
                stdout, stderr = proc.communicate(timeout=5)
                return 130, stdout or "", (stderr or "") + "\nMATLAB stopped by user.", cmd
            if (time.time() - started) > int(timeout_s):
                _terminate_process_tree(proc)
                stdout, stderr = proc.communicate(timeout=5)
                return 124, stdout or "", (stderr or "") + f"\nMATLAB command timed out after {timeout_s} seconds", cmd
            try:
                stdout, stderr = proc.communicate(timeout=0.25)
                return int(proc.returncode or 0), stdout or "", stderr or "", cmd
            except subprocess.TimeoutExpired:
                continue
    except RunStopped:
        return 130, "", "MATLAB start cancelled by user.", cmd
    except FileNotFoundError as exc:
        return 127, "", str(exc), cmd
    except Exception as exc:
        return 1, "", repr(exc), cmd
    finally:
        if process_callback is not None:
            try:
                process_callback(None)
            except Exception:
                pass


def run_mb_matlab_bridge(
    manifest_path: str, out_dir: str | pathlib.Path, cfg: RFFConfig,
    stop_event: Optional[threading.Event] = None, process_callback: Optional[Any] = None,
) -> Tuple[int, str, str, List[str], Dict[str, str]]:
    bridge_dir = pathlib.Path(cfg.mb_bridge_dir or package_default_dir("rff_auto_mb_roi_bridge")).resolve()
    method_file = bridge_dir / "RFF_auto_MB_ROI_bridge.m"
    out = pathlib.Path(out_dir) / "matlab_mb_roi"
    ensure_dir(out)
    if not method_file.exists():
        return 2, "", f"RFF_auto_MB_ROI_bridge.m not found in {bridge_dir}", [], {}
    if not str(cfg.praat_path).strip():
        return 2, "", "Praat executable is required for the MATLAB MB bridge.", [], {}
    cmd_text = (
        f"addpath('{matlab_quote(str(bridge_dir))}'); "
        f"RFF_auto_MB_ROI_bridge('{matlab_quote(str(pathlib.Path(manifest_path).resolve()))}',"
        f"'{matlab_quote(str(out.resolve()))}',"
        f"'{matlab_quote(str(cfg.praat_path))}',"
        f"'MethodLabel','RFF_MB_ROI_MATLAB');"
    )
    rc, stdout, stderr, cmd = run_matlab_batch_command(
        cfg.matlab_path, cmd_text, cfg.matlab_timeout_s, stop_event, process_callback
    )
    files = {
        "wide": str(out / "rff_mb_roi_results_wide.csv"),
        "long": str(out / "rff_mb_roi_cycles_long.csv"),
        "debug": str(out / "rff_mb_roi_debug.csv"),
        "landmarks": str(out / "rff_mb_roi_landmarks_long.csv"),
        "cycle_qc": str(out / "rff_mb_roi_cycle_qc.csv"),
        "config": str(out / "rff_mb_roi_config.json"),
    }
    return rc, stdout, stderr, cmd, files


def run_ap_matlab_bridge(
    manifest_path: str, out_dir: str | pathlib.Path, cfg: RFFConfig,
    stop_event: Optional[threading.Event] = None, process_callback: Optional[Any] = None,
) -> Tuple[int, str, str, List[str], Dict[str, str]]:
    bridge_dir = pathlib.Path(cfg.ap_bridge_dir or package_default_dir("aRFF_AP_ROI_bridge")).resolve()
    method_file = bridge_dir / "run_arff_ap_roi_bridge.m"
    out = pathlib.Path(out_dir) / "matlab_arff_ap_roi"
    ensure_dir(out)
    if not method_file.exists():
        return 2, "", f"run_arff_ap_roi_bridge.m not found in {bridge_dir}", [], {}
    cmd_text = (
        f"addpath('{matlab_quote(str(bridge_dir))}'); "
        f"run_arff_ap_roi_bridge('{matlab_quote(str(pathlib.Path(manifest_path).resolve()))}', "
        f"'{matlab_quote(str(out.resolve()))}', "
        f"'{matlab_quote(str(bridge_dir))}');"
    )
    rc, stdout, stderr, cmd = run_matlab_batch_command(
        cfg.matlab_path, cmd_text, cfg.matlab_timeout_s, stop_event, process_callback
    )
    files = {
        "wide": str(out / "rff_arff_ap_roi_results_wide.csv"),
        "long": str(out / "rff_arff_ap_roi_cycles_long.csv"),
        "debug": str(out / "rff_arff_ap_roi_debug.csv"),
        "landmarks": str(out / "rff_arff_ap_roi_landmarks_long.csv"),
        "cycle_qc": str(out / "rff_arff_ap_roi_cycle_qc.csv"),
        "config": str(out / "rff_arff_ap_roi_config.json"),
    }
    return rc, stdout, stderr, cmd, files

def metadata_for_subject(subject: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> Dict[str, Any]:
    direct = metadata_by_subject.get(str(subject), {}) if metadata_by_subject else {}
    if not direct and metadata_by_subject:
        direct = metadata_by_subject.get(subject_base_id(str(subject)), {})
    direct_age = str(direct.get("AgeGroup", "")).strip()
    direct_sex = _normalize_sex_label(direct.get("Sex", ""))
    has_age = direct_age in VOJTECH_OFF10_THRESH_BY_AGE
    has_sex = direct_sex in VOJTECH_ON1_THRESH_BY_SEX
    if has_age and has_sex:
        source = "participant_metadata"
    elif has_age or has_sex:
        source = "partial_participant_metadata_with_gui_default"
    else:
        source = "gui_default"
    eligible = bool((has_age and has_sex) or cfg.allow_default_metadata_for_normative)
    return {
        "AgeGroup": direct_age if has_age else str(cfg.default_age_group),
        "Sex": direct_sex if has_sex else str(cfg.default_sex),
        "MetadataSource": source,
        "NormativeEligible": eligible,
        "NormativeStatus": (
            "eligible_participant_metadata" if has_age and has_sex
            else "eligible_explicit_default_override" if cfg.allow_default_metadata_for_normative
            else "not_eligible_missing_participant_metadata"
        ),
    }


def standardize_external_wide_df(df: pd.DataFrame, method_label: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> pd.DataFrame:
    df = df.copy()
    rename_map = {
        "OriginalFilepath": "Filepath",
        "OriginalFilename": "Filename",
        "OffRejectLabel": "OffReject",
        "OnRejectLabel": "OnReject",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    if "Filepath" not in df.columns and "Path" in df.columns:
        df["Filepath"] = df["Path"]
    if "Filename" not in df.columns and "Filepath" in df.columns:
        df["Filename"] = df["Filepath"].apply(lambda x: pathlib.Path(str(x)).name)
    if "Method" not in df.columns:
        df["Method"] = method_label
    else:
        df["Method"] = method_label
    if "FricDur" not in df.columns and {"FricStart", "FricEnd"}.issubset(df.columns):
        df["FricDur"] = pd.to_numeric(df["FricEnd"], errors="coerce") - pd.to_numeric(df["FricStart"], errors="coerce")
    for c in ["OffValid", "OnValid"]:
        if c in df.columns:
            df[c] = df[c].apply(bool_from_any)
        else:
            df[c] = False
    for c in ["OffReject", "OnReject"]:
        if c not in df.columns:
            df[c] = ""
    if "NOffLandmarks" not in df.columns:
        df["NOffLandmarks"] = pd.to_numeric(df.get("NOffFinalLandmarks", np.nan), errors="coerce")
    if "NOnLandmarks" not in df.columns:
        df["NOnLandmarks"] = pd.to_numeric(df.get("NOnFinalLandmarks", np.nan), errors="coerce")
    for c in ["Subject", "Token", "Rep", "FricStart", "FricEnd"]:
        if c not in df.columns:
            df[c] = "" if c in {"Subject", "Token"} else np.nan
    # Add metadata, preserving any non-empty values already present.
    age_vals = []
    sex_vals = []
    metadata_sources = []
    normative_eligible = []
    normative_status = []
    for subj in df["Subject"].astype(str):
        meta = metadata_for_subject(subj, metadata_by_subject, cfg)
        age_vals.append(meta["AgeGroup"])
        sex_vals.append(meta["Sex"])
        metadata_sources.append(meta["MetadataSource"])
        normative_eligible.append(meta["NormativeEligible"])
        normative_status.append(meta["NormativeStatus"])
    if "AgeGroup" not in df.columns:
        df["AgeGroup"] = age_vals
    else:
        df["AgeGroup"] = df["AgeGroup"].fillna("").astype(str)
        df.loc[df["AgeGroup"].str.len() == 0, "AgeGroup"] = age_vals
    if "Sex" not in df.columns:
        df["Sex"] = sex_vals
    else:
        df["Sex"] = df["Sex"].fillna("").astype(str)
        df.loc[df["Sex"].str.len() == 0, "Sex"] = sex_vals
    df["MetadataSource"] = metadata_sources
    df["NormativeEligible"] = normative_eligible
    df["NormativeStatus"] = normative_status
    df["ScriptVersion"] = SCRIPT_VERSION
    df["AlgorithmFamily"] = method_label
    if method_label == "RFF_MB_ROI_MATLAB":
        if "PitchSource" not in df.columns:
            df["PitchSource"] = "MATLAB pitch() + original MB MATLAB/Praat pulse path"
        else:
            df["PitchSource"] = df["PitchSource"].fillna("MATLAB pitch() + original MB MATLAB/Praat pulse path")
    elif method_label == "RFF_AP_ROI_MATLAB":
        df["PitchSource"] = "MATLAB aRFF-AP Auditory-SWIPE peak/trough"
    else:
        df["PitchSource"] = "MATLAB bridge"
    # Guarantee the primary RFF columns exist.
    for i in range(1, 11):
        if f"OFF{i}" not in df.columns:
            df[f"OFF{i}"] = np.nan
        if f"ON{i}" not in df.columns:
            df[f"ON{i}"] = np.nan
    if "OFF10" not in df.columns:
        df["OFF10"] = df["OFF10"] if "OFF10" in df.columns else df.get("OFF10", np.nan)
    if "ON1" not in df.columns:
        df["ON1"] = df["ON1"] if "ON1" in df.columns else df.get("ON1", np.nan)
    return df


def standardize_external_long_df(df: pd.DataFrame, method_label: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> pd.DataFrame:
    df = df.copy()
    if "OriginalFilepath" in df.columns and "Filepath" not in df.columns:
        df["Filepath"] = df["OriginalFilepath"]
    if "OriginalFilename" in df.columns and "Filename" not in df.columns:
        df["Filename"] = df["OriginalFilename"]
    if "RejectLabel" in df.columns and "Reject" not in df.columns:
        df["Reject"] = df["RejectLabel"]
    df["Method"] = method_label
    if "ValidSide" in df.columns:
        df["ValidSide"] = df["ValidSide"].apply(bool_from_any)
    else:
        df["ValidSide"] = False
    if "Reject" not in df.columns:
        df["Reject"] = ""
    for c in ["Subject", "Filename", "Filepath", "Token", "Rep", "Side", "Cycle", "RFF_ST"]:
        if c not in df.columns:
            df[c] = "" if c in {"Subject", "Filename", "Filepath", "Token", "Side"} else np.nan
    age_vals = []
    sex_vals = []
    metadata_sources = []
    normative_eligible = []
    normative_status = []
    for subj in df["Subject"].astype(str):
        meta = metadata_for_subject(subj, metadata_by_subject, cfg)
        age_vals.append(meta["AgeGroup"])
        sex_vals.append(meta["Sex"])
        metadata_sources.append(meta["MetadataSource"])
        normative_eligible.append(meta["NormativeEligible"])
        normative_status.append(meta["NormativeStatus"])
    df["AgeGroup"] = age_vals
    df["Sex"] = sex_vals
    df["MetadataSource"] = metadata_sources
    df["NormativeEligible"] = normative_eligible
    df["NormativeStatus"] = normative_status
    return df


def standardize_external_debug_df(df: pd.DataFrame, method_label: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> pd.DataFrame:
    df = df.copy()
    df["Method"] = method_label
    if "OriginalFilename" in df.columns and "Filename" not in df.columns:
        df["Filename"] = df["OriginalFilename"]
    if "RejectLabel" in df.columns and "Reject" not in df.columns:
        df["Reject"] = df["RejectLabel"]
    df["ScriptVersion"] = SCRIPT_VERSION
    df["AlgorithmFamily"] = method_label
    df["PitchSource"] = "MATLAB bridge"
    if "Subject" in df.columns:
        metadata = [metadata_for_subject(subj, metadata_by_subject, cfg) for subj in df["Subject"].astype(str)]
        df["AgeGroup"] = [item["AgeGroup"] for item in metadata]
        df["Sex"] = [item["Sex"] for item in metadata]
        df["MetadataSource"] = [item["MetadataSource"] for item in metadata]
        df["NormativeEligible"] = [item["NormativeEligible"] for item in metadata]
        df["NormativeStatus"] = [item["NormativeStatus"] for item in metadata]
    return df


def load_external_bridge_outputs(files: Mapping[str, str], method_label: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    wide_path = pathlib.Path(files.get("wide", ""))
    long_path = pathlib.Path(files.get("long", ""))
    debug_path = pathlib.Path(files.get("debug", ""))
    if not wide_path.exists():
        raise FileNotFoundError(f"Expected external wide output not found: {wide_path}")
    wide_df = pd.read_csv(wide_path)
    wide_df = standardize_external_wide_df(wide_df, method_label, metadata_by_subject, cfg)
    if long_path.exists():
        long_df = pd.read_csv(long_path)
        long_df = standardize_external_long_df(long_df, method_label, metadata_by_subject, cfg)
    else:
        long_df = pd.DataFrame()
    if debug_path.exists():
        debug_df = pd.read_csv(debug_path)
        debug_df = standardize_external_debug_df(debug_df, method_label, metadata_by_subject, cfg)
    else:
        debug_df = pd.DataFrame()
    return wide_df.to_dict(orient="records"), long_df.to_dict(orient="records"), debug_df.to_dict(orient="records")


def failed_external_rows(roi_df: pd.DataFrame, method_label: str, message: str, metadata_by_subject: Mapping[str, Mapping[str, str]], cfg: RFFConfig) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    wide_rows: List[Dict[str, Any]] = []
    long_rows: List[Dict[str, Any]] = []
    debug_rows: List[Dict[str, Any]] = []
    for _, row in roi_df.iterrows():
        filepath = str(row.get("Filepath", row.get("Path", "")))
        subject = str(row.get("Subject", "")) or subject_from_filename(filepath, str(row.get("Token", "")))
        token = str(row.get("Token", token_from_filename(filepath) or "")).lower()
        filename = str(row.get("Filename", pathlib.Path(filepath).name))
        rep = safe_float(row.get("Rep", np.nan), np.nan)
        fst = safe_float(row.get("FricStart", np.nan), np.nan)
        fend = safe_float(row.get("FricEnd", np.nan), np.nan)
        meta = metadata_for_subject(subject, metadata_by_subject, cfg)
        w = {
            "ScriptVersion": SCRIPT_VERSION,
            "AlgorithmFamily": method_label,
            "PitchSource": "MATLAB bridge",
            "Method": method_label,
            "Subject": subject,
            "Filename": filename,
            "Filepath": filepath,
            "Token": token,
            "Rep": rep,
            "FricStart": fst,
            "FricEnd": fend,
            "FricDur": fend - fst if np.isfinite(fst) and np.isfinite(fend) else np.nan,
            "OffValid": False,
            "OnValid": False,
            "OffReject": message,
            "OnReject": message,
            "NOffLandmarks": 0,
            "NOnLandmarks": 0,
            "AgeGroup": meta["AgeGroup"],
            "Sex": meta["Sex"],
            "MetadataSource": meta["MetadataSource"],
            "NormativeEligible": meta["NormativeEligible"],
            "NormativeStatus": meta["NormativeStatus"],
        }
        for i in range(1, 11):
            w[f"OFF{i}"] = np.nan
            w[f"ON{i}"] = np.nan
        w["OFF10"] = np.nan
        w["ON1"] = np.nan
        wide_rows.append(w)
        for side in ("OFF", "ON"):
            for cycle in range(1, 11):
                long_rows.append({
                    "Method": method_label,
                    "Subject": subject,
                    "Filename": filename,
                    "Filepath": filepath,
                    "Token": token,
                    "Rep": rep,
                    "Side": side,
                    "Cycle": cycle,
                    "RFF_ST": np.nan,
                    "ValidSide": False,
                    "Reject": message,
                    "AgeGroup": meta["AgeGroup"],
                    "Sex": meta["Sex"],
                    "MetadataSource": meta["MetadataSource"],
                    "NormativeEligible": meta["NormativeEligible"],
                    "NormativeStatus": meta["NormativeStatus"],
                })
        debug_rows.append({
            "ScriptVersion": SCRIPT_VERSION,
            "AlgorithmFamily": method_label,
            "PitchSource": "MATLAB bridge",
            "Method": method_label,
            "Subject": subject,
            "Filename": filename,
            "Token": token,
            "Rep": rep,
            "FricStart": fst,
            "FricEnd": fend,
            "OffValid": False,
            "OnValid": False,
            "OffReject": message,
            "OnReject": message,
            "MetadataSource": meta["MetadataSource"],
            "NormativeEligible": meta["NormativeEligible"],
            "NormativeStatus": meta["NormativeStatus"],
            "DebugJSON": json.dumps({"external_bridge_error": message}, ensure_ascii=False),
        })
    return wide_rows, long_rows, debug_rows


# =============================================================================
# Optional RFF spatiotemporal-index (STI) post-processing — v25
# =============================================================================

def _sti_bias_correction_factor(n_traces: int) -> float:
    """Finite-sample correction used for the bias-corrected STI.

    The factor is sqrt((k-1)/2) * Gamma((k-1)/2) / Gamma(k/2), where k is
    the number of repeated trajectories. Log-gamma is used for numerical
    stability. The factor is undefined for fewer than two trajectories.
    """
    k = int(n_traces)
    if k < 2:
        return np.nan
    return float(math.exp(
        0.5 * math.log((k - 1) / 2.0)
        + math.lgamma((k - 1) / 2.0)
        - math.lgamma(k / 2.0)
    ))


def _normalize_rff_trace_for_sti(
    values: Sequence[float],
    interpolation_points: int = 1000,
    sample_points: int = 50,
) -> Optional[np.ndarray]:
    """Z-score and spline-normalize one complete 10-cycle RFF trajectory.

    Each trace is standardized using its sample standard deviation, interpolated
    with a not-a-knot cubic spline, and sampled at the midpoint of equally sized
    blocks. The default 1000/50 settings reproduce the RFF STI implementation
    used in the accompanying methodological analysis.
    """
    x = np.asarray(values, dtype=float)
    if x.size != 10 or not np.all(np.isfinite(x)):
        return None
    sd = float(np.std(x, ddof=1))
    if not np.isfinite(sd) or sd <= 1e-12:
        return None
    z = (x - float(np.mean(x))) / sd
    n_interp = max(100, int(interpolation_points))
    n_sample = max(2, min(int(sample_points), n_interp))
    source_x = np.linspace(0.0, 1.0, x.size)
    target_x = np.linspace(0.0, 1.0, n_interp)
    interpolated = CubicSpline(source_x, z)(target_x)
    # Midpoint of each equal block. With 1000/50 this yields zero-based indices
    # 9, 29, ..., 989, corresponding to 1-based points 10, 30, ..., 990.
    block_edges = np.linspace(0, n_interp, n_sample + 1, dtype=int)
    indices = np.asarray([
        min(n_interp - 1, max(0, (int(block_edges[i]) + int(block_edges[i + 1]) - 1) // 2))
        for i in range(n_sample)
    ], dtype=int)
    return np.asarray(interpolated[indices], dtype=float)


def build_rff_sti_tables(
    long_df: pd.DataFrame,
    config: RFFConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calculate optional participant-level RFF STI tables.

    STI is calculated independently for each Subject × Method × Side using
    complete valid 10-cycle trajectories. At least ``sti_min_traces`` repeated
    trajectories are required; the default is two. The function returns:

    1. participant/method/side STI estimates;
    2. method-level descriptive summary;
    3. 50-point participant STI profiles (mean and SD across traces);
    4. trace-level audit records.

    This is post-processing only. It never changes RFF values, cycle validity,
    rejection codes, or the native MB/aRFF-AP outputs.
    """
    subject_columns = [
        "Subject", "Method", "Side", "NTracesAvailable", "NTracesUsed",
        "STIStatus", "STI_raw", "STI_bias_corrected", "BiasCorrectionFactor",
        "BoundaryCycle", "BoundaryMean_ST", "BoundarySD_ST",
        "AgeGroup", "Sex", "MetadataSource", "NormativeEligible", "NormativeStatus",
        "STIInterpolationPoints", "STISamplePoints", "STIMinTraces",
        "STIImplementation",
    ]
    summary_columns = [
        "Method", "Side", "SubjectsObserved", "SubjectsCalculable",
        "SubjectsInsufficientTraces", "MeanTracesUsed", "MedianTracesUsed",
        "Mean_STI_bias_corrected", "SD_STI_bias_corrected",
        "Median_STI_bias_corrected", "Q1_STI_bias_corrected", "Q3_STI_bias_corrected",
    ]
    profile_columns = [
        "Subject", "Method", "Side", "NTracesUsed", "ProfilePoint",
        "NormalizedPosition", "MeanNormalizedRFF", "SDNormalizedRFF",
    ]
    audit_columns = [
        "Subject", "Method", "Filename", "Filepath", "Token", "Rep", "Side",
        "TraceStatus", "TraceReason", "BoundaryCycle", "BoundaryValue_ST",
        "TraceMean_ST", "TraceSD_ST",
    ]
    if long_df is None or long_df.empty:
        return (
            pd.DataFrame(columns=subject_columns),
            pd.DataFrame(columns=summary_columns),
            pd.DataFrame(columns=profile_columns),
            pd.DataFrame(columns=audit_columns),
        )

    required = {"Subject", "Method", "Token", "Rep", "Side", "Cycle", "RFF_ST", "ValidSide"}
    missing = sorted(required.difference(long_df.columns))
    if missing:
        raise ValueError("STI calculation requires columns: " + ", ".join(missing))

    df = long_df.copy()
    df["Cycle"] = pd.to_numeric(df["Cycle"], errors="coerce")
    df["RFF_ST"] = pd.to_numeric(df["RFF_ST"], errors="coerce")
    df["ValidSide"] = df["ValidSide"].apply(bool_from_any)
    df["Side"] = df["Side"].astype(str).str.upper()
    min_traces = max(2, int(getattr(config, "sti_min_traces", 2)))
    interpolation_points = max(100, int(getattr(config, "sti_interpolation_points", 1000)))
    sample_points = max(2, min(int(getattr(config, "sti_sample_points", 50)), interpolation_points))

    trace_group_cols = ["Subject", "Method", "Token", "Rep", "Side"]
    normalized_by_group: Dict[Tuple[str, str, str], List[np.ndarray]] = {}
    boundary_by_group: Dict[Tuple[str, str, str], List[float]] = {}
    metadata_by_group: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    audit_rows: List[Dict[str, Any]] = []

    for key, group in df.groupby(trace_group_cols, dropna=False, sort=False):
        subject, method, token, rep, side = key
        group = group.sort_values("Cycle")
        filename = str(group["Filename"].dropna().iloc[0]) if "Filename" in group and group["Filename"].dropna().size else ""
        filepath = str(group["Filepath"].dropna().iloc[0]) if "Filepath" in group and group["Filepath"].dropna().size else ""
        cycle_values = group.drop_duplicates("Cycle", keep="first")
        cycles = pd.to_numeric(cycle_values["Cycle"], errors="coerce").to_numpy(float)
        values = pd.to_numeric(cycle_values["RFF_ST"], errors="coerce").to_numpy(float)
        valid_side = bool(group["ValidSide"].apply(bool_from_any).all())
        status = "included"
        reason = ""
        normalized = None
        if not valid_side:
            status, reason = "excluded", "side_not_valid"
        elif len(cycle_values) != 10 or not np.array_equal(cycles.astype(int), np.arange(1, 11)):
            status, reason = "excluded", "requires_exactly_cycles_1_to_10"
        elif not np.all(np.isfinite(values)):
            status, reason = "excluded", "nonfinite_rff_value"
        else:
            normalized = _normalize_rff_trace_for_sti(values, interpolation_points, sample_points)
            if normalized is None:
                status, reason = "excluded", "zero_or_invalid_within_trace_variability"

        boundary_cycle = 10 if str(side).upper() == "OFF" else 1
        boundary_value = np.nan
        if len(cycle_values) == 10 and np.array_equal(cycles.astype(int), np.arange(1, 11)):
            boundary_value = float(values[9] if str(side).upper() == "OFF" else values[0])
        audit_rows.append({
            "Subject": subject, "Method": method, "Filename": filename, "Filepath": filepath,
            "Token": token, "Rep": rep, "Side": str(side).upper(),
            "TraceStatus": status, "TraceReason": reason, "BoundaryCycle": boundary_cycle,
            "BoundaryValue_ST": boundary_value,
            "TraceMean_ST": float(np.mean(values)) if values.size and np.all(np.isfinite(values)) else np.nan,
            "TraceSD_ST": float(np.std(values, ddof=1)) if values.size == 10 and np.all(np.isfinite(values)) else np.nan,
        })
        if normalized is None:
            continue
        group_key = (str(subject), str(method), str(side).upper())
        normalized_by_group.setdefault(group_key, []).append(normalized)
        boundary_by_group.setdefault(group_key, []).append(boundary_value)
        metadata_by_group[group_key] = {
            "AgeGroup": str(group["AgeGroup"].dropna().iloc[0]) if "AgeGroup" in group and group["AgeGroup"].dropna().size else "",
            "Sex": str(group["Sex"].dropna().iloc[0]) if "Sex" in group and group["Sex"].dropna().size else "",
            "MetadataSource": str(group["MetadataSource"].dropna().iloc[0]) if "MetadataSource" in group and group["MetadataSource"].dropna().size else "",
            "NormativeEligible": bool_from_any(group["NormativeEligible"].dropna().iloc[0]) if "NormativeEligible" in group and group["NormativeEligible"].dropna().size else False,
            "NormativeStatus": str(group["NormativeStatus"].dropna().iloc[0]) if "NormativeStatus" in group and group["NormativeStatus"].dropna().size else "",
        }

    # Include every observed Subject × Method × Side, even when STI cannot be calculated.
    observed = (
        df[["Subject", "Method", "Side"]]
        .drop_duplicates()
        .assign(Subject=lambda x: x["Subject"].astype(str), Method=lambda x: x["Method"].astype(str), Side=lambda x: x["Side"].astype(str).str.upper())
    )
    subject_rows: List[Dict[str, Any]] = []
    profile_rows: List[Dict[str, Any]] = []
    implementation = "zscore_each_10_cycle_trace+cubic_spline_1000+50_midpoints+gamma_bias_correction_v25"
    for _, obs in observed.iterrows():
        group_key = (str(obs["Subject"]), str(obs["Method"]), str(obs["Side"]).upper())
        traces = np.asarray(normalized_by_group.get(group_key, []), dtype=float)
        boundaries = np.asarray(boundary_by_group.get(group_key, []), dtype=float)
        n_available = int(len(traces))
        metadata = metadata_by_group.get(group_key, {})
        raw = corrected = factor = np.nan
        status = "calculated" if n_available >= min_traces else "insufficient_valid_traces"
        if n_available >= min_traces:
            point_sd = np.std(traces, axis=0, ddof=1)
            raw = float(np.sum(point_sd))
            factor = _sti_bias_correction_factor(n_available)
            corrected = float(raw * factor)
            point_mean = np.mean(traces, axis=0)
            for point_idx in range(sample_points):
                profile_rows.append({
                    "Subject": group_key[0], "Method": group_key[1], "Side": group_key[2],
                    "NTracesUsed": n_available, "ProfilePoint": point_idx + 1,
                    "NormalizedPosition": float((point_idx + 0.5) / sample_points),
                    "MeanNormalizedRFF": float(point_mean[point_idx]),
                    "SDNormalizedRFF": float(point_sd[point_idx]),
                })
        subject_rows.append({
            "Subject": group_key[0], "Method": group_key[1], "Side": group_key[2],
            "NTracesAvailable": n_available, "NTracesUsed": n_available if status == "calculated" else 0,
            "STIStatus": status, "STI_raw": raw, "STI_bias_corrected": corrected,
            "BiasCorrectionFactor": factor,
            "BoundaryCycle": 10 if group_key[2] == "OFF" else 1,
            "BoundaryMean_ST": float(np.nanmean(boundaries)) if boundaries.size and np.isfinite(boundaries).any() else np.nan,
            "BoundarySD_ST": float(np.nanstd(boundaries, ddof=1)) if np.isfinite(boundaries).sum() >= 2 else np.nan,
            "AgeGroup": metadata.get("AgeGroup", ""), "Sex": metadata.get("Sex", ""),
            "MetadataSource": metadata.get("MetadataSource", ""),
            "NormativeEligible": metadata.get("NormativeEligible", False),
            "NormativeStatus": metadata.get("NormativeStatus", ""),
            "STIInterpolationPoints": interpolation_points, "STISamplePoints": sample_points,
            "STIMinTraces": min_traces, "STIImplementation": implementation,
        })

    subject_df = pd.DataFrame(subject_rows, columns=subject_columns)
    profile_df = pd.DataFrame(profile_rows, columns=profile_columns)
    audit_df = pd.DataFrame(audit_rows, columns=audit_columns)
    summary_rows: List[Dict[str, Any]] = []
    if not subject_df.empty:
        for (method, side), group in subject_df.groupby(["Method", "Side"], dropna=False):
            calc = group.loc[group["STIStatus"].eq("calculated")].copy()
            values = pd.to_numeric(calc["STI_bias_corrected"], errors="coerce").dropna()
            summary_rows.append({
                "Method": method, "Side": side, "SubjectsObserved": int(group["Subject"].nunique()),
                "SubjectsCalculable": int(calc["Subject"].nunique()),
                "SubjectsInsufficientTraces": int(group.loc[~group["STIStatus"].eq("calculated"), "Subject"].nunique()),
                "MeanTracesUsed": float(calc["NTracesUsed"].mean()) if not calc.empty else np.nan,
                "MedianTracesUsed": float(calc["NTracesUsed"].median()) if not calc.empty else np.nan,
                "Mean_STI_bias_corrected": float(values.mean()) if not values.empty else np.nan,
                "SD_STI_bias_corrected": float(values.std(ddof=1)) if len(values) >= 2 else np.nan,
                "Median_STI_bias_corrected": float(values.median()) if not values.empty else np.nan,
                "Q1_STI_bias_corrected": float(values.quantile(0.25)) if not values.empty else np.nan,
                "Q3_STI_bias_corrected": float(values.quantile(0.75)) if not values.empty else np.nan,
            })
    summary_df = pd.DataFrame(summary_rows, columns=summary_columns)
    return subject_df, summary_df, profile_df, audit_df


# =============================================================================
# Debug plots and tabular export
# =============================================================================


def _safe_json_dict(value: Any) -> Dict[str, Any]:
    """Parse a JSON object exported by MATLAB, tolerating empty and double-encoded cells."""
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    try:
        if pd.isna(value):
            return {}
    except Exception:
        pass
    obj: Any = value
    for _ in range(3):
        if isinstance(obj, Mapping):
            return dict(obj)
        if not isinstance(obj, str):
            return {}
        raw = obj.strip()
        if not raw or raw.lower() in {"nan", "none", "null"}:
            return {}
        try:
            obj = json.loads(raw)
        except Exception:
            return {}
    return dict(obj) if isinstance(obj, Mapping) else {}


def _numeric_series_from_json(value: Any) -> np.ndarray:
    """Return finite numeric values from a MATLAB JSON array or Python sequence."""
    if value is None:
        return np.asarray([], dtype=float)
    try:
        if pd.isna(value):
            return np.asarray([], dtype=float)
    except Exception:
        pass
    obj = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw or raw.lower() in {"nan", "none", "null", "[]"}:
            return np.asarray([], dtype=float)
        try:
            obj = json.loads(raw)
        except Exception:
            return np.asarray([], dtype=float)
    try:
        arr = np.asarray(obj, dtype=float).ravel()
    except Exception:
        return np.asarray([], dtype=float)
    return arr[np.isfinite(arr)]


def _pulse_columns_from_external_row(row: Mapping[str, Any], side: str) -> np.ndarray:
    """Read OFF_pulse_01_s... or ON_pulse_01_s... from one MB wide-output row."""
    side = str(side).upper()
    hits: List[Tuple[int, float]] = []
    pattern = re.compile(rf"^{re.escape(side)}_pulse_(\d+)_s$", re.IGNORECASE)
    for key, value in row.items():
        match = pattern.match(str(key))
        if not match:
            continue
        val = safe_float(value, np.nan)
        if np.isfinite(val):
            hits.append((int(match.group(1)), float(val)))
    hits.sort(key=lambda item: item[0])
    return np.asarray([value for _, value in hits], dtype=float)


def _filter_debug_rows_for_wide_row(
    debug_df: pd.DataFrame,
    wide_row: Mapping[str, Any],
    method_label: str,
) -> pd.DataFrame:
    """Match MATLAB debug rows to one wide row using the strongest available keys."""
    if debug_df is None or debug_df.empty:
        return pd.DataFrame()
    mask = pd.Series(True, index=debug_df.index)
    used = False

    # v15: the consolidated debug table contains all methods. Method must be
    # part of the key; otherwise an MB row can match the earlier AVHI/Cepstral
    # row for the same subject/file/token/rep and silently lose bridge QC.
    if "Method" in debug_df.columns:
        mask &= debug_df["Method"].fillna("").astype(str).str.strip().eq(str(method_label).strip())
        used = True

    if method_label == "RFF_AP_ROI_MATLAB":
        for key in ("BridgeFilename", "BridgeSubject"):
            target = str(wide_row.get(key, "")).strip()
            if target and target.lower() != "nan" and key in debug_df.columns:
                mask &= debug_df[key].fillna("").astype(str).str.strip().eq(target)
                used = True
                break
        instance = safe_float(wide_row.get("Instance", np.nan), np.nan)
        if np.isfinite(instance) and "Instance" in debug_df.columns:
            mask &= pd.to_numeric(debug_df["Instance"], errors="coerce").eq(float(instance))
            used = True
    else:
        for key in ("Subject", "Filename", "Token"):
            target = str(wide_row.get(key, "")).strip()
            if target and target.lower() != "nan" and key in debug_df.columns:
                mask &= debug_df[key].fillna("").astype(str).str.strip().eq(target)
                used = True
        rep = safe_float(wide_row.get("Rep", np.nan), np.nan)
        if np.isfinite(rep) and "Rep" in debug_df.columns:
            mask &= pd.to_numeric(debug_df["Rep"], errors="coerce").eq(float(rep))
            used = True

    return debug_df.loc[mask].copy() if used else pd.DataFrame()


def _matlab_bridge_plot_payload(
    wide_row: Mapping[str, Any],
    debug_df: pd.DataFrame,
    method_label: str,
    fs: int,
) -> Dict[str, Any]:
    """Recover candidates, exact final landmarks, and Cycle-QC from a bridge."""
    payload: Dict[str, Any] = {
        "off_final_s": np.asarray([], dtype=float),
        "on_final_s": np.asarray([], dtype=float),
        "off_candidates_s": np.asarray([], dtype=float),
        "on_candidates_s": np.asarray([], dtype=float),
        "off_attempted_s": np.asarray([], dtype=float),
        "on_attempted_s": np.asarray([], dtype=float),
        "off_reject": str(wide_row.get("OffReject", wide_row.get("OffRejectLabel", "")) or ""),
        "on_reject": str(wide_row.get("OnReject", wide_row.get("OnRejectLabel", "")) or ""),
        "off_chosen": str(wide_row.get("OffChosenTrace", "") or ""),
        "on_chosen": str(wide_row.get("OnChosenTrace", "") or ""),
        "off_qc": {},
        "on_qc": {},
        "notes": [],
    }
    matched = _filter_debug_rows_for_wide_row(debug_df, wide_row, method_label)

    if method_label == "RFF_MB_ROI_MATLAB":
        off_final = _pulse_columns_from_external_row(wide_row, "OFF")
        on_final = _pulse_columns_from_external_row(wide_row, "ON")
        if not matched.empty:
            dbg = matched.iloc[0]
            if off_final.size == 0:
                off_final = _numeric_series_from_json(dbg.get("OffFinalPulsesJSON", dbg.get("OffSelectedPulsesJSON")))
            if on_final.size == 0:
                on_final = _numeric_series_from_json(dbg.get("OnFinalPulsesJSON", dbg.get("OnSelectedPulsesJSON")))
            payload["off_candidates_s"] = _numeric_series_from_json(dbg.get("OffCandidatePulsesJSON"))
            payload["on_candidates_s"] = _numeric_series_from_json(dbg.get("OnCandidatePulsesJSON"))
            payload["off_attempted_s"] = _numeric_series_from_json(dbg.get("OffAttemptedPulsesJSON"))
            payload["on_attempted_s"] = _numeric_series_from_json(dbg.get("OnAttemptedPulsesJSON"))
            payload["off_qc"] = _safe_json_dict(dbg.get("OffQCJSON", ""))
            payload["on_qc"] = _safe_json_dict(dbg.get("OnQCJSON", ""))
            if not payload["off_reject"]:
                payload["off_reject"] = str(dbg.get("OffReject", "") or "")
            if not payload["on_reject"]:
                payload["on_reject"] = str(dbg.get("OnReject", "") or "")
            source = str(dbg.get("PulseSource", "") or "").strip()
            if source and source.lower() != "nan":
                payload["notes"].append(f"Pulse source: {source}")
        payload["off_final_s"] = off_final
        payload["on_final_s"] = on_final
        return payload

    # aRFF-AP bridge: final_selected_samples are MATLAB 1-based indices.
    for _, dbg in matched.iterrows():
        side = str(dbg.get("Side", "")).strip().upper()
        summary = _safe_json_dict(dbg.get("DebugSummary", ""))
        selected_times = _numeric_series_from_json(
            summary.get("final_selected_times_s", summary.get("selected_times_s"))
        )
        if selected_times.size == 0:
            selected_samples = _numeric_series_from_json(
                summary.get("final_selected_samples", summary.get("selected_samples"))
            )
            if selected_samples.size:
                selected_times = (selected_samples - 1.0) / float(fs)
        peak_candidates = _numeric_series_from_json(summary.get("candidate_peak_times_s"))
        trough_candidates = _numeric_series_from_json(summary.get("candidate_trough_times_s"))
        if peak_candidates.size == 0:
            peak_samples = _numeric_series_from_json(summary.get("candidate_peak_samples"))
            if peak_samples.size:
                peak_candidates = (peak_samples - 1.0) / float(fs)
        if trough_candidates.size == 0:
            trough_samples = _numeric_series_from_json(summary.get("candidate_trough_samples"))
            if trough_samples.size:
                trough_candidates = (trough_samples - 1.0) / float(fs)
        candidates = np.unique(np.r_[peak_candidates, trough_candidates])
        chosen = str(dbg.get("ChosenTrace", summary.get("chosen", "")) or "")
        reject = str(dbg.get("RejectLabel", summary.get("reject_label", "")) or "")
        qc = {
            "EdgeGap_ms": safe_float(summary.get("edge_gap_ms"), np.nan),
            "PeriodCV": safe_float(summary.get("period_cv"), np.nan),
            "WrongSideCount": safe_float(summary.get("wrong_side_count"), 0),
            "SkippedBoundaryCandidates": safe_float(summary.get("skipped_boundary_candidates"), 0),
            "BoundaryAdjustmentReason": str(summary.get("boundary_adjustment_reason", "") or ""),
            "MaxAdjacentPeriodRatio": safe_float(summary.get("max_adjacent_period_ratio"), np.nan),
            "MaxPeriodToMedianRatio": safe_float(summary.get("max_period_to_median_ratio"), np.nan),
            "ManualReview": bool_from_any(summary.get("manual_review", False)),
            "ReviewReason": str(summary.get("review_reason", "") or ""),
        }
        if side == "OFF":
            payload["off_final_s"] = selected_times
            payload["off_attempted_s"] = selected_times
            payload["off_candidates_s"] = candidates
            payload["off_qc"] = qc
            if chosen:
                payload["off_chosen"] = chosen
            if reject and not _clean_plot_text(payload.get("off_reject", "")):
                payload["off_reject"] = reject
        elif side == "ON":
            payload["on_final_s"] = selected_times
            payload["on_attempted_s"] = selected_times
            payload["on_candidates_s"] = candidates
            payload["on_qc"] = qc
            if chosen:
                payload["on_chosen"] = chosen
            if reject and not _clean_plot_text(payload.get("on_reject", "")):
                payload["on_reject"] = reject

    if matched.empty:
        payload["notes"].append("No matching MATLAB debug row was found.")
    return payload


def _clean_plot_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "not rejected", "not_rejected"} else text


def _waveform_y_at(times: np.ndarray, y: np.ndarray, fs: int) -> np.ndarray:
    times = np.asarray(times, dtype=float)
    if times.size == 0:
        return np.asarray([], dtype=float)
    idx = np.clip(np.round(times * fs).astype(int), 0, max(0, len(y) - 1))
    return y[idx]


def _plot_candidates_and_final(
    ax: Any,
    y: np.ndarray,
    fs: int,
    candidates: np.ndarray,
    final: np.ndarray,
    side: str,
    valid: bool,
    left: float,
    right: float,
) -> None:
    candidates = np.asarray(candidates, dtype=float)
    candidates = candidates[np.isfinite(candidates)]
    final = np.asarray(final, dtype=float)
    final = final[np.isfinite(final)]
    cand_visible = candidates[(candidates >= left) & (candidates <= right)]
    if cand_visible.size:
        ax.scatter(
            cand_visible, _waveform_y_at(cand_visible, y, fs),
            s=11, color="#888888", alpha=0.45, zorder=3,
            label=f"{side} candidates",
        )
    if final.size == 0:
        return
    color = "#2468a2" if side == "OFF" else "#b43c3c"
    linestyle = "-" if valid else "--"
    alpha = 0.85 if valid else 0.65
    final_visible = final[(final >= left) & (final <= right)]
    if final_visible.size:
        ax.scatter(
            final_visible, _waveform_y_at(final_visible, y, fs),
            s=24, color=color, edgecolor="white", linewidth=0.4,
            alpha=alpha, zorder=5, label=f"{side} final landmarks" if valid else f"{side} attempted landmarks",
        )
        for tt in final_visible:
            ax.axvline(tt, color=color, alpha=0.38, lw=0.8, ls=linestyle, zorder=2)

    # Cycle labels follow the algorithmic landmark order, not the visual sort.
    if final.size == 11:
        for i in range(10):
            mid = 0.5 * (final[i] + final[i + 1])
            if not (left <= mid <= right):
                continue
            label = f"{side}{i + 1}"
            is_ref = (side == "OFF" and i == 0) or (side == "ON" and i == 9)
            ax.text(
                mid, 0.76 if i % 2 == 0 else 0.64, label,
                transform=ax.get_xaxis_transform(), rotation=90,
                va="top", ha="center", fontsize=6.5,
                fontweight="bold" if is_ref else "normal",
                color="#a65a00" if is_ref else color,
                alpha=0.95,
            )
            if is_ref:
                ax.axvspan(min(final[i], final[i + 1]), max(final[i], final[i + 1]), color="#f4a261", alpha=0.10, zorder=1)


def _qc_status_text(qc: Mapping[str, Any]) -> str:
    if not qc:
        return ""
    gap = safe_float(qc.get("EdgeGap_ms", qc.get("edge_gap_ms")), np.nan)
    cv = safe_float(qc.get("PeriodCV", qc.get("period_cv")), np.nan)
    wrong = safe_float(qc.get("WrongSideCount", qc.get("wrong_side_count")), np.nan)
    skipped = safe_float(qc.get("SkippedBoundaryCandidates", qc.get("skipped_boundary_candidates")), np.nan)
    parts = []
    if np.isfinite(gap):
        parts.append(f"gap={gap:.1f} ms")
    if np.isfinite(cv):
        parts.append(f"CV={cv:.3f}")
    if np.isfinite(wrong):
        parts.append(f"wrong-side={int(wrong)}")
    if np.isfinite(skipped):
        parts.append(f"skipped-edge={int(skipped)}")
    adjustment = _clean_plot_text(qc.get("BoundaryAdjustmentReason", qc.get("boundary_adjustment_reason", "")))
    if adjustment:
        parts.append(f"adjustment={adjustment}")
    reason = _clean_plot_text(qc.get("ReviewReason", qc.get("review_reason", "")))
    if reason:
        parts.append(f"review={reason}")
    return "; ".join(parts)


def plot_matlab_bridge_debug_row(
    wide_row: Mapping[str, Any],
    debug_df: pd.DataFrame,
    method_label: str,
    out_dir: str | pathlib.Path,
) -> Tuple[bool, str]:
    """Create a Cycle-QC waveform PNG for one MATLAB bridge result row."""
    filepath = str(
        wide_row.get("Filepath", wide_row.get("OriginalFilepath", wide_row.get("Path", "")))
        or ""
    ).strip()
    if not filepath or not pathlib.Path(filepath).exists():
        return False, f"audio file not found: {filepath}"

    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        y, fs = read_audio(filepath)
        y_disp = normalize_audio_for_display(y)
        dur = y.size / fs
        fst = safe_float(wide_row.get("FricStart", np.nan), np.nan)
        fend = safe_float(wide_row.get("FricEnd", np.nan), np.nan)
        if not (np.isfinite(fst) and np.isfinite(fend) and fend > fst):
            return False, "invalid FricStart/FricEnd"

        info = _matlab_bridge_plot_payload(wide_row, debug_df, method_label, fs)
        off_final = np.asarray(info.get("off_final_s", []), dtype=float)
        on_final = np.asarray(info.get("on_final_s", []), dtype=float)
        off_attempted = np.asarray(info.get("off_attempted_s", []), dtype=float)
        on_attempted = np.asarray(info.get("on_attempted_s", []), dtype=float)
        off_plot = off_final if off_final.size else off_attempted
        on_plot = on_final if on_final.size else on_attempted
        off_candidates = np.asarray(info.get("off_candidates_s", []), dtype=float)
        on_candidates = np.asarray(info.get("on_candidates_s", []), dtype=float)

        left = max(0.0, min(fst - 0.45, np.nanmin(off_candidates) - 0.03 if off_candidates.size else fst - 0.45))
        right = min(dur, max(fend + 0.45, np.nanmax(on_candidates) + 0.03 if on_candidates.size else fend + 0.45))
        i0 = max(0, int(round(left * fs)))
        i1 = min(y.size, int(round(right * fs)))
        if i1 <= i0:
            return False, "empty plotting interval"
        max_points = 12000
        step = max(1, int(math.ceil((i1 - i0) / max_points)))
        idx = np.arange(i0, i1, step, dtype=int)

        fig = Figure(figsize=(13, 5.4), dpi=140)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        ax.plot(idx / fs, y_disp[idx], lw=0.65, color="#333333", label="waveform")
        ax.axvspan(fst, fend, color=ACCENT, alpha=0.20, label="marked /f/")
        ax.axvline(fst, color="#147d70", lw=1.0, alpha=0.75)
        ax.axvline(fend, color="#147d70", lw=1.0, alpha=0.75)

        off_valid = bool_from_any(wide_row.get("OffValid", False))
        on_valid = bool_from_any(wide_row.get("OnValid", False))
        _plot_candidates_and_final(ax, y_disp, fs, off_candidates, off_plot, "OFF", off_valid, left, right)
        _plot_candidates_and_final(ax, y_disp, fs, on_candidates, on_plot, "ON", on_valid, left, right)

        subject = str(wide_row.get("Subject", wide_row.get("BridgeSubject", "")) or "")
        token = str(wide_row.get("Token", "") or "")
        rep_val = safe_float(wide_row.get("Rep", wide_row.get("Instance", 1)), 1)
        rep = int(rep_val) if np.isfinite(rep_val) else 1
        off_reject = _clean_plot_text(info.get("off_reject", ""))
        on_reject = _clean_plot_text(info.get("on_reject", ""))
        off_chosen = _clean_plot_text(info.get("off_chosen", ""))
        on_chosen = _clean_plot_text(info.get("on_chosen", ""))

        off_status = "valid" if off_valid else (off_reject or "invalid / no rejection label")
        on_status = "valid" if on_valid else (on_reject or "invalid / no rejection label")
        if off_chosen:
            off_status += f"; chosen={off_chosen}"
        if on_chosen:
            on_status += f"; chosen={on_chosen}"
        off_qc = _qc_status_text(info.get("off_qc", {}))
        on_qc = _qc_status_text(info.get("on_qc", {}))
        note_lines = [
            f"OFF: {off_status} | selected={len(off_plot)}" + (f" | {off_qc}" if off_qc else ""),
            f"ON: {on_status} | selected={len(on_plot)}" + (f" | {on_qc}" if on_qc else ""),
        ]
        note_lines.extend([str(x) for x in info.get("notes", []) if str(x).strip()])
        if len(off_plot) == 0 and len(on_plot) == 0:
            note_lines.append("No selected landmarks were exported for this row.")

        ax.text(
            0.01, 0.98, "\n".join(note_lines), transform=ax.transAxes,
            va="top", ha="left", fontsize=8.2,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.86, "edgecolor": "#777777"},
        )
        ax.set_xlim(left, right)
        ax.set_title(f"{method_label} | {subject} /{token}/ rep {rep} | exact final-cycle audit")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.15)
        handles, labels = ax.get_legend_handles_labels()
        unique = {}
        for handle, label in zip(handles, labels):
            if label and label not in unique:
                unique[label] = handle
        if unique:
            ax.legend(unique.values(), unique.keys(), loc="lower right", fontsize=7.5)
        fig.tight_layout()

        ensure_dir(out_dir)
        safe_subject = re.sub(r"[^A-Za-z0-9._-]+", "_", subject or "subject")
        safe_token = re.sub(r"[^A-Za-z0-9._-]+", "_", token or "token")
        filename = f"{safe_subject}_{safe_token}_rep{rep}_{method_label}.png"
        canvas.print_png(str(pathlib.Path(out_dir) / filename))
        fig.clear()
        return True, str(pathlib.Path(out_dir) / filename)
    except Exception as exc:
        return False, repr(exc)


def plot_external_matlab_bridge_debug(
    files: Mapping[str, str],
    method_label: str,
    out_dir: str | pathlib.Path,
    stop_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """Generate debug plots for every row exported by one MATLAB bridge."""
    wide_path = pathlib.Path(files.get("wide", ""))
    debug_path = pathlib.Path(files.get("debug", ""))
    if not wide_path.exists():
        return {"saved": 0, "failed": 0, "errors": [f"wide output not found: {wide_path}"]}
    wide_df = pd.read_csv(wide_path)
    debug_df = pd.read_csv(debug_path) if debug_path.exists() else pd.DataFrame()
    ensure_dir(out_dir)
    saved = 0
    failures: List[str] = []
    for row_number, (_, row) in enumerate(wide_df.iterrows(), 1):
        if stop_event is not None and stop_event.is_set():
            return {
                "saved": saved, "failed": len(failures), "errors": failures[:20],
                "wide_rows": int(len(wide_df)), "debug_rows": int(len(debug_df)),
                "stopped": True,
            }
        ok, message = plot_matlab_bridge_debug_row(row.to_dict(), debug_df, method_label, out_dir)
        if ok:
            saved += 1
        else:
            failures.append(f"row {row_number}: {message}")
    return {
        "saved": saved,
        "failed": len(failures),
        "errors": failures[:20],
        "wide_rows": int(len(wide_df)),
        "debug_rows": int(len(debug_df)),
    }


def _trace_result_plot_payload(result: TraceResult) -> Dict[str, Any]:
    dbg = result.debug or {}
    payload: Dict[str, Any] = {
        "off_final_s": np.asarray([], dtype=float),
        "on_final_s": np.asarray([], dtype=float),
        "off_candidates_s": np.asarray([], dtype=float),
        "on_candidates_s": np.asarray([], dtype=float),
        "off_qc": {},
        "on_qc": {},
        "off_chosen": "",
        "on_chosen": "",
    }
    if result.method == "AVHI_PRAAT_STRICT":
        for side in ("off", "on"):
            details = dbg.get(f"{side}_details", {}) or {}
            payload[f"{side}_final_s"] = np.asarray(details.get("selected_landmarks_s", []), dtype=float)
            payload[f"{side}_candidates_s"] = np.asarray(
                details.get("candidate_landmarks_s", details.get("all_landmarks_s", [])), dtype=float
            )
            payload[f"{side}_qc"] = details
        return payload

    for side in ("off", "on"):
        side_dbg = dbg.get(f"{side}_debug", {}) or {}
        chosen = str(side_dbg.get("chosen", "") or "")
        payload[f"{side}_chosen"] = chosen
        candidates: List[float] = []
        for trace_name in ("peak", "trough"):
            trace = side_dbg.get(trace_name, {}) or {}
            candidates.extend(_numeric_series_from_json(trace.get("raw_landmarks_s", [])).tolist())
        selected = _numeric_series_from_json(side_dbg.get("final_selected_landmarks_s", []))
        if selected.size != 11 and chosen in {"peak", "trough"}:
            selected = _numeric_series_from_json((side_dbg.get(chosen, {}) or {}).get("selected_landmarks_s", []))
        payload[f"{side}_final_s"] = selected
        payload[f"{side}_candidates_s"] = np.unique(np.asarray(candidates, dtype=float)) if candidates else np.asarray([], dtype=float)
        payload[f"{side}_qc"] = side_dbg.get("cycle_qc", {}) or {}
    return payload


def plot_trace_debug(result: TraceResult, out_dir: str | pathlib.Path) -> None:
    """Save a unified Cycle-QC plot for a Python-native RFF method."""
    if not result.debug:
        return
    ensure_dir(out_dir)
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        y, fs = read_audio(result.filepath)
        y_disp = normalize_audio_for_display(y)
        dur = y.size / fs
        payload = _trace_result_plot_payload(result)
        all_cand = np.r_[payload.get("off_candidates_s", []), payload.get("on_candidates_s", [])]
        all_cand = all_cand[np.isfinite(all_cand)]
        left = max(0.0, result.fric_start - 0.45)
        right = min(dur, result.fric_end + 0.45)
        if all_cand.size:
            left = max(0.0, min(left, float(np.nanmin(all_cand)) - 0.03))
            right = min(dur, max(right, float(np.nanmax(all_cand)) + 0.03))
        i0 = max(0, int(round(left * fs)))
        i1 = min(y.size, int(round(right * fs)))
        if i1 <= i0:
            return
        max_points = 12000
        step = max(1, int(math.ceil((i1 - i0) / max_points)))
        idx = np.arange(i0, i1, step, dtype=int)

        fig = Figure(figsize=(13, 5.4), dpi=140)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_subplot(111)
        ax.plot(idx / fs, y_disp[idx], lw=0.65, color="#333333", label="waveform")
        ax.axvspan(result.fric_start, result.fric_end, color=ACCENT, alpha=0.20, label="marked /f/")
        ax.axvline(result.fric_start, color="#147d70", lw=1.0, alpha=0.75)
        ax.axvline(result.fric_end, color="#147d70", lw=1.0, alpha=0.75)

        _plot_candidates_and_final(
            ax, y_disp, fs,
            np.asarray(payload.get("off_candidates_s", []), dtype=float),
            np.asarray(payload.get("off_final_s", []), dtype=float),
            "OFF", bool(result.off_valid), left, right,
        )
        _plot_candidates_and_final(
            ax, y_disp, fs,
            np.asarray(payload.get("on_candidates_s", []), dtype=float),
            np.asarray(payload.get("on_final_s", []), dtype=float),
            "ON", bool(result.on_valid), left, right,
        )

        off_status = "valid" if result.off_valid else (_clean_plot_text(result.off_reject) or "invalid")
        on_status = "valid" if result.on_valid else (_clean_plot_text(result.on_reject) or "invalid")
        if payload.get("off_chosen"):
            off_status += f"; chosen={payload['off_chosen']}"
        if payload.get("on_chosen"):
            on_status += f"; chosen={payload['on_chosen']}"
        off_qc = _qc_status_text(payload.get("off_qc", {}))
        on_qc = _qc_status_text(payload.get("on_qc", {}))
        note_lines = [
            f"OFF: {off_status} | selected={len(payload.get('off_final_s', []))}" + (f" | {off_qc}" if off_qc else ""),
            f"ON: {on_status} | selected={len(payload.get('on_final_s', []))}" + (f" | {on_qc}" if on_qc else ""),
        ]
        ax.text(
            0.01, 0.98, "\n".join(note_lines), transform=ax.transAxes,
            va="top", ha="left", fontsize=8.2,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.86, "edgecolor": "#777777"},
        )
        ax.set_xlim(left, right)
        ax.set_title(f"{result.method} | {result.subject} /{result.token}/ rep {result.rep} | exact final-cycle audit")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.15)
        handles, labels = ax.get_legend_handles_labels()
        unique = {}
        for handle, label in zip(handles, labels):
            if label and label not in unique:
                unique[label] = handle
        if unique:
            ax.legend(unique.values(), unique.keys(), loc="lower right", fontsize=7.5)
        fig.tight_layout()
        fname = f"{result.subject}_{result.token}_rep{result.rep}_{result.method}.png".replace(os.sep, "_")
        canvas.print_png(str(pathlib.Path(out_dir) / fname))
        fig.clear()
    except Exception:
        # Debug plots must never interrupt the numerical analysis.
        return


def result_to_wide_row(result: TraceResult, metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    metadata = metadata or {}
    dbg0 = result.debug or {}
    row = {
        "ScriptVersion": dbg0.get("implementation_stamp", SCRIPT_VERSION),
        "AlgorithmFamily": dbg0.get("algorithm_family", ""),
        "PitchSource": dbg0.get("pitch_source", ""),
        "Method": result.method,
        "Subject": result.subject,
        "Filename": result.filename,
        "Filepath": result.filepath,
        "Token": result.token,
        "Rep": result.rep,
        "FricStart": result.fric_start,
        "FricEnd": result.fric_end,
        "FricDur": max(0.0, result.fric_end - result.fric_start),
        "OffValid": bool(result.off_valid),
        "OnValid": bool(result.on_valid),
        "OffReject": result.off_reject,
        "OnReject": result.on_reject,
        "NOffLandmarks": int(result.n_off_landmarks),
        "NOnLandmarks": int(result.n_on_landmarks),
        "AgeGroup": str(metadata.get("AgeGroup", "")),
        "Sex": str(metadata.get("Sex", "")),
        "MetadataSource": str(metadata.get("MetadataSource", "gui_default")),
        "NormativeEligible": bool_from_any(metadata.get("NormativeEligible", False)),
        "NormativeStatus": str(metadata.get("NormativeStatus", "not_eligible_missing_participant_metadata")),
    }
    for i in range(10):
        row[f"OFF{i + 1}"] = float(result.off_rff[i]) if result.off_rff is not None and i < len(result.off_rff) else np.nan
    for i in range(10):
        row[f"ON{i + 1}"] = float(result.on_rff[i]) if result.on_rff is not None and i < len(result.on_rff) else np.nan
    row["OFF10"] = row["OFF10"]
    row["ON1"] = row["ON1"]
    return row


def result_to_long_rows(result: TraceResult, metadata: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    metadata = metadata or {}
    rows = []
    for side, arr in (("OFF", result.off_rff), ("ON", result.on_rff)):
        for i in range(1, 11):
            value = np.nan
            if arr is not None and len(arr) >= i:
                value = float(arr[i - 1])
            rows.append({
                "Method": result.method,
                "Subject": result.subject,
                "Filename": result.filename,
                "Filepath": result.filepath,
                "Token": result.token,
                "Rep": result.rep,
                "Side": side,
                "Cycle": i,
                "RFF_ST": value,
                "ValidSide": bool(result.off_valid if side == "OFF" else result.on_valid),
                "Reject": result.off_reject if side == "OFF" else result.on_reject,
                "AgeGroup": str(metadata.get("AgeGroup", "")),
                "Sex": str(metadata.get("Sex", "")),
                "MetadataSource": str(metadata.get("MetadataSource", "gui_default")),
                "NormativeEligible": bool_from_any(metadata.get("NormativeEligible", False)),
                "NormativeStatus": str(metadata.get("NormativeStatus", "not_eligible_missing_participant_metadata")),
            })
    return rows


def result_to_debug_row(result: TraceResult, metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    metadata = metadata or {}
    dbg = result.debug or {}
    # Keep the complete payload in the CSV. v17 truncated this field to fit one
    # Excel cell, which silently broke post-run Cepstral QC and cTFI recovery.
    debug_json = json.dumps(dbg, ensure_ascii=False, default=str)
    return {
        "ScriptVersion": dbg.get("implementation_stamp", SCRIPT_VERSION),
        "AlgorithmFamily": dbg.get("algorithm_family", ""),
        "PitchSource": dbg.get("pitch_source", ""),
        "Method": result.method,
        "Subject": result.subject,
        "Filename": result.filename,
        "Token": result.token,
        "Rep": result.rep,
        "FricStart": result.fric_start,
        "FricEnd": result.fric_end,
        "OffValid": bool(result.off_valid),
        "OnValid": bool(result.on_valid),
        "OffReject": result.off_reject,
        "OnReject": result.on_reject,
        "NOffLandmarks": int(result.n_off_landmarks),
        "NOnLandmarks": int(result.n_on_landmarks),
        "AgeGroup": str(metadata.get("AgeGroup", "")),
        "Sex": str(metadata.get("Sex", "")),
        "MetadataSource": str(metadata.get("MetadataSource", "gui_default")),
        "NormativeEligible": bool_from_any(metadata.get("NormativeEligible", False)),
        "NormativeStatus": str(metadata.get("NormativeStatus", "not_eligible_missing_participant_metadata")),
        "DebugJSON": debug_json,
        "DebugJSONBytes": len(debug_json.encode("utf-8")),
        "DebugJSON_SHA256": hashlib.sha256(debug_json.encode("utf-8")).hexdigest(),
        "DebugJSONTruncated": False,
    }


def build_summary_tables(wide_df: pd.DataFrame, config: RFFConfig) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if wide_df is None or wide_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = wide_df.copy()
    df["OFF10"] = pd.to_numeric(df.get("OFF10"), errors="coerce")
    df["ON1"] = pd.to_numeric(df.get("ON1"), errors="coerce")

    group_cols = ["Subject", "Method"]
    rows = []
    for (subject, method), g in df.groupby(group_cols):
        age_group = str(g["AgeGroup"].dropna().iloc[0]) if "AgeGroup" in g and g["AgeGroup"].dropna().size else config.default_age_group
        sex = str(g["Sex"].dropna().iloc[0]) if "Sex" in g and g["Sex"].dropna().size else config.default_sex
        age_group = age_group if age_group in VOJTECH_OFF10_THRESH_BY_AGE else config.default_age_group
        sex = sex if sex in VOJTECH_ON1_THRESH_BY_SEX else config.default_sex
        metadata_source = str(g["MetadataSource"].dropna().iloc[0]) if "MetadataSource" in g and g["MetadataSource"].dropna().size else "gui_default"
        normative_eligible = bool_from_any(g["NormativeEligible"].dropna().iloc[0]) if "NormativeEligible" in g and g["NormativeEligible"].dropna().size else bool(config.allow_default_metadata_for_normative)
        normative_status = str(g["NormativeStatus"].dropna().iloc[0]) if "NormativeStatus" in g and g["NormativeStatus"].dropna().size else "not_eligible_missing_participant_metadata"
        off_thr = VOJTECH_OFF10_THRESH_BY_AGE[age_group] if normative_eligible else np.nan
        on_thr = VOJTECH_ON1_THRESH_BY_SEX[sex] if normative_eligible else np.nan
        off_vals = pd.to_numeric(g["OFF10"], errors="coerce")
        on_vals = pd.to_numeric(g["ON1"], errors="coerce")
        mean_off = float(off_vals.mean()) if off_vals.notna().any() else np.nan
        mean_on = float(on_vals.mean()) if on_vals.notna().any() else np.nan
        off_margin = mean_off - off_thr if np.isfinite(mean_off) else np.nan
        on_margin = mean_on - on_thr if np.isfinite(mean_on) else np.nan
        rows.append({
            "Subject": subject,
            "Method": method,
            "AgeGroup": age_group,
            "Sex": sex,
            "MetadataSource": metadata_source,
            "NormativeEligible": normative_eligible,
            "NormativeStatus": normative_status,
            "N_OFF10": int(off_vals.notna().sum()),
            "N_ON1": int(on_vals.notna().sum()),
            "Mean_OFF10_ST": mean_off,
            "Mean_ON1_ST": mean_on,
            "OFF10_threshold_ST": off_thr,
            "ON1_threshold_ST": on_thr,
            "OFF10_margin_ST": off_margin,
            "ON1_margin_ST": on_margin,
            "OFF10_at_or_above_threshold": bool(off_margin >= 0) if np.isfinite(off_margin) else pd.NA,
            "ON1_at_or_above_threshold": bool(on_margin >= 0) if np.isfinite(on_margin) else pd.NA,
            "Normative_deficit_ST": float(max(0.0, -off_margin) if np.isfinite(off_margin) else np.nan)
                                  + float(max(0.0, -on_margin) if np.isfinite(on_margin) else np.nan),
            "N_valid_repetitions_any": int((g["OffValid"].astype(bool) | g["OnValid"].astype(bool)).sum()),
            "N_valid_repetitions_both": int((g["OffValid"].astype(bool) & g["OnValid"].astype(bool)).sum()),
        })
    subject_summary = pd.DataFrame(rows)

    rank_rows = []
    for method, g in subject_summary.groupby("Method"):
        eligible = g[g["NormativeEligible"].astype(bool)].copy()
        metadata_coverage = float(100.0 * len(eligible) / len(g)) if len(g) else 0.0
        rank_rows.append({
            "Method": method,
            "Subjects": int(g["Subject"].nunique()),
            "SubjectsNormativeEligible": int(eligible["Subject"].nunique()),
            "MetadataCoveragePct": metadata_coverage,
            "RankingStatus": "eligible" if metadata_coverage == 100.0 else "not_ranked_incomplete_participant_metadata",
            "Mean_N_OFF10": float(g["N_OFF10"].mean()) if not g.empty else np.nan,
            "Mean_N_ON1": float(g["N_ON1"].mean()) if not g.empty else np.nan,
            "Mean_OFF10_ST": float(g["Mean_OFF10_ST"].mean()) if g["Mean_OFF10_ST"].notna().any() else np.nan,
            "Mean_ON1_ST": float(g["Mean_ON1_ST"].mean()) if g["Mean_ON1_ST"].notna().any() else np.nan,
            "Pct_OFF10_normative": float(100.0 * pd.to_numeric(eligible["OFF10_at_or_above_threshold"], errors="coerce").mean()) if not eligible.empty else np.nan,
            "Pct_ON1_normative": float(100.0 * pd.to_numeric(eligible["ON1_at_or_above_threshold"], errors="coerce").mean()) if not eligible.empty else np.nan,
            "Mean_normative_deficit_ST": float(eligible["Normative_deficit_ST"].replace([np.inf, -np.inf], np.nan).mean()) if eligible["Normative_deficit_ST"].notna().any() else np.nan,
            "Mean_valid_repetitions_both": float(g["N_valid_repetitions_both"].mean()) if not g.empty else np.nan,
        })
    ranking = pd.DataFrame(rank_rows)
    if not ranking.empty:
        if bool((ranking["MetadataCoveragePct"] == 100.0).all()):
            ranking = ranking.sort_values(
                by=["Mean_normative_deficit_ST", "Mean_valid_repetitions_both"],
                ascending=[True, False],
            ).reset_index(drop=True)
            ranking.insert(0, "Rank", pd.Series(np.arange(1, len(ranking) + 1), dtype="Int64"))
        else:
            ranking = ranking.sort_values("Method").reset_index(drop=True)
            ranking.insert(0, "Rank", pd.Series([pd.NA] * len(ranking), dtype="Int64"))
    return subject_summary, ranking


def build_normative_metadata_audit(wide_df: pd.DataFrame) -> pd.DataFrame:
    """One row per subject documenting whether normative metadata are genuine."""
    if wide_df is None or wide_df.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for subject, group in wide_df.groupby("Subject", dropna=False):
        source = str(group.get("MetadataSource", pd.Series(["gui_default"])).dropna().iloc[0])
        eligible = bool_from_any(group.get("NormativeEligible", pd.Series([False])).dropna().iloc[0])
        status = str(group.get("NormativeStatus", pd.Series(["not_eligible_missing_participant_metadata"])).dropna().iloc[0])
        rows.append({
            "Subject": subject,
            "AgeGroup": str(group.get("AgeGroup", pd.Series([""])).dropna().iloc[0]),
            "Sex": str(group.get("Sex", pd.Series([""])).dropna().iloc[0]),
            "MetadataSource": source,
            "NormativeEligible": eligible,
            "NormativeStatus": status,
            "Rows": len(group),
        })
    return pd.DataFrame(rows).sort_values("Subject").reset_index(drop=True)


def build_method_validation(wide_df: pd.DataFrame) -> pd.DataFrame:
    """Group-level diagnostics that flag non-comparable methods without changing outputs.

    v21 retains pairwise MAE and sign-conflict diagnostics. A method is no longer
    allowed to pass merely because its correlation is slightly above 0.20 while
    its endpoint values differ by several semitones from every comparator.
    """
    if wide_df is None or wide_df.empty:
        return pd.DataFrame()
    df = wide_df.copy()
    for col in ("OffValid", "OnValid", "OffStrictComparisonEligible", "OnStrictComparisonEligible",
                "OffManualReview", "OnManualReview", "OffBoundaryManualReview", "OnBoundaryManualReview",
                "OffAllCycleManualReview", "OnAllCycleManualReview"):
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].apply(bool_from_any)
    df["OFF10"] = pd.to_numeric(df.get("OFF10"), errors="coerce")
    df["ON1"] = pd.to_numeric(df.get("ON1"), errors="coerce")
    methods = sorted(df.Method.dropna().astype(str).unique())
    pair_corr: Dict[Tuple[str, str], List[float]] = {(m, e): [] for m in methods for e in ("OFF10", "ON1")}
    pair_mae: Dict[Tuple[str, str], List[float]] = {(m, e): [] for m in methods for e in ("OFF10", "ON1")}
    pair_sign_conflict: Dict[Tuple[str, str], List[float]] = {(m, e): [] for m in methods for e in ("OFF10", "ON1")}
    keys = ["Subject", "Token", "Rep"]
    for endpoint, valid_col in (("OFF10", "OffValid"), ("ON1", "OnValid")):
        values = df.pivot_table(index=keys, columns="Method", values=endpoint, aggfunc="first")
        valid = df.pivot_table(index=keys, columns="Method", values=valid_col, aggfunc="first").fillna(False).astype(bool)
        for i, method_a in enumerate(methods):
            for method_b in methods[i + 1:]:
                if method_a not in values or method_b not in values:
                    continue
                mask = valid[method_a] & valid[method_b] & values[method_a].notna() & values[method_b].notna()
                n = int(mask.sum())
                if n < 3:
                    continue
                a = values.loc[mask, method_a].astype(float)
                b = values.loc[mask, method_b].astype(float)
                corr = a.corr(b)
                mae = float(np.mean(np.abs(a - b)))
                sign_conflict = float(np.mean((np.sign(a) != np.sign(b)) & (np.abs(a) > 0.25) & (np.abs(b) > 0.25)))
                if np.isfinite(corr):
                    pair_corr[(method_a, endpoint)].append(float(corr))
                    pair_corr[(method_b, endpoint)].append(float(corr))
                pair_mae[(method_a, endpoint)].append(mae)
                pair_mae[(method_b, endpoint)].append(mae)
                pair_sign_conflict[(method_a, endpoint)].append(sign_conflict)
                pair_sign_conflict[(method_b, endpoint)].append(sign_conflict)

    non_cep_extreme_negative_pct: List[float] = []
    for method, group in df.groupby("Method"):
        if method == "RFF_CEPSTRAL":
            continue
        vals = group.loc[group.OnValid, "ON1"].dropna()
        if len(vals):
            non_cep_extreme_negative_pct.append(float(100.0 * np.mean(vals < -3.0)))
    comparator_extreme_negative_pct = float(np.nanmedian(non_cep_extreme_negative_pct)) if non_cep_extreme_negative_pct else np.nan

    rows: List[Dict[str, Any]] = []
    for method, group in df.groupby("Method"):
        off = group.loc[group.OffValid, "OFF10"].dropna()
        on = group.loc[group.OnValid, "ON1"].dropna()
        off_pct = 100.0 * len(off) / len(group) if len(group) else np.nan
        on_pct = 100.0 * len(on) / len(group) if len(group) else np.nan
        strict_off = int(group.OffStrictComparisonEligible.sum())
        strict_on = int(group.OnStrictComparisonEligible.sum())
        def med(metric: Mapping[Tuple[str, str], List[float]], endpoint: str) -> float:
            vals = metric.get((method, endpoint), [])
            return float(np.nanmedian(vals)) if vals else np.nan
        off_corr, on_corr = med(pair_corr, "OFF10"), med(pair_corr, "ON1")
        off_mae, on_mae = med(pair_mae, "OFF10"), med(pair_mae, "ON1")
        off_sign, on_sign = med(pair_sign_conflict, "OFF10"), med(pair_sign_conflict, "ON1")
        on_negative_pct = float(100.0 * np.mean(on < 0.0)) if len(on) else np.nan
        on_extreme_negative_pct = float(100.0 * np.mean(on < -3.0)) if len(on) else np.nan
        valid_side_total = int(group.OffValid.sum() + group.OnValid.sum())
        accepted_manual_review = int(
            (group.OffValid & group.OffManualReview).sum()
            + (group.OnValid & group.OnManualReview).sum()
        )
        accepted_manual_review_pct = (
            100.0 * accepted_manual_review / valid_side_total if valid_side_total else np.nan
        )
        accepted_all_cycle_review = int(
            (group.OffValid & group.OffAllCycleManualReview).sum()
            + (group.OnValid & group.OnAllCycleManualReview).sum()
        )
        accepted_all_cycle_review_pct = (
            100.0 * accepted_all_cycle_review / valid_side_total if valid_side_total else np.nan
        )

        flags: List[str] = []
        if min(off_pct, on_pct) < 60.0:
            flags.append("low_native_valid_yield")
        if strict_off == 0 or strict_on == 0:
            flags.append("no_strict_boundary_eligible_results")
        if method == "RFF_CEPSTRAL":
            if np.isfinite(accepted_manual_review_pct) and accepted_manual_review_pct > 25.0:
                flags.append("accepted_cepstral_review_over_25pct")
            if np.isfinite(accepted_all_cycle_review_pct) and accepted_all_cycle_review_pct > 20.0:
                flags.append("accepted_all_cycle_trajectory_warning_over_20pct")
            if np.isfinite(on_corr) and np.isfinite(on_mae) and on_corr < 0.35 and on_mae > 2.0:
                flags.append("low_on1_agreement_and_high_error_vs_other_methods")
            if np.isfinite(on_sign) and on_sign > 0.25 and np.isfinite(on_mae) and on_mae > 2.0:
                flags.append("high_on1_sign_conflict_vs_other_methods")
            if (
                np.isfinite(on_extreme_negative_pct)
                and np.isfinite(comparator_extreme_negative_pct)
                and on_extreme_negative_pct > 15.0
                and on_extreme_negative_pct - comparator_extreme_negative_pct > 12.0
            ):
                flags.append("excess_extreme_negative_on1_tail")
        blocking = {
            "low_native_valid_yield",
            "no_strict_boundary_eligible_results",
            "accepted_cepstral_review_over_25pct",
            "accepted_all_cycle_trajectory_warning_over_20pct",
            "low_on1_agreement_and_high_error_vs_other_methods",
            "high_on1_sign_conflict_vs_other_methods",
            "excess_extreme_negative_on1_tail",
        }
        recommended = not any(flag in blocking for flag in flags)
        rows.append({
            "Method": method,
            "Rows": len(group),
            "NativeValidOFF": len(off), "NativeValidOFFPct": off_pct,
            "NativeValidON": len(on), "NativeValidONPct": on_pct,
            "StrictComparisonEligibleOFF": strict_off,
            "StrictComparisonEligibleON": strict_on,
            "MeanOFF10_ST": float(off.mean()) if len(off) else np.nan,
            "MeanON1_ST": float(on.mean()) if len(on) else np.nan,
            "ON1NegativePct": on_negative_pct,
            "ON1BelowMinus3Pct": on_extreme_negative_pct,
            "AcceptedManualReviewSides": accepted_manual_review,
            "AcceptedManualReviewPct": accepted_manual_review_pct,
            "AcceptedAllCycleManualReviewSides": accepted_all_cycle_review,
            "AcceptedAllCycleManualReviewPct": accepted_all_cycle_review_pct,
            "MedianPairwiseCorrelationOFF10": off_corr,
            "MedianPairwiseCorrelationON1": on_corr,
            "MedianPairwiseMAEOFF10_ST": off_mae,
            "MedianPairwiseMAEON1_ST": on_mae,
            "MedianPairwiseSignConflictOFF10": off_sign,
            "MedianPairwiseSignConflictON1": on_sign,
            "MatlabBridgeOutputPreservedByPython": method in {"RFF_MB_ROI_MATLAB", "RFF_AP_ROI_MATLAB"},
            "ValidationFlags": "; ".join(flags),
            "RecommendedForPrimaryStrictComparison": recommended,
            "ValidationStatus": "PASS" if not flags else "CAUTION",
        })
    return pd.DataFrame(rows).sort_values("Method").reset_index(drop=True)

def _analysis_row_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str, float]:
    rep = safe_float(row.get("Rep", row.get("Instance", np.nan)), np.nan)
    rep_key = round(float(rep), 6) if np.isfinite(rep) else -999999.0
    return (
        str(row.get("Method", "")).strip(),
        str(row.get("Subject", row.get("BridgeSubject", ""))).strip(),
        str(row.get("Filename", row.get("OriginalFilename", row.get("BridgeFilename", "")))).strip(),
        str(row.get("Token", "")).strip().lower(),
        rep_key,
    )


def _find_python_debug_row(debug_df: pd.DataFrame, wide_row: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    if debug_df is None or debug_df.empty:
        return None
    method = str(wide_row.get("Method", "")).strip()
    mask = debug_df.get("Method", pd.Series("", index=debug_df.index)).fillna("").astype(str).str.strip().eq(method)
    for key in ("Subject", "Filename", "Token"):
        target = str(wide_row.get(key, "")).strip()
        if target and key in debug_df.columns:
            vals = debug_df[key].fillna("").astype(str).str.strip()
            if key == "Token":
                mask &= vals.str.lower().eq(target.lower())
            else:
                mask &= vals.eq(target)
    rep = safe_float(wide_row.get("Rep", np.nan), np.nan)
    if np.isfinite(rep) and "Rep" in debug_df.columns:
        mask &= pd.to_numeric(debug_df["Rep"], errors="coerce").sub(float(rep)).abs().lt(1e-8)
    hits = debug_df.loc[mask]
    if hits.empty:
        return None
    return hits.iloc[0].to_dict()


def _saved_python_plot_payload(wide_row: Mapping[str, Any], debug_df: pd.DataFrame) -> Dict[str, Any]:
    row = _find_python_debug_row(debug_df, wide_row)
    payload: Dict[str, Any] = {
        "off_final_s": np.asarray([], dtype=float), "on_final_s": np.asarray([], dtype=float),
        "off_candidates_s": np.asarray([], dtype=float), "on_candidates_s": np.asarray([], dtype=float),
        "off_qc": {}, "on_qc": {}, "off_chosen": "", "on_chosen": "",
        "off_source": str(wide_row.get("PitchSource", "")), "on_source": str(wide_row.get("PitchSource", "")),
    }
    if not row:
        return payload
    dbg = _safe_json_dict(row.get("DebugJSON", ""))
    method = str(wide_row.get("Method", ""))
    if method == "AVHI_PRAAT_STRICT":
        for side in ("off", "on"):
            details = dbg.get(f"{side}_details", {}) or {}
            payload[f"{side}_final_s"] = _numeric_series_from_json(details.get("selected_landmarks_s", []))
            payload[f"{side}_candidates_s"] = _numeric_series_from_json(
                details.get("candidate_landmarks_s", details.get("all_landmarks_s", []))
            )
            payload[f"{side}_qc"] = details
            payload[f"{side}_source"] = str(details.get("pulse_source", "Praat/Parselmouth"))
        return payload

    for side in ("off", "on"):
        sd = dbg.get(f"{side}_debug", {}) or {}
        chosen = str(sd.get("chosen", "") or "")
        payload[f"{side}_chosen"] = chosen
        candidates: List[float] = []
        for trace_name in ("peak", "trough"):
            tr = sd.get(trace_name, {}) or {}
            candidates.extend(_numeric_series_from_json(tr.get("raw_landmarks_s", [])).tolist())
        payload[f"{side}_candidates_s"] = np.unique(np.asarray(candidates, dtype=float)) if candidates else np.asarray([], dtype=float)
        payload[f"{side}_final_s"] = _numeric_series_from_json(sd.get("final_selected_landmarks_s", []))
        if payload[f"{side}_final_s"].size != 11 and chosen in {"peak", "trough"}:
            payload[f"{side}_final_s"] = _numeric_series_from_json(
                (sd.get(chosen, {}) or {}).get("selected_landmarks_s", [])
            )
        payload[f"{side}_qc"] = sd.get("cycle_qc", {}) or {}
        payload[f"{side}_source"] = "cepstral-assisted peak/trough" if method == "RFF_CEPSTRAL" else "AP-like peak/trough"
    return payload


def _cycle_qc_record(
    wide_row: Mapping[str, Any],
    side: str,
    final: np.ndarray,
    candidates: np.ndarray,
    qc_hint: Mapping[str, Any],
    chosen: str,
    source: str,
    config: RFFConfig,
) -> Dict[str, Any]:
    side = side.upper()
    final_raw = np.asarray(final, dtype=float).ravel()
    final_raw = final_raw[np.isfinite(final_raw)]
    candidates = np.asarray(candidates, dtype=float).ravel()
    candidates = np.unique(candidates[np.isfinite(candidates)])
    periods = np.abs(np.diff(final_raw))
    med = float(np.nanmedian(periods)) if periods.size else np.nan
    cv = float(np.nanstd(periods) / med) if periods.size and np.isfinite(med) and med > 0 else np.nan
    max_median_ratio, max_adjacent_ratio = _period_ratio_metrics(periods)
    edge = safe_float(wide_row.get("FricStart" if side == "OFF" else "FricEnd"), np.nan)
    if final_raw.size and np.isfinite(edge):
        if side == "OFF":
            wrong = int(np.sum(final_raw >= edge))
            gap = float(edge - np.max(final_raw))
        else:
            wrong = int(np.sum(final_raw <= edge))
            gap = float(np.min(final_raw) - edge)
    else:
        wrong = 0
        gap = np.nan
    skipped_hint = safe_float(
        qc_hint.get("SkippedBoundaryCandidates", qc_hint.get("skipped_boundary_candidates")),
        np.nan,
    ) if qc_hint else np.nan
    skipped = int(round(skipped_hint)) if np.isfinite(skipped_hint) else _boundary_candidate_skip_count(candidates, final_raw, edge, side)
    adjustment = _clean_plot_text(
        qc_hint.get("BoundaryAdjustmentReason", qc_hint.get("boundary_adjustment_reason", ""))
    ) if qc_hint else ""
    if skipped > 0 and not adjustment:
        adjustment = "selected_window_not_edge_adjacent"
    edge_cycles = float(gap / med) if np.isfinite(gap) and np.isfinite(med) and med > 0 else np.nan
    valid = bool_from_any(wide_row.get("OffValid" if side == "OFF" else "OnValid", False))
    reject = _clean_plot_text(wide_row.get("OffReject" if side == "OFF" else "OnReject", ""))
    contiguous = bool(final_raw.size == 11 and periods.size == 10 and np.all(periods > 0) and (not np.isfinite(max_adjacent_ratio) or max_adjacent_ratio <= 2.5))

    reasons: List[str] = []
    severity = ""
    if valid and final_raw.size != 11:
        reasons.append("valid_without_11_final_landmarks")
        severity = "Critical"
    if wrong > 0:
        reasons.append("wrong_side_of_roi")
        severity = "Critical"
    if valid and skipped > 0:
        reasons.append(f"skipped_boundary_candidates={skipped}")
        severity = severity or "Review"
    if valid and (not np.isfinite(gap) or gap > float(config.hard_max_edge_gap_s)):
        reasons.append("selected_window_too_far")
        severity = "Critical"
    if valid and np.isfinite(gap) and gap > float(config.qc_edge_warn_s) and gap <= float(config.hard_max_edge_gap_s):
        reasons.append(f"edge_gap_over_{int(round(config.qc_edge_warn_s*1000))}_ms")
        severity = severity or "Review"
    if valid and np.isfinite(cv) and cv > float(config.qc_period_cv_warn):
        reasons.append(f"period_cv_over_{config.qc_period_cv_warn:.2f}")
        severity = severity or "Review"
    if valid and np.isfinite(max_adjacent_ratio) and max_adjacent_ratio > float(config.qc_adjacent_ratio_warn):
        reasons.append(f"adjacent_period_ratio_over_{config.qc_adjacent_ratio_warn:.2f}")
        severity = severity or "Review"
    if valid and not contiguous:
        reasons.append("noncontiguous_final_window")
        severity = severity or "Critical"

    # Preserve method-computed review reasons. v21 Cepstral exposes all-cycle
    # trajectory evidence separately from the generic geometric QC.
    boundary_review = bool_from_any(qc_hint.get("BoundaryManualReview", False)) if qc_hint else False
    boundary_reason = _clean_plot_text(qc_hint.get("BoundaryReviewReason", "")) if qc_hint else ""
    if boundary_review and boundary_reason:
        for part in [x.strip() for x in boundary_reason.split(";") if x.strip()]:
            if part not in reasons:
                reasons.append(part)
                severity = severity or "Review"

    all_cycle_review = bool_from_any(qc_hint.get("AllCycleManualReview", False)) if qc_hint else False
    all_cycle_reason = _clean_plot_text(qc_hint.get("AllCycleReviewReason", "")) if qc_hint else ""
    if all_cycle_review and all_cycle_reason:
        for part in [x.strip() for x in all_cycle_reason.split(";") if x.strip()]:
            if part not in reasons:
                reasons.append(part)
                severity = severity or "Review"

    # Preserve a bridge-computed review reason when present.
    hint_reason = _clean_plot_text(qc_hint.get("ReviewReason", qc_hint.get("review_reason", ""))) if qc_hint else ""
    if hint_reason:
        for part in [x.strip() for x in hint_reason.split(";") if x.strip()]:
            if part not in reasons:
                reasons.append(part)
                severity = severity or "Review"

    method = str(wide_row.get("Method", ""))
    native_matlab_preserved = method in {"RFF_MB_ROI_MATLAB", "RFF_AP_ROI_MATLAB"}
    if native_matlab_preserved:
        boundary_policy = "native_matlab_selection_preserved_qc_only"
    elif method == "RFF_CEPSTRAL":
        boundary_policy = "python_v23_boundary_adjacent_tiered_qc_final_selection_sync"
    else:
        boundary_policy = "native_python_selection_with_explicit_qc"
    comparison_exclusions: List[str] = []
    if not valid:
        comparison_exclusions.append("native_method_invalid")
    if final_raw.size != 11:
        comparison_exclusions.append("not_11_landmarks")
    if wrong > 0:
        comparison_exclusions.append("wrong_side_of_roi")
    if not contiguous:
        comparison_exclusions.append("noncontiguous_window")
    if skipped > int(config.max_skipped_boundary_candidates):
        comparison_exclusions.append(f"skipped_boundary_candidates={skipped}")
    if not np.isfinite(gap) or gap > float(config.hard_max_edge_gap_s):
        comparison_exclusions.append("edge_gap_hard_limit")
    if method == "RFF_CEPSTRAL" and bool(config.cep_strict_exclude_review) and valid and reasons:
        comparison_exclusions.append("cepstral_qc_review_pending")
    strict_comparison_eligible = not comparison_exclusions

    return {
        "Method": method,
        "Subject": str(wide_row.get("Subject", wide_row.get("BridgeSubject", ""))),
        "Filename": str(wide_row.get("Filename", wide_row.get("OriginalFilename", ""))),
        "Filepath": str(wide_row.get("Filepath", wide_row.get("OriginalFilepath", ""))),
        "Token": str(wide_row.get("Token", "")),
        "Rep": safe_float(wide_row.get("Rep", np.nan), np.nan),
        "Side": side,
        "ValidSide": valid,
        "Reject": reject,
        "ChosenTrace": chosen,
        "LandmarkSource": source,
        "NCandidates": int(candidates.size),
        "NFinalLandmarks": int(final_raw.size if valid else 0),
        "NSelectedOrAttemptedLandmarks": int(final_raw.size),
        "EdgeTime_s": edge,
        "EdgeGap_s": gap,
        "EdgeGap_ms": 1000.0 * gap if np.isfinite(gap) else np.nan,
        "EdgeGapCycles": edge_cycles,
        "WrongSideCount": wrong,
        "SkippedBoundaryCandidates": skipped,
        "BoundaryAdjustmentReason": adjustment,
        "MedianPeriod_s": med,
        "PeriodCV": cv,
        "MaxPeriodToMedianRatio": max_median_ratio,
        "MaxAdjacentPeriodRatio": max_adjacent_ratio,
        "Contiguous": contiguous,
        "ManualReview": bool(valid and reasons),
        "ReviewSeverity": severity,
        "ReviewReason": "; ".join(reasons),
        "MatlabBridgeOutputPreservedByPython": native_matlab_preserved,
        "BoundaryPolicy": boundary_policy,
        "StrictComparisonEligible": strict_comparison_eligible,
        "ComparisonExclusionReason": "; ".join(comparison_exclusions),
        "BoundaryManualReview": boundary_review,
        "BoundaryReviewReason": boundary_reason,
        "BoundaryEvidenceCount": safe_float(qc_hint.get("BoundaryEvidenceCount"), np.nan) if qc_hint else np.nan,
        "BoundaryStrongEvidenceCount": safe_float(qc_hint.get("BoundaryStrongEvidenceCount"), np.nan) if qc_hint else np.nan,
        "CepstralQCStatus": _clean_plot_text(qc_hint.get("CepstralQCStatus", "")) if qc_hint else "",
        "AllCycleManualReview": all_cycle_review,
        "AllCycleReviewReason": all_cycle_reason,
        "AllCyclePenalty": safe_float(qc_hint.get("AllCyclePenalty"), np.nan) if qc_hint else np.nan,
        "FinalSelectionConsistent": bool_from_any(qc_hint.get("FinalSelectionConsistent", True)) if qc_hint else True,
        "FinalSelectionConsistencyErrorST": safe_float(qc_hint.get("FinalSelectionConsistencyErrorST"), np.nan) if qc_hint else np.nan,
        "FinalChosenTrace": _clean_plot_text(qc_hint.get("FinalChosenTrace", chosen)) if qc_hint else chosen,
        "FinalChosenWindowIndex": safe_float(qc_hint.get("FinalChosenWindowIndex"), np.nan) if qc_hint else np.nan,
        "CycleTrackDeviationSTJSON": json.dumps(qc_hint.get("CycleTrackDeviationST", [])) if qc_hint else "[]",
        "CycleIndependentDeviationSTJSON": json.dumps(qc_hint.get("CycleIndependentDeviationST", [])) if qc_hint else "[]",
        "CycleNeighborPeriodRatioJSON": json.dumps(qc_hint.get("CycleNeighborPeriodRatio", [])) if qc_hint else "[]",
        "CycleSkippedSamePhaseCrossingsJSON": json.dumps(qc_hint.get("CycleSkippedSamePhaseCrossings", [])) if qc_hint else "[]",
        "CandidateLandmarksJSON": json.dumps(candidates.tolist()),
        "SelectedLandmarksJSON": json.dumps(final_raw.tolist()),
    }


def build_cycle_qc_artifacts(
    wide_df: pd.DataFrame,
    debug_df: pd.DataFrame,
    config: RFFConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build consolidated exact-landmark, QC, review, and exclusion tables."""
    qc_rows: List[Dict[str, Any]] = []
    landmark_rows: List[Dict[str, Any]] = []
    if wide_df is None or wide_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    for _, wr in wide_df.iterrows():
        row = wr.to_dict()
        method = str(row.get("Method", ""))
        filepath = str(row.get("Filepath", row.get("OriginalFilepath", "")) or "")
        fs = 1
        try:
            if filepath and pathlib.Path(filepath).exists():
                fs = int(sf.info(filepath).samplerate)
        except Exception:
            fs = 1
        if method in {"RFF_MB_ROI_MATLAB", "RFF_AP_ROI_MATLAB"}:
            payload = _matlab_bridge_plot_payload(row, debug_df, method, fs)
            for side in ("off", "on"):
                payload.setdefault(f"{side}_source", "MATLAB bridge")
        else:
            payload = _saved_python_plot_payload(row, debug_df)

        for side in ("off", "on"):
            rec = _cycle_qc_record(
                row,
                side,
                np.asarray(payload.get(f"{side}_final_s", []), dtype=float),
                np.asarray(payload.get(f"{side}_candidates_s", []), dtype=float),
                payload.get(f"{side}_qc", {}) or {},
                str(payload.get(f"{side}_chosen", "") or ""),
                str(payload.get(f"{side}_source", row.get("PitchSource", "")) or ""),
                config,
            )
            qc_rows.append(rec)
            selected = _numeric_series_from_json(rec["SelectedLandmarksJSON"])
            if rec["ValidSide"] and selected.size == 11:
                for i, tt in enumerate(selected, 1):
                    landmark_rows.append({
                        "Method": rec["Method"], "Subject": rec["Subject"], "Filename": rec["Filename"],
                        "Filepath": rec["Filepath"], "Token": rec["Token"], "Rep": rec["Rep"],
                        "Side": rec["Side"], "LandmarkIndex": i,
                        "LandmarkLabel": f"{rec['Side']}_L{i:02d}", "Time_s": float(tt),
                        "SampleIndex": (
                            int(round(float(tt) * fs)) + 1
                            if fs > 1 and rec["Method"] == "RFF_AP_ROI_MATLAB"
                            else (int(round(float(tt) * fs)) if fs > 1 else np.nan)
                        ),
                        "ChosenTrace": rec["ChosenTrace"], "LandmarkSource": rec["LandmarkSource"],
                        "ValidSide": True, "Reject": "",
                    })

    qc_df = pd.DataFrame(qc_rows)
    landmarks_df = pd.DataFrame(landmark_rows)
    review_df = qc_df.loc[qc_df.get("ManualReview", False).astype(bool)].copy() if not qc_df.empty else pd.DataFrame()
    exclusion_df = qc_df.loc[~qc_df.get("ValidSide", False).astype(bool)].copy() if not qc_df.empty else pd.DataFrame()
    return landmarks_df, qc_df, review_df, exclusion_df


def augment_wide_with_cycle_qc(wide_df: pd.DataFrame, qc_df: pd.DataFrame) -> pd.DataFrame:
    if wide_df is None or wide_df.empty or qc_df is None or qc_df.empty:
        return wide_df
    out = wide_df.copy()
    lookup: Dict[Tuple[str, str, str, str, float, str], Mapping[str, Any]] = {}
    for _, r in qc_df.iterrows():
        key = _analysis_row_key(r.to_dict()) + (str(r.get("Side", "")).upper(),)
        lookup[key] = r.to_dict()
    for idx, r in out.iterrows():
        base = _analysis_row_key(r.to_dict())
        for side, prefix in (("OFF", "Off"), ("ON", "On")):
            q = lookup.get(base + (side,))
            if not q:
                continue
            for source_col, dest_suffix in (
                ("NCandidates", "Candidates"), ("NFinalLandmarks", "FinalLandmarks"),
                ("EdgeGap_ms", "EdgeGap_ms"), ("EdgeGapCycles", "EdgeGapCycles"),
                ("WrongSideCount", "WrongSideCount"),
                ("SkippedBoundaryCandidates", "SkippedBoundaryCandidates"),
                ("BoundaryAdjustmentReason", "BoundaryAdjustmentReason"),
                ("PeriodCV", "PeriodCV"),
                ("MaxPeriodToMedianRatio", "MaxPeriodToMedianRatio"),
                ("MaxAdjacentPeriodRatio", "MaxAdjacentPeriodRatio"),
                ("Contiguous", "Contiguous"), ("ManualReview", "ManualReview"),
                ("ReviewReason", "ReviewReason"),
                ("MatlabBridgeOutputPreservedByPython", "MatlabBridgeOutputPreservedByPython"),
                ("BoundaryPolicy", "BoundaryPolicy"),
                ("StrictComparisonEligible", "StrictComparisonEligible"),
                ("ComparisonExclusionReason", "ComparisonExclusionReason"),
                ("BoundaryManualReview", "BoundaryManualReview"),
                ("BoundaryReviewReason", "BoundaryReviewReason"),
                ("BoundaryEvidenceCount", "BoundaryEvidenceCount"),
                ("BoundaryStrongEvidenceCount", "BoundaryStrongEvidenceCount"),
                ("CepstralQCStatus", "CepstralQCStatus"),
                ("AllCycleManualReview", "AllCycleManualReview"),
                ("AllCycleReviewReason", "AllCycleReviewReason"),
                ("AllCyclePenalty", "AllCyclePenalty"),
                ("FinalSelectionConsistent", "FinalSelectionConsistent"),
                ("FinalSelectionConsistencyErrorST", "FinalSelectionConsistencyErrorST"),
                ("FinalChosenTrace", "FinalChosenTrace"),
                ("FinalChosenWindowIndex", "FinalChosenWindowIndex"),
            ):
                out.at[idx, prefix + dest_suffix] = q.get(source_col, np.nan)
    return out


def build_cepstral_transition_index_long(debug_df: pd.DataFrame) -> pd.DataFrame:
    """Materialize the exploratory cTFI stored in Cepstral DebugJSON.

    This table is intentionally separate from all RFF summary/ranking tables.
    It must not be interpreted as classical cycle-based RFF.
    """
    columns = [
        "Method", "IsClassicalRFF", "Subject", "Filename", "Filepath", "Token", "Rep",
        "FricStart", "FricEnd", "Side", "Index", "SampleTime_s", "F0_Hz",
        "Confidence", "Value_ST", "ValidSide", "Reason", "ReferenceRule",
    ]
    if debug_df.empty or "Method" not in debug_df.columns:
        return pd.DataFrame(columns=columns)
    rows: List[Dict[str, Any]] = []
    for _, source in debug_df.loc[debug_df["Method"].astype(str).eq("RFF_CEPSTRAL")].iterrows():
        dbg = _safe_json_dict(source.get("DebugJSON", ""))
        proxy = dbg.get("cepstral_transition_proxy", {}) or {}
        for side in ("OFF", "ON"):
            item = proxy.get(side, {}) or {}
            values = np.asarray(item.get("values_st", []), dtype=float)
            times = np.asarray(item.get("sample_times_s", []), dtype=float)
            f0 = np.asarray(item.get("sampled_f0_hz", []), dtype=float)
            conf = np.asarray(item.get("sampled_confidence", []), dtype=float)
            for i in range(10):
                rows.append({
                    "Method": "CEPSTRAL_TRANSITION_F0_INDEX_EXPLORATORY",
                    "IsClassicalRFF": False,
                    "Subject": source.get("Subject", ""), "Filename": source.get("Filename", ""),
                    "Filepath": source.get("Filepath", ""), "Token": source.get("Token", ""),
                    "Rep": source.get("Rep", np.nan), "FricStart": source.get("FricStart", np.nan),
                    "FricEnd": source.get("FricEnd", np.nan), "Side": side, "Index": i + 1,
                    "SampleTime_s": float(times[i]) if i < times.size else np.nan,
                    "F0_Hz": float(f0[i]) if i < f0.size else np.nan,
                    "Confidence": float(conf[i]) if i < conf.size else np.nan,
                    "Value_ST": float(values[i]) if i < values.size else np.nan,
                    "ValidSide": bool(item.get("valid", False)), "Reason": str(item.get("reason", "")),
                    "ReferenceRule": str(item.get("reference_rule", "")),
                })
    return pd.DataFrame(rows, columns=columns)


RESULT_OUTPUT_FILENAMES = [
    "rff_all_cycles_long.csv",
    "rff_all_traces_wide.csv",
    "rff_debug.csv",
    "rff_final_landmarks_long.csv",
    "rff_cycle_qc.csv",
    "rff_manual_review_queue.csv",
    "rff_exclusion_log.csv",
    "rff_comparison_eligibility.csv",
    "rff_method_validation.csv",
    "rff_normative_metadata_audit.csv",
    "rff_cepstral_transition_index_long.csv",
    "rff_sti_subject_method_side.csv",
    "rff_sti_method_summary.csv",
    "rff_sti_profiles_long.csv",
    "rff_sti_trace_audit.csv",
    "rff_subject_method_summary.csv",
    "rff_method_normative_ranking.csv",
    "rff_method_comparison_outputs.xlsx",
    "rff_config_used.json",
    "rff_script_version.txt",
    "rff_run_manifest.json",
    "rff_roi_marks_MATLAB_MANIFEST.csv",
]

RESULT_OUTPUT_DIRNAMES = [
    "debug_plots",
    "matlab_mb_roi",
    "matlab_arff_ap_roi",
]

RESULT_OUTPUT_GLOBS = [
    "rff_mb_roi_*",
    "rff_arff_ap_roi_*",
]


def find_existing_result_artifacts(out_dir: str | pathlib.Path) -> List[pathlib.Path]:
    """Return generated result artifacts without touching ROI/autosave files.

    The ROI tables remain available when a run is restarted. Previous result
    archives and aborted-run archives are never considered active artifacts.
    """
    out = pathlib.Path(out_dir)
    if not out.exists():
        return []
    found: Dict[str, pathlib.Path] = {}
    for name in RESULT_OUTPUT_FILENAMES + RESULT_OUTPUT_DIRNAMES:
        item = out / name
        if item.exists():
            found[str(item.resolve()).lower()] = item
    for pattern in RESULT_OUTPUT_GLOBS:
        for item in out.glob(pattern):
            if not item.exists():
                continue
            if item.name in {"rff_roi_marks.csv", "rff_roi_marks.xlsx",
                             "rff_roi_marks_AUTOSAVE.csv", "rff_roi_marks_AUTOSAVE.xlsx"}:
                continue
            found[str(item.resolve()).lower()] = item
    return sorted(found.values(), key=lambda x: str(x).lower())


def archive_existing_result_outputs(
    out_dir: str | pathlib.Path,
    category: str = "previous_result_runs",
) -> Optional[str]:
    """Move active result artifacts into a timestamped archive.

    v20 already archived a limited set of top-level result files automatically.
    v21 expands this to the MATLAB subfolders, debug plots, bridge exports and
    manifest, while deliberately preserving ROI marks and ROI autosaves.
    """
    out = pathlib.Path(out_dir)
    existing = find_existing_result_artifacts(out)
    if not existing:
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    archive = out / str(category) / stamp
    ensure_dir(archive)
    for src in existing:
        try:
            target = archive / src.name
            if target.exists():
                target = archive / f"{src.stem}_{int(time.time()*1000)}{src.suffix}"
            shutil.move(str(src), str(target))
        except Exception:
            pass
    return str(archive)


def delete_existing_result_outputs(out_dir: str | pathlib.Path) -> int:
    """Permanently remove active result artifacts, preserving ROI marks."""
    removed = 0
    for item in find_existing_result_artifacts(out_dir):
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=False)
            else:
                item.unlink()
            removed += 1
        except Exception:
            pass
    return removed


class RunStopped(RuntimeError):
    """Raised internally when the user requests a clean stop."""


def _raise_if_stopped(stop_event: Optional[threading.Event]) -> None:
    if stop_event is not None and stop_event.is_set():
        raise RunStopped("Processing stopped by user")

def save_outputs(
    out_dir: str | pathlib.Path,
    roi_df: pd.DataFrame,
    wide_rows: List[Dict[str, Any]],
    long_rows: List[Dict[str, Any]],
    debug_rows: List[Dict[str, Any]],
    config: RFFConfig,
) -> Dict[str, str]:
    out = pathlib.Path(out_dir)
    ensure_dir(out)
    paths: Dict[str, str] = {}

    roi_df.to_csv(out / "rff_roi_marks.csv", index=False, encoding="utf-8-sig")
    paths["roi_csv"] = str(out / "rff_roi_marks.csv")
    try:
        roi_df.to_excel(out / "rff_roi_marks.xlsx", index=False)
        paths["roi_xlsx"] = str(out / "rff_roi_marks.xlsx")
    except Exception:
        pass

    wide_df = pd.DataFrame(wide_rows)
    long_df = pd.DataFrame(long_rows)
    debug_df = pd.DataFrame(debug_rows)
    cepstral_transition_df = build_cepstral_transition_index_long(debug_df)

    landmarks_df, cycle_qc_df, review_df, exclusion_df = build_cycle_qc_artifacts(wide_df, debug_df, config)
    wide_df = augment_wide_with_cycle_qc(wide_df, cycle_qc_df)
    comparison_df = cycle_qc_df.copy()

    wide_df.to_csv(out / "rff_all_traces_wide.csv", index=False, encoding="utf-8-sig")
    long_df.to_csv(out / "rff_all_cycles_long.csv", index=False, encoding="utf-8-sig")
    debug_df.to_csv(out / "rff_debug.csv", index=False, encoding="utf-8-sig")
    landmarks_df.to_csv(out / "rff_final_landmarks_long.csv", index=False, encoding="utf-8-sig")
    cycle_qc_df.to_csv(out / "rff_cycle_qc.csv", index=False, encoding="utf-8-sig")
    review_df.to_csv(out / "rff_manual_review_queue.csv", index=False, encoding="utf-8-sig")
    exclusion_df.to_csv(out / "rff_exclusion_log.csv", index=False, encoding="utf-8-sig")
    comparison_df.to_csv(out / "rff_comparison_eligibility.csv", index=False, encoding="utf-8-sig")
    cepstral_transition_df.to_csv(out / "rff_cepstral_transition_index_long.csv", index=False, encoding="utf-8-sig")
    paths["wide_csv"] = str(out / "rff_all_traces_wide.csv")
    paths["long_csv"] = str(out / "rff_all_cycles_long.csv")
    paths["debug_csv"] = str(out / "rff_debug.csv")
    paths["landmarks_csv"] = str(out / "rff_final_landmarks_long.csv")
    paths["cycle_qc_csv"] = str(out / "rff_cycle_qc.csv")
    paths["manual_review_csv"] = str(out / "rff_manual_review_queue.csv")
    paths["exclusion_log_csv"] = str(out / "rff_exclusion_log.csv")
    paths["comparison_eligibility_csv"] = str(out / "rff_comparison_eligibility.csv")
    paths["cepstral_transition_index_csv"] = str(out / "rff_cepstral_transition_index_long.csv")

    subject_summary, ranking = build_summary_tables(wide_df, config)
    method_validation = build_method_validation(wide_df)
    metadata_audit = build_normative_metadata_audit(wide_df)
    if not ranking.empty and not method_validation.empty:
        ranking = ranking.merge(
            method_validation[["Method", "ValidationStatus", "ValidationFlags", "RecommendedForPrimaryStrictComparison"]],
            on="Method", how="left",
        )
    subject_summary.to_csv(out / "rff_subject_method_summary.csv", index=False, encoding="utf-8-sig")
    ranking.to_csv(out / "rff_method_normative_ranking.csv", index=False, encoding="utf-8-sig")
    method_validation.to_csv(out / "rff_method_validation.csv", index=False, encoding="utf-8-sig")
    metadata_audit.to_csv(out / "rff_normative_metadata_audit.csv", index=False, encoding="utf-8-sig")
    paths["summary_csv"] = str(out / "rff_subject_method_summary.csv")
    paths["ranking_csv"] = str(out / "rff_method_normative_ranking.csv")
    paths["method_validation_csv"] = str(out / "rff_method_validation.csv")
    paths["normative_metadata_audit_csv"] = str(out / "rff_normative_metadata_audit.csv")

    sti_subject_df = pd.DataFrame()
    sti_method_summary_df = pd.DataFrame()
    sti_profiles_df = pd.DataFrame()
    sti_trace_audit_df = pd.DataFrame()
    if bool(getattr(config, "calculate_sti", False)):
        sti_subject_df, sti_method_summary_df, sti_profiles_df, sti_trace_audit_df = build_rff_sti_tables(long_df, config)
        sti_subject_df.to_csv(out / "rff_sti_subject_method_side.csv", index=False, encoding="utf-8-sig")
        sti_method_summary_df.to_csv(out / "rff_sti_method_summary.csv", index=False, encoding="utf-8-sig")
        sti_profiles_df.to_csv(out / "rff_sti_profiles_long.csv", index=False, encoding="utf-8-sig")
        sti_trace_audit_df.to_csv(out / "rff_sti_trace_audit.csv", index=False, encoding="utf-8-sig")
        paths["sti_subject_csv"] = str(out / "rff_sti_subject_method_side.csv")
        paths["sti_method_summary_csv"] = str(out / "rff_sti_method_summary.csv")
        paths["sti_profiles_csv"] = str(out / "rff_sti_profiles_long.csv")
        paths["sti_trace_audit_csv"] = str(out / "rff_sti_trace_audit.csv")

    # Excel cells cannot store more than 32,767 characters. The CSV above is
    # authoritative and complete; the workbook therefore carries a clearly
    # labelled preview instead of corrupting the payload used for QC/cTFI.
    debug_excel_df = debug_df.copy()
    if "DebugJSON" in debug_excel_df.columns:
        debug_text = debug_excel_df["DebugJSON"].fillna("").astype(str)
        preview_limit = 32000
        debug_excel_df["DebugJSONExcelPreviewOnly"] = debug_text.str.len() > preview_limit
        debug_excel_df.loc[debug_excel_df["DebugJSONExcelPreviewOnly"], "DebugJSON"] = (
            debug_text.loc[debug_excel_df["DebugJSONExcelPreviewOnly"]].str.slice(0, preview_limit - 55)
            + "... [TRUNCATED IN XLSX; SEE COMPLETE rff_debug.csv]"
        )
    try:
        with pd.ExcelWriter(out / "rff_method_comparison_outputs.xlsx", engine="openpyxl") as xl:
            roi_df.to_excel(xl, sheet_name="ROI_marks", index=False)
            wide_df.to_excel(xl, sheet_name="wide_traces", index=False)
            long_df.to_excel(xl, sheet_name="long_cycles", index=False)
            debug_excel_df.to_excel(xl, sheet_name="debug", index=False)
            landmarks_df.to_excel(xl, sheet_name="final_landmarks", index=False)
            cycle_qc_df.to_excel(xl, sheet_name="cycle_qc", index=False)
            review_df.to_excel(xl, sheet_name="manual_review", index=False)
            exclusion_df.to_excel(xl, sheet_name="exclusion_log", index=False)
            comparison_df.to_excel(xl, sheet_name="comparison_eligibility", index=False)
            subject_summary.to_excel(xl, sheet_name="subject_summary", index=False)
            ranking.to_excel(xl, sheet_name="method_ranking", index=False)
            method_validation.to_excel(xl, sheet_name="method_validation", index=False)
            metadata_audit.to_excel(xl, sheet_name="metadata_audit", index=False)
            cepstral_transition_df.to_excel(xl, sheet_name="cepstral_cTFI_exploratory", index=False)
            if bool(getattr(config, "calculate_sti", False)):
                sti_subject_df.to_excel(xl, sheet_name="STI_subject", index=False)
                sti_method_summary_df.to_excel(xl, sheet_name="STI_method_summary", index=False)
                sti_profiles_df.to_excel(xl, sheet_name="STI_profiles", index=False)
                sti_trace_audit_df.to_excel(xl, sheet_name="STI_trace_audit", index=False)
        paths["xlsx"] = str(out / "rff_method_comparison_outputs.xlsx")
    except Exception:
        pass

    (out / "rff_config_used.json").write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    paths["config_json"] = str(out / "rff_config_used.json")
    (out / "rff_script_version.txt").write_text(SCRIPT_VERSION + "\n" + SCRIPT_LABEL + "\n", encoding="utf-8")
    paths["script_version_txt"] = str(out / "rff_script_version.txt")
    run_manifest = {
        "script_version": SCRIPT_VERSION,
        "script_label": SCRIPT_LABEL,
        "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "normative_ranking_status": (
            "eligible" if not ranking.empty and bool((ranking.get("MetadataCoveragePct", pd.Series(dtype=float)) == 100.0).all())
            else "not_ranked_incomplete_participant_metadata"
        ),
        "methods_recommended_for_primary_strict_comparison": (
            method_validation.loc[method_validation.RecommendedForPrimaryStrictComparison.astype(bool), "Method"].tolist()
            if not method_validation.empty else []
        ),
        "methods_with_validation_caution": (
            method_validation.loc[method_validation.ValidationStatus.ne("PASS"), "Method"].tolist()
            if not method_validation.empty else []
        ),
        "debug_payload_policy": {
            "rff_debug_csv": "complete JSON payload; authoritative for Cepstral QC and cTFI",
            "xlsx_debug_sheet": "preview only when a payload exceeds the Excel cell limit",
        },
        "matlab_native_result_authority": {
            "MB": "original Berardi thresholds/equations and sliding Praat voting; ROI edges replace FricLoc",
            "AP": "unmodified original RFFoutput.m; ROI edges replace automatic fricative location",
            "QC": "observational only; does not alter native validity"
        },
        "optional_sti": {
            "requested": bool(getattr(config, "calculate_sti", False)),
            "status": "calculated" if bool(getattr(config, "calculate_sti", False)) else "not_requested",
            "minimum_valid_traces": int(getattr(config, "sti_min_traces", 2)),
            "interpolation_points": int(getattr(config, "sti_interpolation_points", 1000)),
            "sample_points": int(getattr(config, "sti_sample_points", 50)),
            "scope": "post-processing only; no RFF values or native method validity changed",
        },
    }
    (out / "rff_run_manifest.json").write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    paths["run_manifest_json"] = str(out / "rff_run_manifest.json")
    return paths


# =============================================================================
# ROI marker GUI
# =============================================================================

class ROIMarkerWindow(tk.Toplevel):
    def __init__(self, master: tk.Tk, wav_path: str, token: str, expected_rois: int = 3):
        super().__init__(master)
        self.title(f"Mark /f/ ROIs - {pathlib.Path(wav_path).name} - /{token}/")
        self.configure(bg=BG_COLOR)
        self.geometry("1120x760")
        self.transient(master)
        self.grab_set()
        self.wav_path = wav_path
        self.token = token
        self.expected_rois = expected_rois
        self.rois: List[Tuple[float, float]] = []
        self._drag_start: Optional[float] = None
        self._rect = None
        self._roi_patches = []
        self._playing = False
        self._play_start_wall = 0.0
        self._play_start_pos = 0.0
        self._playhead_wave = None
        self._playhead_spec = None
        self._sd_stream = None
        self._sd_buf = None
        self._sd_ptr = 0

        try:
            self.y, self.fs = read_audio(wav_path)
            self.y_disp = normalize_audio_for_display(self.y)
            self.duration = self.y.size / self.fs
        except Exception as exc:
            messagebox.showerror("Audio", f"Could not read file:\n{wav_path}\n\n{exc}")
            self.destroy()
            return

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(30, self._tick)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text=f"/{self.token}/  |  {self.wav_path}", font=("Calibri", 11, "bold")).pack(side="left")
        ttk.Button(top, text="Play all", command=self.play_all).pack(side="right", padx=4)
        ttk.Button(top, text="Play selected ROI", command=self.play_selected).pack(side="right", padx=4)
        ttk.Button(top, text="Zoom selected ROI", command=self.zoom_selected).pack(side="right", padx=4)
        ttk.Button(top, text="Reset zoom", command=self.reset_zoom).pack(side="right", padx=4)

        self.fig, (self.ax_wave, self.ax_spec) = plt.subplots(2, 1, figsize=(10.8, 5.8), dpi=100, sharex=True)
        self.fig.patch.set_facecolor(BG_COLOR)
        y_plot, fs_plot = display_downsample(self.y_disp, self.fs)
        t = np.arange(y_plot.size) / fs_plot
        self.ax_wave.plot(t, y_plot, lw=0.6, color="#222222")
        self.ax_wave.set_ylabel("Waveform")
        self.ax_wave.grid(True, alpha=0.15)
        self.ax_spec.specgram(y_plot, NFFT=1024, Fs=fs_plot, noverlap=896, cmap="magma")
        self.ax_spec.set_ylim(0, min(8000, fs_plot / 2.0))
        self.ax_spec.set_xlim(0, self.duration)
        self.ax_spec.set_xlabel("Time (s)")
        self.ax_spec.set_ylabel("Frequency (Hz)")
        self.ax_wave.set_title("Drag across the fricative /f/ region. Mark exactly 3 ROIs when possible.")
        self._playhead_wave = self.ax_wave.axvline(0, color=ACCENT, lw=1.3)
        self._playhead_spec = self.ax_spec.axvline(0, color=ACCENT, lw=1.3)
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=8)
        self.roi_list = tk.Listbox(bottom, height=5, width=56, font=FONT)
        self.roi_list.pack(side="left", padx=(0, 8))
        btns = ttk.Frame(bottom)
        btns.pack(side="left")
        ttk.Button(btns, text="Delete selected", command=self.delete_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="Clear all", command=self.clear_rois).pack(fill="x", pady=2)
        ttk.Button(btns, text="Confirm", command=self.confirm).pack(fill="x", pady=2)
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(fill="x", pady=2)

    def _on_press(self, event):
        if event.inaxes not in (self.ax_wave, self.ax_spec) or event.xdata is None:
            return
        self._drag_start = float(np.clip(event.xdata, 0.0, self.duration))
        if self._rect is not None:
            try:
                self._rect.remove()
            except Exception:
                pass
            self._rect = None

    def _on_motion(self, event):
        if self._drag_start is None or event.inaxes not in (self.ax_wave, self.ax_spec) or event.xdata is None:
            return
        x0 = self._drag_start
        x1 = float(np.clip(event.xdata, 0.0, self.duration))
        left, right = (x0, x1) if x0 <= x1 else (x1, x0)
        if self._rect is not None:
            try:
                self._rect.remove()
            except Exception:
                pass
        self._rect = self.ax_spec.axvspan(left, right, color=ACCENT, alpha=0.30)
        self.canvas.draw_idle()

    def _on_release(self, event):
        if self._drag_start is None or event.inaxes not in (self.ax_wave, self.ax_spec) or event.xdata is None:
            self._drag_start = None
            return
        x0 = self._drag_start
        x1 = float(np.clip(event.xdata, 0.0, self.duration))
        self._drag_start = None
        left, right = (x0, x1) if x0 <= x1 else (x1, x0)
        if right - left < 0.015:
            if self._rect is not None:
                self._rect.remove()
                self._rect = None
                self.canvas.draw_idle()
            return
        self.rois.append((float(left), float(right)))
        self.rois.sort(key=lambda ab: ab[0])
        self._redraw_rois()

    def _redraw_rois(self):
        if self._rect is not None:
            try:
                self._rect.remove()
            except Exception:
                pass
            self._rect = None
        for p in self._roi_patches:
            try:
                p.remove()
            except Exception:
                pass
        self._roi_patches = []
        for a, b in self.rois:
            self._roi_patches.append(self.ax_wave.axvspan(a, b, color=ACCENT, alpha=0.18))
            self._roi_patches.append(self.ax_spec.axvspan(a, b, color=ACCENT, alpha=0.24))
        self.roi_list.delete(0, "end")
        for i, (a, b) in enumerate(self.rois, 1):
            self.roi_list.insert("end", f"ROI {i}: {a:.4f} - {b:.4f} s | dur {b-a:.4f} s")
        self.canvas.draw_idle()

    def delete_selected(self):
        sel = list(self.roi_list.curselection())
        if not sel:
            return
        self.rois.pop(sel[0])
        self._redraw_rois()

    def clear_rois(self):
        self.rois = []
        self._redraw_rois()

    def zoom_selected(self):
        sel = list(self.roi_list.curselection())
        if not sel:
            return
        a, b = self.rois[sel[0]]
        pad = max(0.15, 2 * (b - a))
        self.ax_spec.set_xlim(max(0, a - pad), min(self.duration, b + pad))
        self.canvas.draw_idle()

    def reset_zoom(self):
        self.ax_spec.set_xlim(0, self.duration)
        self.canvas.draw_idle()

    def _stop_audio(self):
        try:
            if self._sd_stream is not None:
                self._sd_stream.stop(); self._sd_stream.close()
        except Exception:
            pass
        self._sd_stream = None
        self._playing = False

    def _play_pcm(self, samples: np.ndarray, start_pos: float):
        if sounddevice is None:
            messagebox.showwarning("Audio", "sounddevice is not installed. Install with: pip install sounddevice")
            return
        y = np.asarray(samples, dtype=np.float32).reshape(-1)
        if y.size == 0:
            return
        peak = float(np.max(np.abs(y)))
        if peak > 1:
            y = y / peak
        self._stop_audio()
        self._sd_buf = y
        self._sd_ptr = 0
        self._play_start_wall = time.time()
        self._play_start_pos = float(start_pos)
        self._playing = True

        def callback(outdata, frames, time_info, status):
            end = self._sd_ptr + frames
            chunk = self._sd_buf[self._sd_ptr:end]
            if chunk.size < frames:
                chunk = np.concatenate([chunk, np.zeros(frames - chunk.size, dtype=np.float32)])
                try:
                    self.after(0, self._stop_audio)
                except Exception:
                    pass
            outdata[:] = chunk.reshape(-1, 1)
            self._sd_ptr = end

        self._sd_stream = sounddevice.OutputStream(samplerate=self.fs, channels=1, dtype="float32", callback=callback)
        self._sd_stream.start()

    def play_all(self):
        self._play_pcm(self.y_disp * 0.95, 0.0)

    def play_selected(self):
        sel = list(self.roi_list.curselection())
        if not sel:
            messagebox.showinfo("Play", "Select one ROI first.")
            return
        a, b = self.rois[sel[0]]
        i0 = max(0, int(round(a * self.fs)))
        i1 = min(self.y.size, int(round(b * self.fs)))
        self._play_pcm(self.y_disp[i0:i1] * 0.95, a)

    def _tick(self):
        if self._playing:
            pos = self._play_start_pos + (time.time() - self._play_start_wall)
            try:
                self._playhead_wave.set_xdata([pos, pos])
                self._playhead_spec.set_xdata([pos, pos])
                self.canvas.draw_idle()
            except Exception:
                pass
        self.after(30, self._tick)

    def confirm(self):
        if len(self.rois) != self.expected_rois:
            ok = messagebox.askyesno(
                "ROI count",
                f"You marked {len(self.rois)} ROIs. Expected {self.expected_rois}. Proceed anyway?",
            )
            if not ok:
                return
        self._stop_audio()
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.rois = []
        self._stop_audio()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# =============================================================================
# Main application GUI
# =============================================================================

class RFFComparisonGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RFF Method Comparison - v25 Optional STI")
        self.configure(bg=BG_COLOR)
        self.geometry("1230x960")
        self.option_add("*Font", "Calibri 11")
        self.config_obj = RFFConfig()
        self.files: List[Dict[str, Any]] = []
        self.roi_rows: List[Dict[str, Any]] = []
        self.metadata_by_subject: Dict[str, Dict[str, str]] = {}
        self.current_scan_root: str = ""
        self._ui_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self._run_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_process_lock = threading.Lock()
        self._active_process: Optional[subprocess.Popen] = None
        self._build_style()
        self._build_ui()
        self.after(80, self._drain_ui_queue)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=DARK_TEXT)
        style.configure("TButton", padding=6)
        style.configure("Header.TLabel", font=("Calibri", 15, "bold"), foreground=DARK_TEXT, background=BG_COLOR)

    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(header, text="RFF Method Comparison", style="Header.TLabel").pack(side="left")

        form = ttk.Frame(self)
        form.pack(fill="x", padx=12, pady=4)
        self.root_var = tk.StringVar(value=DEFAULT_ROOT)
        self.out_var = tk.StringVar(value=DEFAULT_OUTPUT)
        self.praat_var = tk.StringVar(value=DEFAULT_PRAAT_EXE)
        self.age_var = tk.StringVar(value=self.config_obj.default_age_group)
        self.sex_var = tk.StringVar(value=self.config_obj.default_sex)
        self.bandpass_var = tk.BooleanVar(value=False)
        self.debug_plots_var = tk.BooleanVar(value=False)
        self.calculate_sti_var = tk.BooleanVar(value=False)
        self.matlab_var = tk.StringVar(value=DEFAULT_MATLAB_EXE)
        self.mb_bridge_dir_var = tk.StringVar(value=package_default_dir("rff_auto_mb_roi_bridge"))
        self.ap_bridge_dir_var = tk.StringVar(value=package_default_dir("aRFF_AP_ROI_bridge"))
        self.run_matlab_mb_var = tk.BooleanVar(value=True)
        self.run_matlab_ap_var = tk.BooleanVar(value=True)
        self.allow_default_normative_var = tk.BooleanVar(value=False)

        ttk.Label(form, text="Corpus root:").grid(row=0, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.root_var, width=92).grid(row=0, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Choose", command=self.choose_root).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(form, text="Scan", command=self.scan).grid(row=0, column=3, padx=4, pady=4)
        self.clear_scan_button = ttk.Button(form, text="Clear scanned data", command=self.clear_scanned_data)
        self.clear_scan_button.grid(row=0, column=4, padx=4, pady=4)

        ttk.Label(form, text="Output folder:").grid(row=1, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.out_var, width=92).grid(row=1, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Choose", command=self.choose_out).grid(row=1, column=2, padx=4, pady=4)

        ttk.Label(form, text="Praat exe (for AVHI/MB):").grid(row=2, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.praat_var, width=92).grid(row=2, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Browse", command=self.choose_praat).grid(row=2, column=2, padx=4, pady=4)

        ttk.Label(form, text="MATLAB exe:").grid(row=3, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.matlab_var, width=92).grid(row=3, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Browse", command=self.choose_matlab).grid(row=3, column=2, padx=4, pady=4)

        ttk.Label(form, text="MB bridge folder:").grid(row=4, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.mb_bridge_dir_var, width=92).grid(row=4, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Choose", command=self.choose_mb_bridge).grid(row=4, column=2, padx=4, pady=4)

        ttk.Label(form, text="aRFF-AP bridge folder:").grid(row=5, column=0, sticky="e", padx=4, pady=4)
        ttk.Entry(form, textvariable=self.ap_bridge_dir_var, width=92).grid(row=5, column=1, sticky="we", padx=4, pady=4)
        ttk.Button(form, text="Choose", command=self.choose_ap_bridge).grid(row=5, column=2, padx=4, pady=4)

        opts = ttk.Frame(form)
        opts.grid(row=6, column=1, sticky="w", padx=4, pady=4)
        ttk.Label(opts, text="Default age group:").pack(side="left", padx=(0, 4))
        ttk.Combobox(opts, textvariable=self.age_var, values=list(VOJTECH_OFF10_THRESH_BY_AGE), width=8, state="readonly").pack(side="left", padx=(0, 14))
        ttk.Label(opts, text="Default sex:").pack(side="left", padx=(0, 4))
        ttk.Combobox(opts, textvariable=self.sex_var, values=list(VOJTECH_ON1_THRESH_BY_SEX), width=8, state="readonly").pack(side="left", padx=(0, 14))
        ttk.Checkbutton(opts, text="Praat band-pass 60-3000 Hz", variable=self.bandpass_var).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(opts, text="Save debug plots (slower)", variable=self.debug_plots_var).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(opts, text="Run MATLAB MB", variable=self.run_matlab_mb_var).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(opts, text="Run MATLAB aRFF-AP", variable=self.run_matlab_ap_var).pack(side="left")
        ttk.Button(form, text="Load metadata CSV/XLSX", command=self.load_metadata).grid(row=6, column=2, padx=4, pady=4)

        normative_opts = ttk.Frame(form)
        normative_opts.grid(row=7, column=1, sticky="w", padx=4, pady=(0, 4))
        ttk.Checkbutton(
            normative_opts,
            text="Explicitly allow GUI default age/sex in normative ranking",
            variable=self.allow_default_normative_var,
        ).pack(side="left")
        ttk.Label(
            normative_opts,
            text="(leave unchecked for participant-safe normative outputs)",
        ).pack(side="left", padx=(8, 0))

        sti_opts = ttk.Frame(form)
        sti_opts.grid(row=8, column=1, sticky="w", padx=4, pady=(0, 4))
        ttk.Checkbutton(
            sti_opts,
            text="Calculate RFF spatiotemporal index (STI; exploratory)",
            variable=self.calculate_sti_var,
        ).pack(side="left")
        ttk.Label(
            sti_opts,
            text="(requires at least 2 valid repeated traces per participant, method, and side)",
        ).pack(side="left", padx=(8, 0))

        form.columnconfigure(1, weight=1)

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=12, pady=6)
        columns = ("Subject", "Token", "Filename", "Folder")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", height=17, selectmode="extended")
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=130 if c != "Folder" else 540, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=12, pady=4)
        ttk.Button(actions, text="Import fricative_locations from folders", command=self.import_fricative_locations).pack(side="left", padx=4)
        ttk.Button(actions, text="Mark/Edit ROIs for selected files", command=self.mark_selected).pack(side="left", padx=4)
        self.run_button = ttk.Button(actions, text="Run RFF on marked ROIs", command=self.run_marked)
        self.run_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(actions, text="Stop current run", command=self.stop_run, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(actions, text="Load existing ROI CSV/XLSX", command=self.load_roi_table).pack(side="left", padx=4)
        ttk.Button(actions, text="Save ROI table only", command=self.save_roi_only).pack(side="left", padx=4)

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=False, padx=12, pady=(4, 10))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", font=("Consolas", 10))
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status).pack(fill="x", padx=12, pady=(0, 6))

    def _drain_ui_queue(self):
        """Process log/status updates created by worker threads on the Tk main thread."""
        try:
            while True:
                kind, msg = self._ui_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(msg))
                elif kind == "status":
                    self.status.set(str(msg))
                elif kind == "run_state":
                    self._set_running_state(bool(msg))
        except queue.Empty:
            pass
        try:
            self.after(80, self._drain_ui_queue)
        except Exception:
            pass

    def _append_log(self, msg: str):
        self.log_text.insert("end", str(msg).rstrip() + "\n")
        self.log_text.see("end")
        self.update_idletasks()

    def log(self, msg: str):
        # Safe from worker threads: queue the operation and let Tk handle it.
        if threading.current_thread() is threading.main_thread():
            self._append_log(msg)
        else:
            self._ui_queue.put(("log", str(msg)))

    def set_status(self, msg: str):
        if threading.current_thread() is threading.main_thread():
            self.status.set(str(msg))
        else:
            self._ui_queue.put(("status", str(msg)))


    def _set_running_state(self, running: bool):
        try:
            self.run_button.configure(state="disabled" if running else "normal")
            self.stop_button.configure(state="normal" if running else "disabled")
            self.clear_scan_button.configure(state="disabled" if running else "normal")
        except Exception:
            pass

    def _register_active_process(self, proc: Optional[subprocess.Popen]):
        with self._active_process_lock:
            self._active_process = proc

    def stop_run(self):
        if self._run_thread is None or not self._run_thread.is_alive():
            self._set_running_state(False)
            return
        ok = messagebox.askyesno(
            "Stop processing",
            "Stop the current run?\n\nPartial generated outputs will be moved to an aborted_runs archive. "
            "ROI marks and ROI autosaves will be preserved so the run can be restarted from zero.",
        )
        if not ok:
            return
        self._stop_event.set()
        self.set_status("Stopping current run...")
        self.log("Stop requested by user. Finishing the current atomic step and cancelling MATLAB if active.")
        with self._active_process_lock:
            proc = self._active_process
        if proc is not None and proc.poll() is None:
            _terminate_process_tree(proc)

    def _prepare_output_for_new_run(self, out: str) -> bool:
        existing = find_existing_result_artifacts(out)
        if not existing:
            return True
        answer = messagebox.askyesnocancel(
            "Existing results in output folder",
            f"Found {len(existing)} existing result artifacts in the selected output folder.\n\n"
            "YES: archive them in previous_result_runs/<timestamp> and start a clean run.\n"
            "NO: permanently overwrite/delete them and start a clean run.\n"
            "CANCEL: do not start processing.\n\n"
            "ROI marks and ROI autosaves are preserved in either case.",
        )
        if answer is None:
            return False
        if answer:
            archive = archive_existing_result_outputs(out, "previous_result_runs")
            self.log(f"Existing results archived before new run: {archive}")
        else:
            removed = delete_existing_result_outputs(out)
            self.log(f"Existing results permanently removed before new run: {removed} artifacts.")
        return True

    def choose_root(self):
        p = filedialog.askdirectory(title="Choose corpus root")
        if p:
            self.root_var.set(p)
            if not self.out_var.get().strip():
                self.out_var.set(DEFAULT_OUTPUT)

    def choose_out(self):
        p = filedialog.askdirectory(title="Choose output folder")
        if p:
            self.out_var.set(p)

    def choose_praat(self):
        p = filedialog.askopenfilename(title="Choose Praat executable", filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            self.praat_var.set(p)

    def choose_matlab(self):
        p = filedialog.askopenfilename(title="Choose MATLAB executable", filetypes=[("MATLAB executable", "matlab.exe;matlab"), ("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            self.matlab_var.set(p)

    def choose_mb_bridge(self):
        p = filedialog.askdirectory(title="Choose RFF_auto_MB_ROI_bridge folder")
        if p:
            self.mb_bridge_dir_var.set(p)

    def choose_ap_bridge(self):
        p = filedialog.askdirectory(title="Choose aRFF_AP_ROI_bridge folder")
        if p:
            self.ap_bridge_dir_var.set(p)

    @staticmethod
    def _normalized_scan_root(path: str | pathlib.Path) -> str:
        """Return a stable root key for detecting corpus changes across scans."""
        try:
            return os.path.normcase(str(pathlib.Path(path).expanduser().resolve()))
        except Exception:
            return os.path.normcase(os.path.abspath(str(path)))

    def clear_scanned_data(self, ask_confirmation: bool = True) -> bool:
        """Clear only in-memory scan/ROI state so another corpus can be loaded safely.

        Saved ROI tables, autosaves, debug plots, and result files on disk are not
        deleted. Participant metadata is cleared because it belongs to the corpus
        currently held in memory and must not leak into a subsequent group.
        """
        if self._run_thread is not None and self._run_thread.is_alive():
            messagebox.showwarning(
                "Processing active",
                "Stop the current run before clearing scanned data.",
            )
            return False

        n_files = len(self.files)
        n_rois = len(self.roi_rows)
        n_meta = len(self.metadata_by_subject)
        if ask_confirmation and (n_files or n_rois or n_meta):
            ok = messagebox.askyesno(
                "Clear scanned data",
                f"Clear the current in-memory corpus data?\n\n"
                f"Scanned audio files: {n_files}\n"
                f"ROI rows in memory: {n_rois}\n"
                f"Participant metadata rows: {n_meta}\n\n"
                "Saved files in the output folder will not be deleted. "
                "The corpus-root and output-folder fields will remain unchanged.",
            )
            if not ok:
                return False

        self.files = []
        self.roi_rows = []
        self.metadata_by_subject = {}
        self.current_scan_root = ""
        try:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.tree.selection_remove(self.tree.selection())
        except Exception:
            pass
        self.log(
            f"Cleared in-memory scan data: {n_files} audio files, "
            f"{n_rois} ROI rows, {n_meta} metadata rows. Saved output files were preserved."
        )
        self.set_status("Scanned data cleared. Choose or scan a corpus folder.")
        return True

    def scan(self):
        root = self.root_var.get().strip()
        if not root or not pathlib.Path(root).exists():
            messagebox.showerror("Folder", "Choose a valid corpus root folder.")
            return

        new_root = self._normalized_scan_root(root)
        current_root = self.current_scan_root
        has_memory_data = bool(self.files or self.roi_rows or self.metadata_by_subject)
        replacing_corpus = has_memory_data and (not current_root or current_root != new_root)
        if replacing_corpus:
            old_label = current_root or "an imported ROI/metadata table"
            ok = messagebox.askyesno(
                "Replace current scanned corpus",
                "A different corpus or ROI table is already loaded in memory.\n\n"
                f"Current source: {old_label}\n"
                f"New corpus: {new_root}\n\n"
                "Clear the current display, ROI rows, and participant metadata before scanning the new corpus? "
                "Saved output files will not be deleted.",
            )
            if not ok:
                return
            if not self.clear_scanned_data(ask_confirmation=False):
                return

        self.files = scan_token_files(root)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, r in enumerate(self.files):
            self.tree.insert("", "end", iid=str(i), values=(r["Subject"], r["Token"], r["Filename"], r["Folder"]))
        self.current_scan_root = new_root
        self.log(f"Scanned: {root}")
        self.log(f"Found {len(self.files)} token audio files containing afa/ifi/ufu.")
        counts = pd.DataFrame(self.files)["Token"].value_counts().to_dict() if self.files else {}
        self.log(f"Token counts: {counts}")
        if not self.out_var.get().strip():
            self.out_var.set(DEFAULT_OUTPUT)
        # Automatically import existing fricative_locations_* files so you do not need to re-mark ROIs.
        # When a different root is selected, the old in-memory ROI table has already been cleared above.
        self.import_fricative_locations(show_popup=False)
        self.set_status(f"Found {len(self.files)} files. ROI rows in memory: {len(self.roi_rows)}")

    def selected_file_rows(self) -> List[Dict[str, Any]]:
        ids = self.tree.selection()
        if not ids:
            return self.files
        out = []
        for iid in ids:
            try:
                out.append(self.files[int(iid)])
            except Exception:
                pass
        return out

    def load_metadata(self):
        p = filedialog.askopenfilename(title="Metadata CSV/XLSX", filetypes=[("CSV/Excel", "*.csv;*.xlsx;*.xls"), ("All", "*.*")])
        if not p:
            return
        try:
            meta, messages = load_participant_metadata_file(p)
            if not meta:
                raise ValueError("; ".join(messages) or "No usable metadata rows were found.")
            self.metadata_by_subject = meta
            self.log(f"Loaded metadata for {len(self.metadata_by_subject)} subjects from {p}.")
            for msg in messages[:4]:
                self.log("  " + msg)
        except Exception as exc:
            messagebox.showerror("Metadata", f"Could not load metadata:\n{exc}")

    def autosave_roi_table(self, reason: str = ""):
        """Crash-safe ROI autosave. Called after import and after every manual file confirmation."""
        if not self.roi_rows:
            return
        out = self.out_var.get().strip() or DEFAULT_OUTPUT
        try:
            ensure_dir(out)
            df = self.roi_dataframe()
            autosave_csv = pathlib.Path(out) / "rff_roi_marks_AUTOSAVE.csv"
            autosave_xlsx = pathlib.Path(out) / "rff_roi_marks_AUTOSAVE.xlsx"
            df.to_csv(autosave_csv, index=False, encoding="utf-8-sig")
            try:
                df.to_excel(autosave_xlsx, index=False)
            except Exception:
                pass
            backup_dir = pathlib.Path(out) / "roi_autosave_backups"
            ensure_dir(backup_dir)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            df.to_csv(backup_dir / f"rff_roi_marks_{stamp}.csv", index=False, encoding="utf-8-sig")
            if reason:
                self.log(f"ROI autosaved ({reason}): {autosave_csv}")
        except Exception as exc:
            self.log(f"ROI autosave failed: {exc}")

    def import_fricative_locations(self, show_popup: bool = True):
        root = self.root_var.get().strip()
        if not root or not pathlib.Path(root).exists():
            if show_popup:
                messagebox.showerror("Folder", "Choose a valid corpus root folder first.")
            return
        if not self.files:
            self.files = scan_token_files(root)
        df, messages = import_fricative_locations_from_root(root, self.files)
        for msg in messages:
            self.log(msg)
        if df.empty:
            self.log("No ROI rows imported from fricative-location files.")
            if show_popup:
                messagebox.showinfo("Fricative locations", "No ROI rows could be imported.")
            return

        # Append/update: imported rows replace previous rows for the same Path/Token/Rep.
        existing = pd.DataFrame(self.roi_rows) if self.roi_rows else pd.DataFrame()
        if not existing.empty:
            for c in ("Path", "Token", "Rep"):
                if c not in existing.columns:
                    existing[c] = np.nan
            imported_keys = set((str(r["Path"]), str(r["Token"]), int(float(r["Rep"]))) for _, r in df.iterrows())
            keep_mask = []
            for _, r in existing.iterrows():
                try:
                    key = (str(r.get("Path", "")), str(r.get("Token", "")), int(float(r.get("Rep", -1))))
                except Exception:
                    key = (str(r.get("Path", "")), str(r.get("Token", "")), -1)
                keep_mask.append(key not in imported_keys)
            combined = pd.concat([existing.loc[keep_mask], df], ignore_index=True)
        else:
            combined = df.copy()
        combined = combined.sort_values(["Subject", "Token", "Path", "Rep", "FricStart"]).reset_index(drop=True)
        self.roi_rows = combined.to_dict(orient="records")
        self.log(f"ROI table now has {len(self.roi_rows)} rows after importing fricative-location files.")
        self.autosave_roi_table("imported fricative_locations")
        self.set_status(f"ROI rows in memory: {len(self.roi_rows)}")
        if show_popup:
            messagebox.showinfo("Fricative locations", f"Imported {len(df)} ROI rows. Total ROI rows in memory: {len(self.roi_rows)}")

    def mark_selected(self):
        rows = self.selected_file_rows()
        if not rows:
            messagebox.showwarning("Files", "No files available. Scan first.")
            return
        for r in rows:
            self.log(f"Opening ROI marker: {r['Subject']} /{r['Token']}/ {r['Filename']}")
            dlg = ROIMarkerWindow(self, r["Path"], r["Token"], expected_rois=3)
            self.wait_window(dlg)
            rois = getattr(dlg, "rois", [])
            if not rois:
                self.log(f"No ROIs saved for {r['Filename']}.")
                continue
            # Remove previous ROIs for same file, then add new ones.
            self.roi_rows = [x for x in self.roi_rows if x.get("Path") != r["Path"]]
            for i, (a, b) in enumerate(sorted(rois, key=lambda ab: ab[0]), 1):
                self.roi_rows.append({
                    "Subject": r["Subject"],
                    "Filename": r["Filename"],
                    "Path": r["Path"],
                    "Token": r["Token"],
                    "Rep": int(i),
                    "FricStart": float(a),
                    "FricEnd": float(b),
                    "FricLoc": float(0.5 * (a + b)),
                })
            self.log(f"Saved {len(rois)} ROIs for {r['Filename']}.")
            self.autosave_roi_table(f"manual ROI confirmation for {r['Filename']}")
        self.set_status(f"ROI rows in memory: {len(self.roi_rows)}")

    def roi_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.roi_rows)

    def save_roi_only(self):
        if not self.roi_rows:
            messagebox.showwarning("ROI", "No ROI marks in memory.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Output", "Choose an output folder.")
            return
        ensure_dir(out)
        df = self.roi_dataframe()
        df.to_csv(pathlib.Path(out) / "rff_roi_marks.csv", index=False, encoding="utf-8-sig")
        try:
            df.to_excel(pathlib.Path(out) / "rff_roi_marks.xlsx", index=False)
        except Exception:
            pass
        self.log(f"ROI table saved to {out}")

    def load_roi_table(self):
        p = filedialog.askopenfilename(title="Load ROI CSV/XLSX", filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx;*.xls"), ("All", "*.*")])
        if not p:
            return
        try:
            if p.lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(p)
            else:
                df = pd.read_csv(p)
            needed = {"Subject", "Filename", "Path", "Token", "Rep", "FricStart", "FricEnd"}
            missing = needed - set(df.columns)
            if missing:
                raise ValueError(f"ROI table missing columns: {sorted(missing)}")
            self.roi_rows = df.to_dict(orient="records")
            self.log(f"Loaded {len(self.roi_rows)} ROI rows from {p}")
            self.set_status(f"ROI rows in memory: {len(self.roi_rows)}")
        except Exception as exc:
            messagebox.showerror("ROI", f"Could not load ROI table:\n{exc}")

    def update_config_from_gui(self) -> RFFConfig:
        cfg = RFFConfig()
        cfg.praat_path = self.praat_var.get().strip()
        cfg.use_bandpass = bool(self.bandpass_var.get())
        cfg.save_debug_plots = bool(self.debug_plots_var.get())
        cfg.calculate_sti = bool(self.calculate_sti_var.get())
        cfg.default_age_group = self.age_var.get().strip() or "40-64"
        cfg.default_sex = self.sex_var.get().strip() or "Male"
        cfg.allow_default_metadata_for_normative = bool(self.allow_default_normative_var.get())
        cfg.matlab_path = self.matlab_var.get().strip() or "matlab"
        cfg.mb_bridge_dir = self.mb_bridge_dir_var.get().strip() or package_default_dir("rff_auto_mb_roi_bridge")
        cfg.ap_bridge_dir = self.ap_bridge_dir_var.get().strip() or package_default_dir("aRFF_AP_ROI_bridge")
        cfg.run_matlab_mb = bool(self.run_matlab_mb_var.get())
        cfg.run_matlab_ap = bool(self.run_matlab_ap_var.get())
        return cfg

    def run_marked(self):
        if self._run_thread is not None and self._run_thread.is_alive():
            messagebox.showwarning("Processing", "A processing run is already active.")
            return
        if not self.roi_rows:
            messagebox.showwarning("ROI", "No ROI rows. Mark ROIs or load an existing ROI table first.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Output", "Choose an output folder.")
            return
        cfg = self.update_config_from_gui()
        if not self.metadata_by_subject:
            meta, msg = auto_load_participant_metadata(self.root_var.get().strip(), out)
            if meta:
                self.metadata_by_subject = meta
            self.log(msg)
        if not self.metadata_by_subject and not cfg.allow_default_metadata_for_normative:
            self.log("Normative ranking will be withheld: participant-specific age/sex metadata were not loaded.")
        ensure_dir(out)
        if not self._prepare_output_for_new_run(out):
            self.log("New run cancelled before processing.")
            return
        self._stop_event.clear()
        self._set_running_state(True)
        self.set_status("Starting RFF method comparison...")
        self._run_thread = threading.Thread(target=self._run_worker, args=(out, cfg), daemon=True)
        self._run_thread.start()

    def _run_worker(self, out: str, cfg: RFFConfig):
        try:
            _raise_if_stopped(self._stop_event)
            roi_df = self.roi_dataframe().copy()
            wide_rows: List[Dict[str, Any]] = []
            long_rows: List[Dict[str, Any]] = []
            debug_rows: List[Dict[str, Any]] = []
            plot_dir = pathlib.Path(out) / "debug_plots"
            total = len(roi_df)
            self.log(f"Starting RFF comparison for {total} ROI rows.")
            self.log(f"Script version: {SCRIPT_VERSION}")
            self.log("Python methods: AVHI_PRAAT_STRICT, RFF_CEPSTRAL")
            self.log("Cepstral v21 policy: boundary-adjacent 10 cycles only; no deeper steady-state window substitution.")
            if cfg.calculate_sti:
                self.log("Optional RFF STI enabled: bias-corrected participant-level OFF and ON trajectory variability will be exported.")
            else:
                self.log("Optional RFF STI disabled for this run.")
            if cfg.run_matlab_mb:
                self.log("MATLAB bridge enabled: RFF_MB_ROI_MATLAB")
            if cfg.run_matlab_ap:
                self.log("MATLAB bridge enabled: RFF_AP_ROI_MATLAB")

            matlab_manifest = prepare_matlab_manifest(roi_df, out, cfg)
            self.log(f"MATLAB manifest prepared: {matlab_manifest}")

            for idx, row in roi_df.iterrows():
                _raise_if_stopped(self._stop_event)
                wav_path = str(row["Path"])
                subject = str(row.get("Subject") or subject_from_filename(wav_path, str(row.get("Token", ""))))
                token = str(row.get("Token", token_from_filename(wav_path) or "")).lower()
                rep = int(row.get("Rep", 1))
                fst = float(row["FricStart"])
                fend = float(row["FricEnd"])
                meta = metadata_for_subject(subject, self.metadata_by_subject, cfg)
                self.log(f"[{idx+1}/{total}] {subject} /{token}/ rep {rep}")

                methods: List[TraceResult] = []
                try:
                    methods.append(compute_praat_based_rff(
                        wav_path, subject, token, rep, fst, fend, cfg,
                        "AVHI_PRAAT_STRICT", strict=True, subharmonic_repair=False,
                    ))
                except Exception as exc:
                    methods.append(TraceResult(
                        "AVHI_PRAAT_STRICT", subject, os.path.basename(wav_path), wav_path,
                        token, rep, fst, fend, None, None, False, False, str(exc), str(exc),
                    ))
                _raise_if_stopped(self._stop_event)
                try:
                    methods.append(compute_cepstral_rff(wav_path, subject, token, rep, fst, fend, cfg))
                except Exception as exc:
                    methods.append(TraceResult(
                        "RFF_CEPSTRAL", subject, os.path.basename(wav_path), wav_path,
                        token, rep, fst, fend, None, None, False, False, str(exc), str(exc),
                    ))

                for res in methods:
                    _raise_if_stopped(self._stop_event)
                    wide_rows.append(result_to_wide_row(res, meta))
                    long_rows.extend(result_to_long_rows(res, meta))
                    debug_rows.append(result_to_debug_row(res, meta))
                    if cfg.save_debug_plots:
                        plot_trace_debug(res, plot_dir / res.method)

            if cfg.run_matlab_mb:
                _raise_if_stopped(self._stop_event)
                self.log("Running MATLAB MB ROI bridge...")
                rc, stdout, stderr, cmd, files = run_mb_matlab_bridge(
                    matlab_manifest, out, cfg, self._stop_event, self._register_active_process,
                )
                if rc == 130 or self._stop_event.is_set():
                    raise RunStopped("MATLAB MB bridge stopped by user")
                self.log("MATLAB MB command: " + " ".join(cmd))
                if stdout.strip():
                    self.log("MATLAB MB stdout:\n" + stdout.strip()[-4000:])
                if stderr.strip():
                    self.log("MATLAB MB stderr:\n" + stderr.strip()[-4000:])
                if rc == 0:
                    try:
                        w, l, d = load_external_bridge_outputs(files, "RFF_MB_ROI_MATLAB", self.metadata_by_subject, cfg)
                        wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)
                        self.log(f"Loaded MATLAB MB outputs: {len(w)} wide rows, {len(l)} long rows, {len(d)} debug rows.")
                        if cfg.save_debug_plots:
                            stats = plot_external_matlab_bridge_debug(
                                files, "RFF_MB_ROI_MATLAB", plot_dir / "RFF_MB_ROI_MATLAB", self._stop_event,
                            )
                            if stats.get("stopped") or self._stop_event.is_set():
                                raise RunStopped("MATLAB MB debug plotting stopped by user")
                            self.log(f"MATLAB MB debug plots: {stats.get('saved', 0)} saved, {stats.get('failed', 0)} failed.")
                            for err in stats.get("errors", [])[:5]:
                                self.log("  MATLAB MB plot warning: " + str(err))
                    except RunStopped:
                        raise
                    except Exception as exc:
                        self.log(f"Could not load MATLAB MB outputs: {exc}")
                        w, l, d = failed_external_rows(
                            roi_df, "RFF_MB_ROI_MATLAB", f"MATLAB MB output load failed: {exc}",
                            self.metadata_by_subject, cfg,
                        )
                        wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)
                else:
                    msg = f"MATLAB MB bridge failed with return code {rc}. {stderr.strip() or stdout.strip()}"
                    self.log(msg)
                    w, l, d = failed_external_rows(roi_df, "RFF_MB_ROI_MATLAB", msg, self.metadata_by_subject, cfg)
                    wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)

            if cfg.run_matlab_ap:
                _raise_if_stopped(self._stop_event)
                self.log("Running MATLAB aRFF-AP ROI bridge...")
                rc, stdout, stderr, cmd, files = run_ap_matlab_bridge(
                    matlab_manifest, out, cfg, self._stop_event, self._register_active_process,
                )
                if rc == 130 or self._stop_event.is_set():
                    raise RunStopped("MATLAB aRFF-AP bridge stopped by user")
                self.log("MATLAB aRFF-AP command: " + " ".join(cmd))
                if stdout.strip():
                    self.log("MATLAB aRFF-AP stdout:\n" + stdout.strip()[-4000:])
                if stderr.strip():
                    self.log("MATLAB aRFF-AP stderr:\n" + stderr.strip()[-4000:])
                if rc == 0:
                    try:
                        w, l, d = load_external_bridge_outputs(files, "RFF_AP_ROI_MATLAB", self.metadata_by_subject, cfg)
                        wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)
                        self.log(f"Loaded MATLAB aRFF-AP outputs: {len(w)} wide rows, {len(l)} long rows, {len(d)} debug rows.")
                        if cfg.save_debug_plots:
                            stats = plot_external_matlab_bridge_debug(
                                files, "RFF_AP_ROI_MATLAB", plot_dir / "RFF_AP_ROI_MATLAB", self._stop_event,
                            )
                            if stats.get("stopped") or self._stop_event.is_set():
                                raise RunStopped("MATLAB aRFF-AP debug plotting stopped by user")
                            self.log(f"MATLAB aRFF-AP debug plots: {stats.get('saved', 0)} saved, {stats.get('failed', 0)} failed.")
                            for err in stats.get("errors", [])[:5]:
                                self.log("  MATLAB aRFF-AP plot warning: " + str(err))
                    except RunStopped:
                        raise
                    except Exception as exc:
                        self.log(f"Could not load MATLAB aRFF-AP outputs: {exc}")
                        w, l, d = failed_external_rows(
                            roi_df, "RFF_AP_ROI_MATLAB", f"MATLAB aRFF-AP output load failed: {exc}",
                            self.metadata_by_subject, cfg,
                        )
                        wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)
                else:
                    msg = f"MATLAB aRFF-AP bridge failed with return code {rc}. {stderr.strip() or stdout.strip()}"
                    self.log(msg)
                    w, l, d = failed_external_rows(roi_df, "RFF_AP_ROI_MATLAB", msg, self.metadata_by_subject, cfg)
                    wide_rows.extend(w); long_rows.extend(l); debug_rows.extend(d)

            _raise_if_stopped(self._stop_event)
            paths = save_outputs(out, roi_df, wide_rows, long_rows, debug_rows, cfg)
            self.log("Finished. Outputs saved:")
            for k, path_value in paths.items():
                self.log(f"  {k}: {path_value}")
            self.set_status("Finished RFF method comparison.")
        except RunStopped as exc:
            archive = archive_existing_result_outputs(out, "aborted_runs")
            self.log(f"RUN STOPPED: {exc}")
            if archive:
                self.log(f"Partial generated artifacts moved to: {archive}")
            else:
                self.log("No partial result artifacts required archiving.")
            self.set_status("Run stopped. ROI marks were preserved; ready to restart from zero.")
        except Exception as exc:
            archive = archive_existing_result_outputs(out, "failed_runs")
            self.log(f"ERROR: {exc}")
            if archive:
                self.log(f"Partial artifacts from the failed run moved to: {archive}")
            self.set_status("Error during RFF method comparison. See log for details.")
        finally:
            self._register_active_process(None)
            self._ui_queue.put(("run_state", False))



# =============================================================================
# Entry point
# =============================================================================

def main():
    app = RFFComparisonGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
