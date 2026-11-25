"""Score accepted OFF10 and ON1 against the synthetic source-period targets."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

METHODS = {
    "AVHI_PRAAT_STRICT": "AVHI_PRAAT_STRICT",
    "RFF_PRAAT_ROI": "AVHI_PRAAT_STRICT",
    "RFF-TC-ROI": "AVHI_PRAAT_STRICT",
    "RFF_MB_ROI_MATLAB": "RFF_MB_ROI_MATLAB",
    "RFF-MB": "RFF_MB_ROI_MATLAB",
    "RFF_AP_ROI_MATLAB": "RFF_AP_ROI_MATLAB",
    "aRFF-AP": "RFF_AP_ROI_MATLAB",
    "RFF_CEPSTRAL": "RFF_CEPSTRAL",
    "cRFF": "RFF_CEPSTRAL",
}
METADATA = ["ID", "Suite", "Source", "Tract", "F0", "Vowel", "Trajectory", "Condition", "Seed"]
KEY = ["ID", "Method", "Side"]


def score(manifest, canonical, wide, landmarks):
    stimuli = pd.read_csv(manifest, usecols=METADATA)
    targets = pd.read_csv(canonical)
    extract = pd.read_csv(wide).rename(columns={"Subject": "ID"})
    extract["Method"] = extract["Method"].map(METHODS)
    if extract["Method"].isna().any() or extract.duplicated(["ID", "Method"]).any():
        raise ValueError("Expected one row per stimulus and recognized method in the wide export.")
    expected = set(stimuli.ID)
    if set(extract.ID) != expected or not extract.groupby("ID").Method.nunique().eq(4).all():
        raise ValueError("The wide export must represent each stimulus for all four methods.")

    marks = pd.read_csv(
        landmarks, usecols=["Subject", "Method", "Side", "LandmarkIndex", "Time_s", "ValidSide"]
    ).rename(columns={"Subject": "ID"})
    marks["Method"] = marks["Method"].map(METHODS)
    marks = marks[marks["ValidSide"].isin([True, "True", "true"])]
    if marks["Method"].isna().any() or marks.duplicated(KEY + ["LandmarkIndex"]).any():
        raise ValueError("The valid-landmark export contains unrecognized or duplicate cycles.")
    sequences = marks.sort_values("LandmarkIndex").groupby(KEY)["Time_s"].agg(list)

    rows = []
    for side, endpoint, title in (("OFF", 10, "Off"), ("ON", 1, "On")):
        target = targets[targets.Side.eq(side)]
        boundary = target[target.Cycle.eq(endpoint)].set_index("ID")["True_RFF_ST"]
        frequencies = target.groupby("ID").True_F0_Hz.agg(["min", "max"])
        bounds = target.groupby("ID").agg(start=("Start_s", "min"), end=("End_s", "max"))
        for record in extract.to_dict("records"):
            identifier = record["ID"]
            flag = record[title + "Valid"]
            accepted = flag in (True, "True", "true")
            if flag not in (False, "False", "false", True, "True", "true"):
                raise ValueError(f"Unrecognized acceptance flag in {identifier}")
            value = record[f"{side}{endpoint}"] if accepted else np.nan
            key = (identifier, record["Method"], side)
            start, end = np.nan, np.nan
            if accepted:
                if key not in sequences.index or not np.isfinite(value):
                    raise ValueError(f"Missing accepted RFF value or landmarks for {key}")
                times = np.asarray(sequences[key])
                if len(times) != 11 or not np.isfinite(times).all() or not (np.diff(times) > 0).all():
                    raise ValueError(f"Expected 11 increasing accepted landmarks for {key}")
                start = (times[0] - bounds.loc[identifier, "start"]) * 1000
                end = (times[-1] - bounds.loc[identifier, "end"]) * 1000
            source_f0 = frequencies.loc[identifier]
            true = boundary[identifier]
            rows.append(dict(
                ID=identifier, Method=record["Method"], Side=side, Accepted=accepted,
                Estimated_RFF_ST=value, True_RFF_ST=true, Error_ST=value-true,
                True_cycles_within_shared_75_400_Hz=bool(source_f0["min"] >= 75 and source_f0["max"] <= 400),
                Selected_start_displacement_ms=start, Selected_end_displacement_ms=end,
            ))
    return pd.DataFrame(rows).merge(stimuli, on="ID", validate="many_to_one")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "canonical_cycles", "wide_export", "landmark_export", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    metrics = score(args.manifest, args.canonical_cycles, args.wide_export, args.landmark_export)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
