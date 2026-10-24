# RFF Method Comparison v25

A reproducible desktop application for processing the same manually verified vowel–/f/–vowel regions of interest (ROIs) with four relative fundamental frequency (RFF) pipelines. Version 25 preserves the v24 extraction logic and adds an optional exploratory spatiotemporal-index (STI) calculation.

## Methods included

| Public manuscript label | Internal output code | Description |
|---|---|---|
| **RFF-TC-ROI** | `AVHI_PRAAT_STRICT` | ROI-guided Praat/Parselmouth pulse extraction developed by Tiago Cruz from his own AVHI rff.py module, with transition, steady-state, outlier, and rejection rules. |
| **RFF-MB** | `RFF_MB_ROI_MATLAB` | Mark Berardi's MATLAB/Praat RFF pipeline adapted to use the verified ROI boundaries. |
| **aRFF-AP** | `RFF_AP_ROI_MATLAB` | The Vojtech/Stepp Lab automated RFF pipeline adapted to use the verified ROI boundaries. |
| **cRFF** | `RFF_CEPSTRAL` | Cepstral-assisted classical 10-cycle RFF independently implemented by Tiago Cruz in Python, using cepstral/autocorrelation tracking and analytic-phase cycle landmarks. |

The internal code `AVHI_PRAAT_STRICT` is retained for backward compatibility; publications and public-facing documentation may refer to it as **RFF-TC-ROI**.

## What was preserved in the third-party methods

Unmodified copies of the original RFF-MB and aRFF-AP source files are retained alongside separate ROI adapters. Native aRFF-AP already includes automatic fricative localization followed by human verification and correction; supplying external boundaries controls localization inputs. These adapters change the input conditions, so technical availability under an external ROI is not a measure of native-configuration accuracy.

- **aRFF-AP:** the original automatic fricative-localization step was replaced by externally supplied `FricStart` and `FricEnd` boundaries. The native Auditory-SWIPE′ pitch estimation, cycle extraction, rejection logic, and RFF calculation were retained.
- **RFF-MB:** the original single `FricLoc` anchor was replaced by `FricStart` for offset and `FricEnd` for onset. The native Praat pulse extraction, 10-ms sliding-window voting, rejection sequence, and RFF equations were retained.
- Additional bridge changes are limited to portable paths, file input/output, temporary-file handling, audit exports, and diagnostic plots.

See [`docs/METHOD_PROVENANCE.md`](docs/METHOD_PROVENANCE.md), [`ORIGINAL_CODE_PROVENANCE_v16.md`](ORIGINAL_CODE_PROVENANCE_v16.md), and [`NATIVE_METHOD_PRESERVATION_v25.json`](NATIVE_METHOD_PRESERVATION_v25.json).

## Optional STI calculation

The GUI includes:

> **Calculate RFF spatiotemporal index (STI; exploratory)**

When selected, STI is calculated separately for offset and onset for each participant and method from complete valid 10-cycle trajectories. At least two trajectories are required. The option does not alter pulse detection, cycle selection, conventional RFF values, rejection rules, or method validity.

STI output files:

- `rff_sti_subject_method_side.csv`
- `rff_sti_method_summary.csv`
- `rff_sti_profiles_long.csv`
- `rff_sti_trace_audit.csv`
- corresponding sheets in `rff_method_comparison_outputs.xlsx`

STI is an exploratory trajectory-variability measure. It is not a diagnosis of vocal hyperfunction and does not replace OFF10, ON1, auditory-perceptual assessment, or physiological evaluation.

## Requirements

- Windows 10/11 recommended
- Python 3.10 or newer
- MATLAB for RFF-MB and aRFF-AP
- Praat and `praat-parselmouth` for Praat-based processing

The current package was tested with MATLAB R2026a. The Python-only methods can be used without MATLAB.

## Installation

### Windows quick setup

Double-click:

```text
setup_windows.bat
```

Then run:

```text
run_rff_v25.bat
```

### Manual setup

```bash
python -m venv .venv
```

Activate the environment:

```bat
.venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the application:

```bash
python avhi_rff_method_comparison_gui_MATLAB_BRIDGE_v25_OPTIONAL_STI.py
```

## Input organization

The application scans a corpus folder recursively for audio filenames containing `afa`, `ifi`, or `ufu`. ROIs can be marked in the GUI or imported from `fricative_locations_*.csv` / `.xlsx` files.

A minimal ROI table is provided at [`examples/fricative_locations_template.csv`](examples/fricative_locations_template.csv). Common accepted columns include:

- `Subject`
- `Filename`
- `Token`
- `Rep`
- `FricStart`
- `FricEnd`

Times should normally be expressed in seconds. Participant metadata are optional; a template is provided in [`participant_metadata_template.csv`](participant_metadata_template.csv).

## Main outputs

The output folder may contain:

- ROI tables and autosave backups
- cycle-level and trace-level RFF tables
- participant-by-method summaries
- method availability and validation summaries
- exclusion and manual-review logs
- MATLAB bridge manifests
- optional debug plots
- optional STI tables
- an Excel workbook containing the principal output sheets
- a run manifest and configuration file

Do not publish participant audio, identifiable metadata, ROI tables linked to identities, or analysis outputs containing protected research data.

## Validation

Run the frozen regression checks:

```bash
python validate_v25_regression.py
```

Audit a completed output folder:

```bash
python audit_v25_output_consistency.py PATH_TO_OUTPUT_FOLDER
```

The GitHub Actions workflow in `.github/workflows/validate.yml` repeats the Python regression check after every push and pull request.

## How to cite

### This software

Use the citation generated by GitHub from [`CITATION.cff`](CITATION.cff). Update the repository URL in that file after the public repository is created.

### RFF-MB

Berardi M, Tippit E, Gao Y, DeSouza GN, Dietrich M. Automated Analysis of Relative Fundamental Frequency in Continuous Speech: Development and Comparison of Three Processing Pipelines. *Journal of Voice*. 2025. doi:10.1016/j.jvoice.2025.04.006.

The original RFF-MB repository is maintained by Mark Berardi (`mark-berardi/rff_auto_mb`). Its MIT license is retained in [`rff_auto_mb_roi_bridge/LICENSE`](rff_auto_mb_roi_bridge/LICENSE).

### aRFF-AP and related automated RFF methods

For microphone-signal processing, cite:

Vojtech JM, Segina RK, Buckley DP, Kolin KR, Tardif MC, Noordzij JP, Stepp CE. Refining algorithmic estimation of relative fundamental frequency: Accounting for sample characteristics and fundamental frequency estimation method. *The Journal of the Acoustical Society of America*. 2019;146(5):3184–3202. doi:10.1121/1.5131025.

For accelerometer-signal processing, cite:

Groll MD, Vojtech JM, Hablani S, Mehta DD, Buckley DP, Noordzij JP, Stepp CE. Automated Relative Fundamental Frequency Algorithms for Use With Neck-Surface Accelerometer Signals. *Journal of Voice*. 2022;36(2):156–169. Published online 2020. doi:10.1016/j.jvoice.2020.06.001.

Foundational automated RFF estimation:

Lien Y-AS, Stepp CE. Automated estimation of relative fundamental frequency. In: *2013 35th Annual International Conference of the IEEE Engineering in Medicine and Biology Society (EMBC)*; Osaka, Japan. 2013:461–464. doi:10.1109/EMBC.2013.6609956. PMID:24110143.

### Spatiotemporal index

Vojtech J, Toles LE, Buckley DP, Stepp CE. Capturing the Intraspeaker Heterogeneity of Vocal Hyperfunction Using Spatiotemporal Indices of Relative Fundamental Frequency. *Journal of Speech, Language, and Hearing Research*. 2025;68(9):4220–4235. doi:10.1044/2025_JSLHR-25-00138.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and redistribution information.

## Development transparency

OpenAI ChatGPT assisted with portions of code drafting, debugging, documentation, and implementation of prespecified statistical and validation procedures. All AI-assisted code and text were reviewed, executed, tested, and revised by the authors. Artificial intelligence was not used to generate or alter participant data or to make autonomous scientific decisions. See [`AI_ASSISTANCE.md`](AI_ASSISTANCE.md).

## Repository scope and licensing

This repository contains code with mixed provenance. The RFF-MB subdirectory retains its original MIT license. The aRFF-AP files are included with permission and require the scholarly citations listed above. No repository-wide license is implied by the presence of a third-party license in a subdirectory. Consult [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) before reuse or redistribution.

## Version

Current release: **v25.0.0**
