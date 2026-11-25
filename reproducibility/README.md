# Study reproducibility

The study evaluated RFF Method Comparison v25 at [commit ee19c521a2de](https://github.com/tiagolbc/rff-method-comparison/tree/ee19c521a2de43d84f8c59fb850aeb9c2bbff96a). Use that snapshot for extraction and this directory for the study analysis scripts. The repository contains no participant recordings, participant-level acoustic or perceptual data, or real-corpus ROI manifests. Run the analysis commands in a separate working directory with the authorized local inputs.

The reproducibility checks used Python 3.12 with NumPy 2.5.5, SciPy 1.18.1, pandas 3.0.1, SoundFile 0.14.0, statsmodels 0.15.0, Matplotlib 3.11.2, and Parselmouth 0.4.7. The two MATLAB extraction routes were checked with MATLAB R2026b Update 1. Install the [application dependencies](../requirements.txt) and statsmodels in the analysis environment.

## Regenerate the synthetic benchmark

```text
python reproducibility/generate_synthetic.py work/synthetic
```

The destination must be a new directory. The [stimulus protocol](synthetic_protocol.json) gives the factorial grid and seeds. The generator writes 2,520 voiced stimuli, 24 target-absent controls, ROI manifests, 50,400 canonical source cycles, and the complete source-event sequences. The positive waveforms are in 'audio' and the controls are in 'negative_controls'. The two formant profiles are acoustic model settings.

Use the generated waveform paths and the same FricStart and FricEnd values for all four extraction implementations. [Extraction settings](extraction_settings.json) record the numerical and logical settings from the study run. Use local executable paths for Praat and MATLAB. The [four-route fixture](../tests/run_four_method_fixture.py) shows the Python entry points and MATLAB batch dispatch used by the application.

Use the consolidated application exports to score all positive signals.

```text
python reproducibility/score_synthetic.py work/synthetic/manifest.csv work/synthetic/truth/canonical_cycles.csv work/exports/rff_all_traces_wide.csv work/exports/rff_final_landmarks_long.csv work/synthetic/endpoint_results.csv
```

The synthetic stimulus ID must be the Subject in both exports. Supply one wide row per stimulus and method, with OffValid and OnValid indicating availability after an attempted extraction. Preserve execution failures and rejections as unavailable cases in the run records. The landmark table supplies 11 ordered Time_s values per accepted side. The scorer uses the prescribed source periods and reports the accepted estimates, errors, supported frequency range, and selected-window displacement. The controls have no source-period endpoint and are summarized by accepted-side counts.

## Reproduce the statistical analyses

Create a working directory with the following structure. File names match the analytical CSV exports used by the scripts.

```text
work/analysis/
  inputs/
    RFF_transition_level_v24.csv
    RFF_cycle_level_v24.csv
    ratings_all_originals_and_retests.csv
    judge02_alternate_ratings.csv
    symmetric_vote/
      Normal Group/
      Altered Group/
  transition_acoustic_properties.csv
  reprocessed_real/
    fresh_landmarks.csv
```

The transition and cycle tables are the finalized four-method extraction tables with analytical covariates, one transition per Subject/Token/Rep/Method and one cycle per side and cycle index. The transition input includes Method and MethodCode. The two rating CSVs use Subject, Session (Original or Retest), Overall, Roughness, Breathiness, Strain, and Instability. The combined file also includes Judge (Judge 01 through Judge 07). The alternate file supplies Judge 02’s separate session for the session sensitivity. Subjects must use a consistent key across files.

In each CPPS group directory under 'symmetric_vote', the four subdirectories are 'python_on050_fallback', 'python_on050_no_fallback', 'mb_on050_fallback', and 'mb_on050_no_fallback'. Use 'rff_all_traces_wide.csv' in the Python directories and 'rff_mb_roi_results_wide.csv' in the MB directories. These are the symmetric-onset sensitivity outputs. The acoustic-properties CSV contains the independent per-side CPPS and normalized autocorrelation estimates keyed by transition. The landmark CSV contains the final landmarks from the four methods.

Run from the repository root. Outputs are written to the local working directory. Some outputs are at participant or transition level.

```text
python reproducibility/analyze.py work/analysis
python reproducibility/refresh_descriptives.py work/analysis
python reproducibility/r07_sensitivities.py work/analysis
python reproducibility/additional_statistics.py work/analysis
python reproducibility/clarify_cpps_fdr.py work/analysis
python reproducibility/matched_comparisons.py work/analysis/inputs/RFF_transition_level_v24.csv work/synthetic/endpoint_results.csv work/synthetic/manifest.csv work/analysis/additional_comparisons
python reproducibility/analyze_sti.py work/analysis/inputs/RFF_cycle_level_v24.csv --out work/analysis/STI_reproduction
python reproducibility/supplementary_tables.py work/analysis work/analysis/supplementary
```

These commands reproduce measurement availability, rating reliability, strain and availability models, propensity weights, agreement on available and common transitions, matching and error tests, and the exploratory sensitivity and STI tables. The all-pairs agreement file includes the absolute ON1 difference counts shown in the Table S4 note.

## Pulse voting and fallback Table S14

[Table S14 aggregate counts](table_s14.csv) are included. 'Voted' and 'Fallback' identify candidate routes. 'Other' corresponds to the table’s Neither column. Acceptance also requires passing the downstream quality checks.

Create temporary instrumented copies of the evaluated routines and replay TC-ROI with the local 639-transition manifest.

```text
python reproducibility/vote_audit.py prepare ../rff-study-source work/vote
python reproducibility/vote_audit.py trace-tc work/vote local/real_manifest.csv reproducibility/extraction_settings.json work/tc_vote.csv
```

The real manifest must contain Filepath, Subject, Token, Rep, FricStart, and FricEnd. Use the study MB manifests with the same waveform excerpts, including MBAnalysisStart and MBAnalysisEnd where the transition is isolated from a recording. In MATLAB, add the temporary bridge to the path and run one call for each study manifest using distinct output directories.

```matlab
addpath('work/vote/rff_auto_mb_roi_bridge');
RFF_auto_MB_ROI_bridge('local/mb_manifest.csv', 'work/mb_batch', 'C:/Praat/Praat.exe', 'SaveXlsx', false);
```

Pass all resulting MB batch directories to the summarizer.

```text
python reproducibility/vote_audit.py summarize work/tc_vote.csv work/table_s14.csv work/mb_batch
```

Compare the acceptance flags and accepted RFF values with the corresponding uninstrumented outputs before interpreting branch counts. The script adds instrumentation to scratch copies. The published numerical extraction routines remain the reference for the study.
