# Method provenance and ROI adaptations

## RFF-TC-ROI

`AVHI_PRAAT_STRICT` is the stable internal output identifier for the method referred to publicly as **RFF-TC-ROI**. It is an ROI-guided Python/Praat-Parselmouth pipeline developed by Tiago Cruz. The internal identifier is retained to avoid breaking existing output parsers and regression comparisons.

## RFF-MB

The unmodified original file is retained as:

- `rff_auto_mb_roi_bridge/RFF_auto_MB_original_unmodified.m`

The ROI bridge is implemented separately. The original method accepted a single `FricLoc` location for both sides of the transition. The bridge supplies:

- `FricStart` to anchor voicing offset;
- `FricEnd` to anchor voicing onset.

The original pulse source, sliding-window voting, rejection sequence, and RFF equations are retained. Operational changes support portable paths, temporary-file handling, auditable batch input/output, and diagnostic plotting.

## aRFF-AP

Original or byte-preserved source copies are retained, including:

- `aRFF_AP_ROI_bridge/main_RFF_original_auto_fricative.m`
- `aRFF_AP_ROI_bridge/dependencies/find_RFFcycles_aswipep_original_auto_fricative.m`
- `aRFF_AP_ROI_bridge/dependencies/RFFoutput.m`
- `aRFF_AP_ROI_bridge/dependencies/calcRFF.m`

The separate ROI adapter replaces the original automatic fricative-localization result with externally verified `FricStart` and `FricEnd` boundaries. The native Auditory-SWIPE′ pitch estimation, cycle-candidate logic, rejection rules, and final RFF calculation remain authoritative.

## Public-package cleanup

The GitHub-ready archive excludes development audio, generated outputs, participant-linked quality-control tables, and historical internal audit notes. Their removal does not alter any extraction function.

## Verification

- `validate_v25_regression.py` verifies that the optional STI addition does not change v24-style extraction outputs when STI is disabled.
- `NATIVE_METHOD_PRESERVATION_v25.json` records SHA-256 hashes for retained native and adapter source files.
- `SHA256SUMS.txt` records hashes for the complete GitHub-ready package.
