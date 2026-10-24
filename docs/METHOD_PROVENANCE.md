# Method provenance and ROI adaptations

## RFF-TC-ROI

`AVHI_PRAAT_STRICT` is the stable internal output identifier for the method referred to publicly as **RFF-TC-ROI**. It is an ROI-guided Python/Praat-Parselmouth implementation developed by Tiago Cruz from his own AVHI rff.py module. The internal identifier is retained to avoid breaking existing output parsers and regression comparisons.

## cRFF

`RFF_CEPSTRAL` identifies the cepstral-assisted classical RFF implementation developed independently by Tiago Cruz. The active `compute_cepstral_rff` route reads the waveform, constructs multiresolution cepstral/autocorrelation candidates, links a Viterbi periodicity path, derives Hilbert analytic-phase landmarks, and calculates ten-cycle RFF from accepted periods. It does not obtain its RFF values through the native aRFF-AP bridge or the retained legacy Python AP approximation. Generic numerical helpers are shared within the application.

Cepstral evidence supports periodicity tracking and acceptance. The final measure uses the classical cycle-frequency ratio in semitones; it does not append CPPS as a classifier feature. Legacy AP approximation helpers remain in the source for development comparison and are distinct from both the active cRFF route and native MATLAB aRFF-AP. These descriptions document implementation, without claiming physiological validation or historical priority.

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

Native aRFF-AP already includes automatic fricative localization followed by human verification and correction. The separate ROI adapter replaces that localization result with externally verified `FricStart` and `FricEnd` boundaries. The native Auditory-SWIPE′ pitch estimation, cycle-candidate logic, rejection rules, and final RFF calculation remain authoritative.

External boundaries change the operating inputs of the adapted methods. Technical availability describes whether an implementation returns an accepted result under its own rules; it does not establish accuracy or performance in the native localization workflow.

## Public-package cleanup

The GitHub-ready archive excludes development audio, generated outputs, participant-linked quality-control tables, and historical internal audit notes. Their removal does not alter any extraction function.

## Verification

- `validate_v25_regression.py` verifies that the optional STI addition does not change v24-style extraction outputs when STI is disabled.
- `NATIVE_METHOD_PRESERVATION_v25.json` records SHA-256 hashes for retained native and adapter source files.
- `SHA256SUMS.txt` records hashes for the complete GitHub-ready package.
