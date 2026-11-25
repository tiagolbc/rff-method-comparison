"""Regenerate the study's 2,520 positive stimuli and 24 target-absent controls."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal
import soundfile as sf

FS = 44100
FORMANTS = {
    "a": [730, 1090, 2440, 3500, 4500],
    "i": [270, 2290, 3010, 3500, 4500],
    "u": [300, 870, 2240, 3500, 4500],
}
MANIFEST_COLUMNS = ["Filepath", "Subject", "Filename", "Token", "Rep", "FricStart", "FricEnd"]


def synthesize(row, protocol, output):
    rng = np.random.default_rng(int(row["Seed"]) + int(row["StimulusIndex"]) * 7919)
    f0, condition = row["F0"], row["Condition"]
    off_target, on_target = protocol["Trajectories"][row["Trajectory"]]
    jitter = {"jitter1pct": .01, "jitter3pct": .03, "compound": .03}.get(condition, 0)
    shimmer = .10 if condition in ("shimmer10pct", "compound") else 0
    alternate = .30 if condition in ("alternation30pct", "compound") else 0
    soft = condition in ("soft_boundary", "compound")
    n = max(40, int(round(f0 * .48)))
    off_st, on_st = np.zeros(n), np.zeros(n)
    off_st[-10:] = off_target * np.linspace(0, 1, 10)**2
    on_st[:10] = on_target * np.linspace(1, 0, 10)**2

    periods, times, amplitudes = [], [], []
    for side, st in [("OFF", off_st), ("ON", on_st)]:
        per = (1/f0) * 2**(-st/12) * np.exp(rng.normal(0, jitter, n))
        events = np.r_[0, np.cumsum(per)]
        amp = np.exp(rng.normal(-.5*shimmer**2, shimmer, n)) * (1-alternate*(np.arange(n)%2))
        if soft:
            taper = np.linspace(.12, 1, 10)**1.5
            if side == "OFF":
                amp[-10:] *= taper[::-1]
            else:
                amp[:10] *= taper
        periods.append(per)
        times.append(events)
        amplitudes.append(amp)

    first_source = .06
    fric_start = first_source + times[0][-1]
    fric_end = fric_start + .15
    starts = [first_source, fric_end]
    duration = fric_end + times[1][-1] + .06
    t = np.arange(int(np.ceil(duration * FS))) / FS
    flow = np.zeros_like(t)
    for k in range(2):
        events = times[k] + starts[k]
        for j, per in enumerate(periods[k]):
            left, right = events[j], events[j+1]
            i0, i1 = int(np.ceil(left*FS)), min(len(t), int(np.ceil(right*FS)))
            phase = (t[i0:i1] - left) / per
            g = np.zeros_like(phase)
            if row["Source"] == "rosenberg":
                opening = phase < .4
                closing = (phase >= .4) & (phase < .6)
                g[opening] = .5 * (1-np.cos(np.pi*phase[opening]/.4))
                g[closing] = np.cos(np.pi*(phase[closing]-.4)/.4)
            else:
                for h in range(1, min(40, int(FS/(2*f0)))):
                    g += np.sin(2*np.pi*h*phase + .17*h)/(h**1.5)
            flow[i0:i1] = amplitudes[k][j] * g

    y = np.r_[0, np.diff(flow)] * FS if row["Source"] == "rosenberg" else flow.copy()
    formants = np.array(FORMANTS[row["Vowel"]], float) * (1.17 if row["Tract"] == "female_like" else 1)
    for f, bw in zip(formants, [80, 90, 120, 180, 220]):
        radius = np.exp(-np.pi*bw/FS)
        a = [1, -2*radius*np.cos(2*np.pi*f/FS), radius*radius]
        y = signal.lfilter([1-radius], a, y)
    voiced = ((t >= first_source) & (t < fric_start)) | ((t >= fric_end) & (t < fric_end+times[1][-1]))
    y /= max(np.sqrt(np.mean(y[voiced]**2)), 1e-20)
    fric = (t >= fric_start) & (t < fric_end)
    sos = signal.butter(2, [1500, 9000], fs=FS, btype="bandpass", output="sos")
    noise = signal.sosfilt(sos, rng.normal(size=t.size))
    noise /= np.sqrt(np.mean(noise**2))
    y[fric] += .18 * noise[fric]
    snr = {"noise30": 30, "noise15": 15, "compound": 15}.get(condition)
    if snr is not None:
        y += rng.normal(size=t.size)*10**(-snr/20)
    y *= .85 / max(np.max(np.abs(y)), 1e-20)
    path = output / "audio" / f"{row['ID']}.wav"
    sf.write(path, y, FS, subtype="FLOAT")

    canonical, full_reference = [], {}
    for k, side in enumerate(["OFF", "ON"]):
        events = times[k] + starts[k]
        freqs = 1 / periods[k]
        selected = np.arange(n-10, n) if side == "OFF" else np.arange(10)
        ref = selected[0] if side == "OFF" else selected[-1]
        values = 12 * np.log2(freqs[selected] / freqs[ref])
        full_reference[side+"_events"] = events
        full_reference[side+"_frequencies"] = freqs
        for cycle, j, value in zip(range(1, 11), selected, values):
            canonical.append({
                "ID": row["ID"], "Side": side, "Cycle": cycle, "True_RFF_ST": float(value),
                "True_F0_Hz": float(freqs[j]), "Start_s": float(events[j]), "End_s": float(events[j+1]),
            })
    np.savez_compressed(output / "truth" / f"{row['ID']}.npz", **full_reference)
    manifest = {
        **row, "Filepath": str(path), "Subject": row["ID"], "Filename": path.name,
        "Token": row["Vowel"]+"f"+row["Vowel"], "Rep": 1, "FricStart": fric_start,
        "FricEnd": fric_end, "Duration": duration, "SHA256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return manifest, canonical


def write_manifests(rows, folder):
    manifest = pd.DataFrame(rows)
    manifest.to_csv(folder / "manifest.csv", index=False)
    manifest[MANIFEST_COLUMNS].to_csv(folder / "matlab_manifest.csv", index=False)


def generate_positive(output, protocol):
    (output / "audio").mkdir()
    (output / "truth").mkdir()
    manifest, truth = [], []
    grid = itertools.product(
        protocol["Vocal_tract_profiles"], protocol["F0_Hz"], protocol["Vowels"],
        protocol["Trajectories"], protocol["Replicate_seeds"],
    )
    designs = [
        (source, suite, condition)
        for source, suite, conditions in [
            ("rosenberg", "main", protocol["Main_conditions"]),
            ("harmonic", "independent_source", ["clean"]),
            ("rosenberg", "compound", ["compound"]),
        ]
        for condition in conditions
    ]
    for tract, f0, vowel, trajectory, seed in grid:
        for source, suite, condition in designs:
            i = len(manifest)
            row = dict(
                Source=source, Suite=suite, Tract=tract, F0=f0, Vowel=vowel,
                Trajectory=trajectory, Seed=seed, Condition=condition, ID=f"S{i+1:05d}", StimulusIndex=i,
            )
            entry, canonical = synthesize(row, protocol, output)
            manifest.append(entry)
            truth.extend(canonical)
            if len(manifest) % 250 == 0:
                print(f"Generated {len(manifest)} positive stimuli", flush=True)
    if len(manifest) != protocol["Synthetic_total"]:
        raise ValueError(f"Unexpected benchmark size: {len(manifest)}")
    write_manifests(manifest, output)
    pd.DataFrame(truth).to_csv(output / "truth" / "canonical_cycles.csv", index=False)


def generate_controls(output, protocol):
    output.mkdir()
    rows = []
    grid = itertools.product(
        protocol["Vocal_tract_profiles"], protocol["Vowels"], protocol["Replicate_seeds"],
        ["colored_noise_only", "silent_vowels"],
    )
    for i, (tract, vowel, seed, condition) in enumerate(grid):
        identifier = f"N{i+1:04d}"
        rng = np.random.default_rng(seed+i*7919)
        t = np.arange(int(1.27*FS))/FS
        x = rng.normal(size=len(t))
        fric = (t >= .54) & (t < .69)
        vowels = ((t >= .06) & (t < .54)) | ((t >= .69) & (t < 1.17))
        for f, bw in zip(FORMANTS[vowel], [80, 90, 120, 180, 220]):
            f = f * (1.17 if tract == "female_like" else 1)
            radius = np.exp(-np.pi*bw/FS)
            x = signal.lfilter([1-radius], [1, -2*radius*np.cos(2*np.pi*f/FS), radius*radius], x)
        x /= max(np.sqrt(np.mean(x*x)), 1e-20)
        y = np.zeros_like(x)
        if condition == "colored_noise_only":
            y[vowels] = x[vowels]
        sos = signal.butter(2, [1500, 9000], btype="bandpass", fs=FS, output="sos")
        fric_noise = signal.sosfilt(sos, rng.normal(size=len(t)))
        fric_noise /= np.std(fric_noise)
        y[fric] = .18*fric_noise[fric]
        y *= .85/max(np.max(np.abs(y)), 1e-20)
        path = output / f"{identifier}.wav"
        sf.write(path, y, FS, subtype="FLOAT")
        rows.append(dict(
            ID=identifier, Subject=identifier, Filepath=str(path), Filename=path.name,
            Token=vowel+"f"+vowel, Rep=1, FricStart=.54, FricEnd=.69, Tract=tract,
            Vowel=vowel, Seed=seed, Condition=condition, SHA256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ))
    write_manifests(rows, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New destination directory")
    args = parser.parse_args()
    protocol = json.loads(Path(__file__).with_name("synthetic_protocol.json").read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.mkdir(parents=True)
    generate_positive(output, protocol)
    generate_controls(output / "negative_controls", protocol)
    print(f"Wrote the benchmark waveforms, ROIs and source-period targets to {output}")


if __name__ == "__main__":
    main()
