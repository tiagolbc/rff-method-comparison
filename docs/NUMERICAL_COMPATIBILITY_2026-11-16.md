# Numerical compatibility and ROI processing — 16 November 2026

This update aligns two numerical helpers with the documented MATLAB definitions used by the supplied third-party sources. The GUI entry point, ROI format, seven-judge analysis protocol, native rejection thresholds, and TC-ROI/cRFF computation are unchanged.

- AP `smooth(x,span)` now computes a centered moving average, reduces even spans to the next lower odd span, and uses symmetric shorter endpoint windows. The earlier helper used a moving median. The supported domain is finite uniformly indexed vectors; this is not the full Curve Fitting Toolbox API.
- MB `prctile(x,p)` now uses midpoint interpolation (type 5). The earlier helper used inclusive interpolation (type 7). The supported domain is the vector call used by the bridge.

Both helpers are independently implemented. No proprietary MathWorks implementation is redistributed. The moving-average helper was checked against independent direct-window means (63 vector/span cases). The percentile helper was compared with installed base-MATLAB R2026b `prctile`. Other AP finite-vector helper formulas were checked against autocorrelation and least-squares identities. These mathematical checks do not establish binary equivalence to optional toolboxes for all input domains.

The AP source parameter MAT file and native rejection thresholds remain those supplied with the original archive. Native source retention alone is insufficient to establish identical numerical behavior: dependency resolution and the external boundary protocol also matter. The ROI adapter uses separate consonant start/end anchors and adjacent vowel contexts, whereas the original workflow uses its own localization/verification inputs. Results must therefore be identified as ROI-adapted implementations.

Users comparing with results from preceding revisions should reprocess AP measurements and recalculate dependent statistics. In the controlled audit, changing only AP smoothing altered real-corpus acceptance and values. The MB percentile alignment changed no acceptance or RFF result across the 639 real transitions and 2,520 positive synthetic signals tested; this does not imply equivalence for every possible signal.

The study's synthetic source clocks define mathematical period targets, not physiological glottal-closure truth. Agreement, acceptance, and source-clock error are distinct outcomes. Full source hashes, execution logs and participant-level reanalysis are retained with the study materials; participant recordings and ratings are not distributed in this software repository.

Definitions: [MATLAB smooth](https://www.mathworks.com/help/curvefit/smooth.html), [MATLAB prctile](https://www.mathworks.com/help/matlab/ref/prctile.html).
