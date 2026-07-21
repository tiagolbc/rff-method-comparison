# RFF Method Comparison v25.0.0

This release compares four ROI-guided RFF pipelines on the same verified vowel–/f/–vowel transitions:

- RFF-TC-ROI (`AVHI_PRAAT_STRICT`)
- RFF-MB
- aRFF-AP
- cRFF

## New in v25

- Optional exploratory RFF spatiotemporal-index calculation
- Participant-level raw and bias-corrected STI
- 50-point STI profile exports
- Trace-level inclusion/exclusion audit
- STI sheets in the Excel workbook

The STI option is disabled by default and does not change conventional RFF extraction, pulse detection, cycle selection, rejection rules, or method validity.

## Reproducibility

Run:

```bash
python validate_v25_regression.py
```

The public package excludes participant audio, identifiable metadata, real ROI tables, and generated research outputs.
