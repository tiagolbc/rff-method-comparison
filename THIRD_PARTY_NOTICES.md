# Third-party notices

This repository contains original integration code, ROI adapters, and third-party method files. The files retain their original authorship information and must be cited as described below.

## RFF-MB

The `rff_auto_mb_roi_bridge` directory contains the original Mark Berardi implementation and an ROI-controlled bridge. The original MIT license is preserved in `rff_auto_mb_roi_bridge/LICENSE`.

Required scholarly citation:

Berardi M, Tippit E, Gao Y, DeSouza GN, Dietrich M. Automated Analysis of Relative Fundamental Frequency in Continuous Speech: Development and Comparison of Three Processing Pipelines. *Journal of Voice*. 2025. doi:10.1016/j.jvoice.2025.04.006.

## aRFF-AP

The `aRFF_AP_ROI_bridge` directory contains source files attributed in their headers to Jennifer/Jenny Vojtech and the Stepp Lab, together with dependencies and separate ROI-adapter functions. Redistribution permission has been granted to the repository maintainer subject to the required scholarly citations.

For microphone signals:

Vojtech JM, Segina RK, Buckley DP, Kolin KR, Tardif MC, Noordzij JP, Stepp CE. Refining algorithmic estimation of relative fundamental frequency: Accounting for sample characteristics and fundamental frequency estimation method. *The Journal of the Acoustical Society of America*. 2019;146(5):3184–3202. doi:10.1121/1.5131025.

For accelerometer signals:

Groll MD, Vojtech JM, Hablani S, Mehta DD, Buckley DP, Noordzij JP, Stepp CE. Automated Relative Fundamental Frequency Algorithms for Use With Neck-Surface Accelerometer Signals. *Journal of Voice*. 2022;36(2):156–169. Published online 2020. doi:10.1016/j.jvoice.2020.06.001.

Foundational automated RFF estimation:

Lien Y-AS, Stepp CE. Automated estimation of relative fundamental frequency. In: *2013 35th Annual International Conference of the IEEE Engineering in Medicine and Biology Society (EMBC)*; Osaka, Japan. 2013:461–464. doi:10.1109/EMBC.2013.6609956. PMID:24110143.

## Bundled dependencies

The aRFF-AP package includes Auditory-SWIPE′ and auditory-filterbank dependencies whose authorship and references are retained in the corresponding source headers. Those notices remain applicable.

## Repository data policy

The public repository must not contain participant audio, identifiable metadata, ROI tables linked to participant identities, or generated outputs containing protected research data. The GitHub-ready package intentionally excludes development audio, participant-linked audit tables, and generated analysis folders.
