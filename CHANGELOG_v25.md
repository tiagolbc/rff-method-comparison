# Changelog — v25 Optional STI

## RFF numerical methods

- No changes to RFF-TC-ROI (`AVHI_PRAAT_STRICT`), RFF-MB, aRFF-AP, cRFF, cTFI, validity rules, quality-control thresholds, or PASS/REVIEW/FAIL classification.
- Native MATLAB source and ROI-adapter files are unchanged from the supplied v25 package.
- The v24 GUI corpus-reset and output-protection behavior is preserved.

## New optional post-processing

- Added a GUI checkbox to calculate RFF spatiotemporal indices.
- STI is calculated independently for each participant, method, and side from complete valid repeated 10-cycle trajectories.
- Added raw and gamma-bias-corrected STI, trace counts, OFF10/ON1 mean and SD, 50-point profiles, and a trace audit.
- Added STI CSV outputs and Excel workbook sheets only when the checkbox is selected.
- Added STI settings and status to the saved configuration and run manifest.

## GitHub-ready public package

- Added complete citations for RFF-MB, aRFF-AP microphone and accelerometer methods, foundational automated RFF estimation, and STI.
- Added third-party notices, AI-assistance disclosure, `CITATION.cff`, contribution guidance, Windows launchers, GitHub Actions validation, and publication instructions.
- Removed development audio, generated outputs, participant-linked audit tables, and internal historical audit notes.

## Validation

- Added synthetic STI regression tests.
- Verified that the integrated STI implementation reproduces the independent v24 cycle-level analysis to numerical precision.
- Verified that all retained native MB and aRFF-AP source files are byte-identical to the supplied v25 package.
