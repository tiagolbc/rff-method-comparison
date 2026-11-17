# Method provenance and ROI adaptations

RFF Method Comparison v25 integrates four extraction implementations. The application uses common recordings and externally verified fricative boundaries, records each method's acceptance decisions, and exports conventional cycle-based RFF values.

## RFF-TC-ROI

AVHI_PRAAT_STRICT is the output identifier for RFF-TC-ROI, the ROI-guided Python/Praat-Parselmouth implementation developed by Tiago Cruz from his AVHI rff.py module. It selects pulse windows around the supplied boundaries and applies its period, outlier, and steady-state checks.

## cRFF

RFF_CEPSTRAL identifies the cepstral-assisted RFF implementation developed by Tiago Cruz. The active compute_cepstral_rff route reads the waveform, constructs multiresolution cepstral/autocorrelation candidates, links a Viterbi periodicity path, derives Hilbert analytic-phase landmarks, and calculates ten-cycle RFF from accepted periods. Its active extraction path does not call the native aRFF-AP bridge. Generic numerical utilities are shared within the application.

Cepstral evidence supports periodicity tracking and acceptance. The final RFF measure is the cycle-frequency ratio in semitones. The static function inventory and independent execution checks identify the cRFF computation used in the comparison.

## RFF-MB

The supplied original script is retained as rff_auto_mb_roi_bridge/RFF_auto_MB_original_unmodified.m. Its separate ROI bridge supplies FricStart for offset and FricEnd for onset in place of the original single FricLoc anchor. Recordings containing multiple transitions are isolated into adjacent segments. The original pulse source, sliding-window voting, rejection sequence and RFF equations are retained.

## aRFF-AP

Retained source files include main_RFF_original_auto_fricative.m, find_RFFcycles_aswipep_original_auto_fricative.m, RFFoutput.m, calcRFF.m and the source parameter MAT file.

Native aRFF-AP includes automatic fricative localization followed by human verification and correction. The separate ROI adapter supplies externally verified FricStart and FricEnd boundaries and adjacent vowel contexts. Auditory-SWIPE′ pitch estimation, cycle-candidate routines, rejection rules and final RFF calculation are retained.

## Numerical operations and source identification

The [numerical compatibility record](NUMERICAL_COMPATIBILITY_2026-11-16.md) specifies the helper call forms. The [original-source record](ORIGINAL_CODE_PROVENANCE.md) identifies the supplied source archives. NATIVE_METHOD_PRESERVATION_v25.json records hashes for the distributed source components; tests/original_source_baseline.json supplies independent original-archive baseline hashes.

The [compatibility tests](../tests/README.md) check numerical operators, original/adapted routines under matched inputs, and all four application dispatch routes on shared signals and ROIs. Acceptance and value agreement are distinct outputs of these checks.
