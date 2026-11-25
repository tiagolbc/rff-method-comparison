#!/usr/bin/env python3
"""
Complete exploratory spatiotemporal-index analysis of RFF trajectories.

Input
-----
RFF_cycle_level_v24.csv

Primary STI calculation
-----------------------
For every participant, RFF method, and side:
1. retain complete valid 10-cycle traces;
2. z-score each trace using the sample standard deviation;
3. interpolate to 1,000 points with a not-a-knot cubic spline;
4. sample the midpoint of each 2% block (50 values);
5. sum the sample SD across traces at the 50 points;
6. apply the finite-sample correction:
   BC-STI = STI * sqrt((k-1)/2) * Gamma((k-1)/2) / Gamma(k/2).

Outputs include descriptive summaries, adjusted strain models, minimum-trace
sensitivities, boundary-cycle SD models, group comparisons, method agreement,
exact common-transition analyses, and 1,000 trace-count-balanced subsamples.
"""

from pathlib import Path
from itertools import combinations
import argparse
import math

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.interpolate import CubicSpline
from scipy import stats
from scipy.stats import norm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

METHOD_ORDER = ["RFF-Praat-ROI", "RFF-MB", "aRFF-AP", "Cepstral-assisted RFF"]
SIDE_ORDER = ["OFF", "ON"]
DISPLAY = {
    "RFF-Praat-ROI": "RFF-Praat-ROI",
    "RFF-MB": "RFF-MB",
    "aRFF-AP": "aRFF-AP",
    "Cepstral-assisted RFF": "cRFF",
}

def bc_factor(k: int) -> float:
    if k < 2:
        return float("nan")
    return math.exp(
        0.5 * math.log((k - 1) / 2.0)
        + math.lgamma((k - 1) / 2.0)
        - math.lgamma(k / 2.0)
    )

def normalize_trace(values):
    values = np.asarray(values, dtype=float)
    sd = np.std(values, ddof=1)
    if not np.isfinite(sd) or sd <= 1e-12:
        return None
    z = (values - np.mean(values)) / sd
    x = np.linspace(0.0, 1.0, 10)
    x1000 = np.linspace(0.0, 1.0, 1000)
    midpoint_indices = np.arange(9, 1000, 20)  # 1-indexed 10,30,...,990
    return CubicSpline(x, z)(x1000)[midpoint_indices]

def sti_from_normalized(traces):
    traces = np.asarray(traces, dtype=float)
    k = len(traces)
    if k < 2:
        return np.nan, np.nan
    raw = float(np.std(traces, axis=0, ddof=1).sum())
    return raw, float(raw * bc_factor(k))

def build_trace_table(cycle):
    rows = []
    valid = cycle[(cycle["ValidSide"] == 1) & cycle["RFF_ST"].notna()].copy()
    for (subject, method, token, rep, side), g in valid.groupby(
        ["Subject", "Method", "Token", "Rep", "Side"], sort=False
    ):
        g = g.sort_values("Cycle")
        if len(g) != 10 or g["Cycle"].tolist() != list(range(1, 11)):
            continue
        values = g["RFF_ST"].to_numpy(float)
        norm50 = normalize_trace(values)
        if norm50 is None:
            continue
        meta = g.iloc[0]
        row = {
            "Subject": subject, "Method": method, "Token": token, "Rep": int(rep),
            "Side": side,
            "BoundaryValue": values[9] if side == "OFF" else values[0],
            "Age": meta["Age"], "Sex": meta["Sex"], "CPPSStatus": meta["CPPSStatus"],
            "PerceptualGroup4": meta["PerceptualGroup4"],
            "PerceptualGroup3": meta.get("PerceptualGroup3", np.nan),
            "AnyTension": meta.get("AnyTension", np.nan),
            "Roughness": meta["Roughness"], "Breathiness": meta["Breathiness"],
            "Tension": meta["Tension"],
        }
        row.update({f"P{i+1}": norm50[i] for i in range(50)})
        rows.append(row)
    return pd.DataFrame(rows)

def subject_metrics(traces):
    rows = []
    pcols = [f"P{i}" for i in range(1, 51)]
    for (subject, method, side), g in traces.groupby(["Subject", "Method", "Side"]):
        raw, corrected = sti_from_normalized(g[pcols].to_numpy())
        meta = g.iloc[0]
        rows.append({
            "Subject": subject, "Method": method, "Side": side, "NTraces": len(g),
            "STI_raw": raw, "STI_BC": corrected,
            "BoundaryMean": g["BoundaryValue"].mean(),
            "BoundarySD": g["BoundaryValue"].std(ddof=1) if len(g) >= 2 else np.nan,
            "Age": meta["Age"], "Sex": meta["Sex"], "CPPSStatus": meta["CPPSStatus"],
            "PerceptualGroup4": meta["PerceptualGroup4"],
            "PerceptualGroup3": meta.get("PerceptualGroup3", np.nan),
            "AnyTension": meta.get("AnyTension", np.nan),
            "Roughness": meta["Roughness"], "Breathiness": meta["Breathiness"],
            "Tension": meta["Tension"],
        })
    return pd.DataFrame(rows)

def prepare_covariates(g):
    g = g.copy()
    g["Tension10"] = g["Tension"] / 10
    g["Roughness10"] = g["Roughness"] / 10
    g["Breathiness10"] = g["Breathiness"] / 10
    g["Age10"] = g["Age"] / 10
    return g

def strain_models(metrics, min_traces=2, outcome="STI_BC", add_mean=False, add_n=False):
    rows = []
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = metrics[
                (metrics["Method"] == method) & (metrics["Side"] == side)
                & (metrics["NTraces"] >= min_traces) & metrics[outcome].notna()
            ]
            g = prepare_covariates(g)
            terms = "Tension10 + Roughness10 + Breathiness10 + Age10 + C(Sex) + C(CPPSStatus)"
            if add_mean:
                terms += " + BoundaryMean"
            if add_n:
                terms += " + NTraces"
            model = smf.ols(f"{outcome} ~ {terms}", data=g).fit(cov_type="HC3")
            ci = model.conf_int().loc["Tension10"]
            rows.append({
                "Method": method, "Side": side, "MinTraces": min_traces,
                "Outcome": outcome, "AddMean": add_mean, "AddN": add_n,
                "N": len(g), "BetaStrain10": model.params["Tension10"],
                "SE": model.bse["Tension10"],
                "CI_low": ci.iloc[0], "CI_high": ci.iloc[1],
                "p": model.pvalues["Tension10"],
                "R2": model.rsquared, "AdjR2": model.rsquared_adj,
            })
    out = pd.DataFrame(rows)
    out["FDR_p"] = multipletests(out["p"], method="fdr_bh")[1]
    return out

def descriptive(metrics):
    return (
        metrics[metrics["NTraces"] >= 2]
        .groupby(["Method", "Side"])
        .agg(
            N=("Subject", "size"),
            NTraces_mean=("NTraces", "mean"),
            NTraces_median=("NTraces", "median"),
            STI_mean=("STI_BC", "mean"),
            STI_sd=("STI_BC", "std"),
            STI_median=("STI_BC", "median"),
            STI_q1=("STI_BC", lambda x: x.quantile(.25)),
            STI_q3=("STI_BC", lambda x: x.quantile(.75)),
            BoundarySD_mean=("BoundarySD", "mean"),
            BoundarySD_sd=("BoundarySD", "std"),
        ).reset_index()
    )

def group_comparisons(metrics):
    order = ["Normal", "R/B without tension", "Isolated tension", "R/B + tension"]
    rows = []
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = metrics[
                (metrics["Method"] == method) & (metrics["Side"] == side)
                & (metrics["NTraces"] >= 2) & metrics["STI_BC"].notna()
            ]
            arrays = [g.loc[g["PerceptualGroup4"] == grp, "STI_BC"].dropna().to_numpy() for grp in order]
            kw = stats.kruskal(*arrays)
            row = {"Method": method, "Side": side, "N": len(g), "KW_H": kw.statistic, "p": kw.pvalue}
            for i, a in enumerate(arrays, 1):
                row[f"n_{i}"] = len(a)
                row[f"mean_{i}"] = np.mean(a) if len(a) else np.nan
                row[f"median_{i}"] = np.median(a) if len(a) else np.nan
            rows.append(row)
    out = pd.DataFrame(rows)
    out["FDR_p"] = multipletests(out["p"], method="fdr_bh")[1]
    return out

def lin_ccc(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    vx, vy = x.var(ddof=1), y.var(ddof=1)
    cov = np.cov(x, y, ddof=1)[0, 1]
    return 2 * cov / (vx + vy + (x.mean() - y.mean()) ** 2)

def method_agreement(metrics):
    rows = []
    for side in SIDE_ORDER:
        wide = metrics[
            (metrics["Side"] == side) & (metrics["NTraces"] >= 2)
        ].pivot(index="Subject", columns="Method", values="STI_BC")
        for a, b in combinations(METHOD_ORDER, 2):
            d = wide[[a, b]].dropna()
            rho, rho_p = stats.spearmanr(d[a], d[b])
            pearson, _ = stats.pearsonr(d[a], d[b])
            diff = d[b] - d[a]
            rows.append({
                "Side": side, "Method1": a, "Method2": b, "N": len(d),
                "Spearman": rho, "Spearman_p": rho_p, "Pearson": pearson,
                "CCC": lin_ccc(d[a], d[b]),
                "Bias_M2_minus_M1": diff.mean(),
                "MAE": np.abs(diff).mean(),
                "RMSE": np.sqrt(np.mean(diff ** 2)),
            })
    return pd.DataFrame(rows)

def method_differences(metrics):
    omni, pairwise = [], []
    for side in SIDE_ORDER:
        wide = metrics[
            (metrics["Side"] == side) & (metrics["NTraces"] >= 2)
        ].pivot(index="Subject", columns="Method", values="STI_BC")
        complete = wide[METHOD_ORDER].dropna()
        fr = stats.friedmanchisquare(*[complete[m] for m in METHOD_ORDER])
        omni.append({"Side": side, "N": len(complete), "Friedman_chi2": fr.statistic, "p": fr.pvalue})
        temp, pvals = [], []
        for a, b in combinations(METHOD_ORDER, 2):
            w = stats.wilcoxon(complete[a], complete[b])
            temp.append({
                "Side": side, "Method1": a, "Method2": b, "N": len(complete),
                "MedianDiff_M2-M1": np.median(complete[b] - complete[a]),
                "MeanDiff_M2-M1": np.mean(complete[b] - complete[a]),
                "W": w.statistic, "p": w.pvalue,
            })
            pvals.append(w.pvalue)
        adjusted = multipletests(pvals, method="holm")[1]
        for row, p_adj in zip(temp, adjusted):
            row["Holm_p"] = p_adj
            pairwise.append(row)
    return pd.DataFrame(omni), pd.DataFrame(pairwise)

def exact_common_metrics(traces):
    rows = []
    pcols = [f"P{i}" for i in range(1, 51)]
    for side in SIDE_ORDER:
        d = traces[traces["Side"] == side]
        counts = d.groupby(["Subject", "Token", "Rep"])["Method"].nunique()
        common_ids = set(counts[counts == 4].index)
        common = d.set_index(["Subject", "Token", "Rep"])
        common = common.loc[common.index.isin(common_ids)].reset_index()
        for (subject, method), g in common.groupby(["Subject", "Method"]):
            if len(g) < 2:
                continue
            raw, corrected = sti_from_normalized(g[pcols].to_numpy())
            meta = g.iloc[0]
            rows.append({
                "Subject": subject, "Method": method, "Side": side,
                "NTraces": len(g), "STI_raw": raw, "STI_BC": corrected,
                "BoundaryMean": g["BoundaryValue"].mean(),
                "BoundarySD": g["BoundaryValue"].std(ddof=1),
                "Age": meta["Age"], "Sex": meta["Sex"], "CPPSStatus": meta["CPPSStatus"],
                "PerceptualGroup4": meta["PerceptualGroup4"],
                "Roughness": meta["Roughness"], "Breathiness": meta["Breathiness"],
                "Tension": meta["Tension"],
            })
    return pd.DataFrame(rows)

def fit_on_dataframe(data, outcome="STI_BC"):
    rows = []
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = data[(data["Method"] == method) & (data["Side"] == side) & data[outcome].notna()]
            g = prepare_covariates(g)
            model = smf.ols(
                f"{outcome} ~ Tension10 + Roughness10 + Breathiness10 + Age10 + C(Sex) + C(CPPSStatus)",
                data=g
            ).fit(cov_type="HC3")
            ci = model.conf_int().loc["Tension10"]
            rows.append({
                "Method": method, "Side": side, "N": len(g),
                "BetaStrain10": model.params["Tension10"],
                "CI_low": ci.iloc[0], "CI_high": ci.iloc[1],
                "p": model.pvalues["Tension10"],
            })
    out = pd.DataFrame(rows)
    out["FDR_p"] = multipletests(out["p"], method="fdr_bh")[1]
    return out

def full_covariate_models(metrics):
    rows = []
    predictors = [
        "Tension10", "Roughness10", "Breathiness10", "Age10",
        "C(Sex)[T.Male]", "C(CPPSStatus)[T.Normal]"
    ]
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = metrics[
                (metrics["Method"] == method) & (metrics["Side"] == side)
                & (metrics["NTraces"] >= 2) & metrics["STI_BC"].notna()
            ]
            g = prepare_covariates(g)
            model = smf.ols(
                "STI_BC ~ Tension10 + Roughness10 + Breathiness10 + Age10 + C(Sex) + C(CPPSStatus)",
                data=g
            ).fit(cov_type="HC3")
            for predictor in predictors:
                if predictor not in model.params:
                    continue
                ci = model.conf_int().loc[predictor]
                rows.append({
                    "Method": method, "Side": side, "Predictor": predictor, "N": len(g),
                    "Beta": model.params[predictor], "CI_low": ci.iloc[0], "CI_high": ci.iloc[1],
                    "p": model.pvalues[predictor],
                })
    out = pd.DataFrame(rows)
    out["FDR_p_within_predictor"] = np.nan
    for predictor in out["Predictor"].unique():
        mask = out["Predictor"] == predictor
        out.loc[mask, "FDR_p_within_predictor"] = multipletests(
            out.loc[mask, "p"], method="fdr_bh"
        )[1]
    return out

def ols_hc3_beta_p(y, X, beta_index=1):
    y, X = np.asarray(y, float), np.asarray(X, float)
    inv = np.linalg.pinv(X.T @ X)
    beta = inv @ X.T @ y
    residual = y - X @ beta
    leverage = np.einsum("ij,jk,ik->i", X, inv, X)
    adjusted = residual / (1 - leverage)
    meat = X.T @ ((adjusted ** 2)[:, None] * X)
    covariance = inv @ meat @ inv
    se = np.sqrt(np.maximum(np.diag(covariance), 0))
    z = beta[beta_index] / se[beta_index]
    return beta[beta_index], 2 * norm.sf(abs(z))

def balanced_subsampling(traces, cycle, iterations=1000, min_traces=3, seed=20260717):
    pcols = [f"P{i}" for i in range(1, 51)]
    arrays = {
        key: g[pcols].to_numpy(float)
        for key, g in traces.groupby(["Subject", "Method", "Side"])
    }
    meta = (
        cycle[["Subject", "Age", "Sex", "CPPSStatus", "Tension", "Roughness", "Breathiness"]]
        .drop_duplicates("Subject").set_index("Subject")
    )
    rng = np.random.default_rng(seed)
    records = []
    for side in SIDE_ORDER:
        eligible = []
        for subject in meta.index:
            counts = [len(arrays.get((subject, method, side), [])) for method in METHOD_ORDER]
            if min(counts) >= min_traces:
                eligible.append((subject, min(counts)))
        subjects = [s for s, _ in eligible]
        minimums = dict(eligible)
        d = meta.loc[subjects].copy()
        X = np.column_stack([
            np.ones(len(d)),
            d["Tension"].to_numpy() / 10,
            d["Roughness"].to_numpy() / 10,
            d["Breathiness"].to_numpy() / 10,
            d["Age"].to_numpy() / 10,
            (d["Sex"] == "Male").astype(float).to_numpy(),
            (d["CPPSStatus"] == "Altered").astype(float).to_numpy(),
        ])
        for iteration in range(1, iterations + 1):
            for method in METHOD_ORDER:
                y = []
                for subject in subjects:
                    arr = arrays[(subject, method, side)]
                    k = minimums[subject]
                    selected = arr[rng.choice(len(arr), size=k, replace=False)]
                    raw = np.std(selected, axis=0, ddof=1).sum()
                    y.append(raw * bc_factor(k))
                beta, p = ols_hc3_beta_p(y, X)
                records.append({
                    "Iteration": iteration, "Side": side, "Method": method,
                    "N": len(subjects), "BetaStrain10": beta, "p": p,
                })
    iterations_df = pd.DataFrame(records)
    summary = (
        iterations_df.groupby(["Method", "Side"])
        .agg(
            N=("N", "first"),
            Beta_median=("BetaStrain10", "median"),
            Beta_mean=("BetaStrain10", "mean"),
            Beta_p2_5=("BetaStrain10", lambda x: np.quantile(x, .025)),
            Beta_p97_5=("BetaStrain10", lambda x: np.quantile(x, .975)),
            Prop_positive=("BetaStrain10", lambda x: (x > 0).mean()),
            Prop_p_lt_05=("p", lambda x: (x < .05).mean()),
            Median_p=("p", "median"),
        ).reset_index()
    )
    return iterations_df, summary

def correlations_with_mean(metrics):
    rows = []
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = metrics[
                (metrics["Method"] == method) & (metrics["Side"] == side)
                & (metrics["NTraces"] >= 2)
            ].dropna(subset=["STI_BC", "BoundaryMean"])
            rho, p = stats.spearmanr(g["STI_BC"], g["BoundaryMean"])
            rows.append({
                "Method": method, "Side": side, "N": len(g),
                "Spearman_STI_mean": rho, "p": p,
            })
    return pd.DataFrame(rows)

def make_figures(metrics, primary, balanced_iterations, figures_dir):
    figures_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for method in METHOD_ORDER:
        for side in SIDE_ORDER:
            g = metrics[(metrics["Method"] == method) & (metrics["Side"] == side)]
            rows.append({
                "Label": f"{DISPLAY[method]}\n{side}",
                "At least 2": int((g["NTraces"] >= 2).sum()),
                "At least 3": int((g["NTraces"] >= 3).sum()),
                "At least 6": int((g["NTraces"] >= 6).sum()),
            })
    avail = pd.DataFrame(rows)
    x = np.arange(len(avail)); width = .25
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x-width, avail["At least 2"], width, label="At least 2")
    ax.bar(x, avail["At least 3"], width, label="At least 3")
    ax.bar(x+width, avail["At least 6"], width, label="At least 6")
    ax.set_ylabel("Participants with calculable STI")
    ax.set_xticks(x); ax.set_xticklabels(avail["Label"]); ax.set_ylim(0, 75)
    ax.legend(); ax.grid(axis="y", alpha=.25); fig.tight_layout()
    fig.savefig(figures_dir / "Figure_STI_1_Availability.png", dpi=300); plt.close(fig)

    labels = [f"{DISPLAY[m]}\n{s}" for m in METHOD_ORDER for s in SIDE_ORDER]
    plot = metrics[metrics["NTraces"] >= 2].copy()
    plot["Label"] = plot.apply(lambda r: f"{DISPLAY[r['Method']]}\n{r['Side']}", axis=1)
    data = [plot.loc[plot["Label"] == label, "STI_BC"].dropna().to_numpy() for label in labels]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.boxplot(data, tick_labels=labels, showmeans=True)
    ax.set_ylabel("Bias-corrected RFF spatiotemporal index")
    ax.grid(axis="y", alpha=.25); fig.tight_layout()
    fig.savefig(figures_dir / "Figure_STI_2_Distributions.png", dpi=300); plt.close(fig)

    forest = primary.copy()
    forest["Label"] = forest.apply(lambda r: f"{DISPLAY[r['Method']]} {r['Side']}", axis=1)
    forest = forest.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(forest))
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.errorbar(
        forest["BetaStrain10"], y,
        xerr=[forest["BetaStrain10"]-forest["CI_low"], forest["CI_high"]-forest["BetaStrain10"]],
        fmt="o", capsize=4
    )
    ax.axvline(0, linewidth=1); ax.set_yticks(y); ax.set_yticklabels(forest["Label"])
    ax.set_xlabel("Change in bias-corrected STI per 10-point increase in strain")
    ax.grid(axis="x", alpha=.25); fig.tight_layout()
    fig.savefig(figures_dir / "Figure_STI_3_Adjusted_Strain_Associations.png", dpi=300); plt.close(fig)

    plot = balanced_iterations.copy()
    plot["Label"] = plot.apply(lambda r: f"{DISPLAY[r['Method']]}\n{r['Side']}", axis=1)
    data = [plot.loc[plot["Label"] == label, "BetaStrain10"].to_numpy() for label in labels]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.boxplot(data, tick_labels=labels, showfliers=False)
    ax.axhline(0, linewidth=1)
    ax.set_ylabel("Adjusted strain coefficient across balanced subsamples")
    ax.grid(axis="y", alpha=.25); fig.tight_layout()
    fig.savefig(figures_dir / "Figure_STI_4_Balanced_Subsampling.png", dpi=300); plt.close(fig)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cycle_csv")
    parser.add_argument("--out", default="RFF_STI_results")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260717)
    args = parser.parse_args()

    out = Path(args.out)
    tables_dir = out / "tables"
    figures_dir = out / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    cycle = pd.read_csv(args.cycle_csv)
    traces = build_trace_table(cycle)
    metrics = subject_metrics(traces)

    primary = strain_models(metrics, 2)
    min3 = strain_models(metrics, 3)
    min6 = strain_models(metrics, 6)
    incremental = strain_models(metrics, 2, add_mean=True)
    add_n = strain_models(metrics, 2, add_n=True)
    boundary_sd = strain_models(metrics, 2, outcome="BoundarySD")
    raw = strain_models(metrics, 2, outcome="STI_raw")
    groups = group_comparisons(metrics)
    agreement = method_agreement(metrics)
    omni, pairwise = method_differences(metrics)
    common = exact_common_metrics(traces)
    common_models = fit_on_dataframe(common)
    common_groups = group_comparisons(common.assign(NTraces=common["NTraces"]))
    common_omni, common_pairwise = method_differences(common.assign(NTraces=common["NTraces"]))
    balanced_iterations, balanced_summary = balanced_subsampling(
        traces, cycle, iterations=args.iterations, seed=args.seed
    )
    full_cov = full_covariate_models(metrics)
    corr_mean = correlations_with_mean(metrics)

    outputs = {
        "STI_subject_method_side.csv": metrics,
        "STI_descriptive_by_method_side.csv": descriptive(metrics),
        "STI_primary_strain_models_min2.csv": primary,
        "STI_strain_models_min3.csv": min3,
        "STI_strain_models_min6.csv": min6,
        "STI_strain_models_adjusted_for_mean_RFF.csv": incremental,
        "STI_strain_models_adjusted_for_trace_count.csv": add_n,
        "Boundary_SD_strain_models.csv": boundary_sd,
        "STI_raw_strain_models.csv": raw,
        "STI_group_comparisons.csv": groups,
        "STI_method_agreement.csv": agreement,
        "STI_method_difference_omnibus.csv": omni,
        "STI_method_difference_pairwise.csv": pairwise,
        "STI_exact_common_support_subject_metrics.csv": common,
        "STI_exact_common_support_strain_models.csv": common_models,
        "STI_exact_common_support_group_comparisons.csv": common_groups,
        "STI_exact_common_support_method_difference_omnibus.csv": common_omni,
        "STI_exact_common_support_method_difference_pairwise.csv": common_pairwise,
        "STI_balanced_subsampling_iterations.csv": balanced_iterations,
        "STI_balanced_subsampling_summary.csv": balanced_summary,
        "STI_full_covariate_models.csv": full_cov,
        "STI_correlation_with_mean_RFF.csv": corr_mean,
    }
    for filename, frame in outputs.items():
        frame.to_csv(tables_dir / filename, index=False)

    make_figures(metrics, primary, balanced_iterations, figures_dir)
    print(f"Analysis complete: {out.resolve()}")

if __name__ == "__main__":
    main()
