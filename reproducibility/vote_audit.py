"""Prepare temporary vote tracing and reproduce the aggregate counts in Table S14."""
import argparse
import csv
from dataclasses import fields
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

import numpy as np
import pandas as pd

APPLICATION = "avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py"
KEY = ["Subject", "Token", "Rep"]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one occurrence in the evaluated source: {old!r}")
    return text.replace(old, new)


def prepare(repository, scratch):
    """Instrument copies of the evaluated extraction functions."""
    text = (repository / APPLICATION).read_text(encoding="utf-8-sig")
    start = text.index("def refine_pulses_near_edge(")
    end = text.index("\ndef maybe_fix_subharmonic(", start)
    routine = text[start:end]
    edits = [
        ("    pulses_all = np.asarray", '    vote_trace[side] = "no_candidates"\n    pulses_all = np.asarray'),
        ("        return np.asarray(off_near if side", '        vote_trace[side] = "fallback_one_side"\n        return np.asarray(off_near if side'),
        ("                return np.asarray(off_near[:", '                vote_trace[side] = "vote"\n                return np.asarray(off_near[:'),
        ("        return np.asarray(off_near,", '        vote_trace[side] = "fallback_no_vote"\n        return np.asarray(off_near,'),
        ("            return np.asarray(on_near[idx_local:", '            vote_trace[side] = "vote"\n            return np.asarray(on_near[idx_local:'),
        ("    return np.asarray(on_near, dtype=float)", '    vote_trace[side] = "fallback_no_vote"\n    return np.asarray(on_near, dtype=float)'),
    ]
    for old, new in edits:
        routine = replace_once(routine, old, new)
    scratch.mkdir(parents=True)
    (scratch / "tc.py").write_text(text[:start] + "vote_trace = {}\n\n" + routine + text[end:], encoding="utf-8")

    mb = scratch / "rff_auto_mb_roi_bridge"
    shutil.copytree(repository / mb.name, mb)
    helper = mb / "Dependencies" / "get_pulses_slide_mb_native.m"
    text = helper.read_text(encoding="utf-8-sig")
    text = replace_once(text, "function out_pulses =", "function [out_pulses, voted] =")
    text = replace_once(text, "    switch on_off", "    voted = false;\n    switch on_off")
    marker = "                if ~isempty(upa)\n"
    if text.count(marker) != 2:
        raise ValueError("The MB helper does not match the expected offset and onset vote branches.")
    helper.write_text(text.replace(marker, marker + "                    voted = true;\n"), encoding="utf-8")

    bridge = mb / "RFF_auto_MB_ROI_bridge.m"
    text = bridge.read_text(encoding="utf-8-sig")
    marker = "% Execute the original 10-ms sliding-window/voting helper independently at"
    text = replace_once(text, marker, "offBranch = -1; onBranch = -1;\n" + marker)
    for side in ("off", "on"):
        text = replace_once(text, f"{side}_candidates = get_pulses_slide_mb_native(",
                            f"[{side}_candidates, {side}Branch] = get_pulses_slide_mb_native(")
    marker = "debug.NOffCandidates = numel(off_candidates);"
    text = replace_once(text, marker, "debug.OffVoteBranch = double(offBranch);\n"
                        "debug.OnVoteBranch = double(onBranch);\n" + marker)
    text, matches = re.subn(r"(?m)^(\s*)(dbg\.NOffCandidates =)",
                            r"\1dbg.OffVoteBranch = NaN; dbg.OnVoteBranch = NaN;\n\1\2", text)
    if matches != 1:
        raise ValueError("The MB bridge does not match the expected diagnostic schema.")
    bridge.write_text(text, encoding="utf-8")


def trace_tc(scratch, manifest, config, output):
    spec = importlib.util.spec_from_file_location("rff_tc_vote_trace", scratch / "tc.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    settings = json.loads(config.read_text(encoding="utf-8-sig"))
    names = {x.name for x in fields(module.RFFConfig)}
    cfg = module.RFFConfig(**{k: v for k, v in settings.items() if k in names})
    cfg.run_matlab_ap = cfg.run_matlab_mb = cfg.save_debug_plots = False
    cfg.praat_path = ""
    with manifest.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    records = []
    for i, row in enumerate(rows, 1):
        path = row["Filepath"]
        module.vote_trace.clear()
        result = module.compute_praat_based_rff(
            path, row["Subject"], row["Token"], int(row["Rep"]),
            float(row["FricStart"]), float(row["FricEnd"]), cfg, "AVHI_PRAAT_STRICT", strict=True,
        )
        for side, endpoint in (("off", 9), ("on", 0)):
            valid = bool(getattr(result, f"{side}_valid"))
            estimates = getattr(result, f"{side}_rff")
            records.append(dict(
                Subject=row["Subject"], Token=row["Token"], Rep=int(row["Rep"]),
                Side=side, Branch=module.vote_trace.get(side, "not_reached"),
                Accepted=valid, Value=estimates[endpoint] if valid else np.nan,
            ))
        if i % 100 == 0:
            print(f"Traced {i} of {len(rows)} transitions", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output, index=False)


def read_mb(batches, side):
    title = side.capitalize()
    endpoint = "OFF10" if side == "off" else "ON1"
    wide_columns = KEY + [title+"Valid", endpoint]
    debug_columns = KEY + [title+"VoteBranch"]
    wide, debug = [], []
    for directory in batches:
        wide.append(pd.read_csv(directory / "rff_mb_roi_results_wide.csv", usecols=wide_columns))
        debug.append(pd.read_csv(directory / "rff_mb_roi_debug.csv", usecols=debug_columns))
    m = pd.concat(wide).merge(pd.concat(debug), on=KEY, how="outer", validate="one_to_one", indicator=True)
    if not m["_merge"].eq("both").all():
        raise ValueError("MB diagnostic and result records do not cover the same transitions.")
    m["Branch"] = m[title+"VoteBranch"].map({-1: "not_reached", 0: "fallback_no_vote", 1: "vote"})
    if m["Branch"].isna().any():
        raise ValueError("Unknown MB vote branch or failed execution.")
    return m.rename(columns={title+"Valid": "Accepted", endpoint: "Value"})


def counts(rows, label, side):
    vote = rows["Branch"].eq("vote")
    fallback = rows["Branch"].str.startswith("fallback")
    accepted = rows["Accepted"].map({True: True, False: False, "True": True, "False": False})
    if accepted.isna().any() or rows.loc[accepted, "Value"].isna().any():
        raise ValueError(f"Inconsistent acceptance flags for {label} {side}.")
    return dict(
        Method=label, Side=side.upper(), Reached=int((vote | fallback).sum()),
        Voted=int(vote.sum()), Fallback=int(fallback.sum()), Other=int((~(vote | fallback)).sum()),
        Accepted=int(accepted.sum()), AcceptedFallback=int((accepted & fallback).sum()),
        AcceptedVote=int((accepted & vote).sum()), AcceptedOther=int((accepted & ~(vote | fallback)).sum()),
        MedianFallback=rows.loc[accepted & fallback, "Value"].median(),
        MedianVote=rows.loc[accepted & vote, "Value"].median(),
    )


def summarize(tc_path, batches, output, expected_transitions):
    tc = pd.read_csv(tc_path)
    if len(tc) != 2 * expected_transitions or set(tc["Side"]) != {"off", "on"}:
        raise ValueError("The TC-ROI trace does not cover both sides of the requested transitions.")
    records = []
    for side in ("off", "on"):
        t = tc[tc["Side"].eq(side)]
        m = read_mb(batches, side)
        if len(t) != expected_transitions or len(m) != expected_transitions:
            raise ValueError(f"Unexpected transition count for {side}.")
        if set(KEY).issubset(t):
            joined = t[KEY].merge(m[KEY], on=KEY, how="outer", validate="one_to_one", indicator=True)
            if not joined["_merge"].eq("both").all():
                raise ValueError("The two trace sets do not cover the same transitions.")
        records.extend([counts(t, "RFF-TC-ROI", side), counts(m, "RFF-MB", side)])
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(output, index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare", help="Instrument copies of the evaluated sources")
    preparation.add_argument("repository", type=Path)
    preparation.add_argument("scratch", type=Path)
    tc = commands.add_parser("trace-tc", help="Replay TC-ROI on a local corpus manifest")
    for name in ("scratch", "manifest", "config", "output"):
        tc.add_argument(name, type=Path)
    summary = commands.add_parser("summarize", help="Aggregate TC-ROI and MB trace outputs")
    summary.add_argument("tc_csv", type=Path)
    summary.add_argument("output", type=Path)
    summary.add_argument("mb_batches", type=Path, nargs="+")
    summary.add_argument("--transitions", type=int, default=639)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.repository, args.scratch)
    elif args.command == "trace-tc":
        trace_tc(args.scratch, args.manifest, args.config, args.output)
    else:
        summarize(args.tc_csv, args.mb_batches, args.output, args.transitions)


if __name__ == "__main__":
    main()
