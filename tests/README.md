# Original-source and ROI compatibility tests

These tests check source retention, numerical operators, and matched-input routine behavior. They identify the preparation and anchors used in each comparison and distinguish that setup from the application’s external-ROI workflow.

## 1. Original-source retention

From the repository root:

```text
python -m unittest discover -s tests -v
```

The fixed baseline hashes come from the supplied original AP and MB archives, not from the files currently under test. Text line endings and a UTF-8 BOM are normalized; the AP parameter MAT file is compared byte for byte. Separate ROI adapters are required to exist alongside the retained originals.

## 2. Numerical compatibility in MATLAB

```matlab
addpath(fullfile(repoRoot,'tests'));
validate_numerical_compatibility(repoRoot);
check_optional_native_helpers(repoRoot,fullfile(tempdir,'RFF_optional_native_helpers.json'));
```

The mandatory test compares the AP moving average with independent direct means (including even spans and endpoint behavior), the MB percentiles with installed base-MATLAB `prctile`, and finite-vector AP correlation/shape formulas with independent mathematical identities. The optional test compares installed Curve Fitting, Econometrics, and Statistics toolbox functions directly. Unavailable native functions are explicitly **SKIPPED**, never counted as passes. The restricted helpers do not implement the full optional-toolbox APIs, NaN smoothing, or arbitrary multidimensional call forms.

## 3. Execute original and adapted routines

Extract the authors' original archives into separate folders; supply their paths explicitly. Generate deterministic engineering fixtures (130 and 240 Hz; no participant audio):

```text
python tests/generate_compatibility_fixtures.py C:/RFFCompatibility/fixtures
```

Use a new writable scratch directory for each invocation:

```matlab
compare_ap_cycle_core(repoRoot,manifestPath,apOutputDir,originalAP);
compare_mb_original(repoRoot,manifestPath,praatExe,mbOutputDir,originalMB);
```

AP first runs the actual production bridge. It then compares the supplied original cycle routine with the ROI cycle routine using identical prepared parameters and coincident anchors, asserting identical peak/trough landmarks and RFF arrays. This isolates cycle-core compatibility; it does not assert equality between automatic fricative localization and separate external consonant edges.

MB executes the supplied original script on the same whole-file PCM16 fixtures used by the bridge, with a common `FricLoc` center. It compares native acceptance, all 11 landmarks and all ten RFF values. On Windows, a scratch batch wrapper supplies synchronous UTF-8 Praat output; the original source is not edited. Each original invocation processes one file, avoiding the supplied script's clearing of its loop-display bookkeeping variable. The bridge's real external-edge/cropping workflow is a separate protocol.

The low deterministic fixture noise floor avoids the original AP conditioning's undefined spectral ratio on perfectly silent stretches. These are deterministic engineering fixtures for comparing numerical behavior under coincident preparation and anchors. Corpus-level controlled experiments and their aggregate results are described in the dated numerical compatibility record; private recordings and ratings are not included here.

## 4. Exercise all four application routes together

```text
python tests/run_four_method_fixture.py --matlab MATLAB_EXECUTABLE --praat PRAAT_EXECUTABLE --out NEW_SCRATCH_FOLDER
```

This calls the same Python TC/cRFF entry points and MATLAB MB/AP dispatch functions used by the application on identical signals and ROIs. Native rejection is a valid return; accepted-side normalization is checked only where accepted. The executed receipt explicitly records that AP rejected both simple integration fixtures, rather than silently substituting favorable examples. Accepted AP cycle-core calculations are checked in the matched-input original-source layer. The dated receipt records all outcomes and explicit native-toolbox skips.
