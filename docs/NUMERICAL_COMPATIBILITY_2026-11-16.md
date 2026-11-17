# Numerical compatibility and ROI processing

This record describes the numerical helpers and input protocol used by RFF Method Comparison v25.

- AP smooth(x,span) computes a centered moving average, reduces even spans to the next lower odd span, and uses symmetric shorter endpoint windows. Its supported domain is finite uniformly indexed vectors.
- MB prctile(x,p) uses midpoint interpolation (type 5) for the vector call used by the bridge.

Both helpers are independently implemented. No proprietary MathWorks implementation is redistributed. The moving-average helper was checked against independent direct-window means in 63 vector/span cases. The percentile helper was compared with installed base-MATLAB R2026b prctile. Other AP finite-vector helper formulas were checked against autocorrelation and least-squares identities. The test documentation identifies the supported call forms and explicitly records optional native-toolbox comparisons as skipped when unavailable.

The AP parameter MAT file and native rejection thresholds are retained from the supplied source. The ROI adapter uses externally supplied consonant start/end anchors and adjacent vowel contexts. MB uses separate side anchors and isolates transitions where required. Matched-input comparisons test the original and adapted routines under coincident preparation and anchors; the common-ROI comparison evaluates the input protocol actually used in the study.

## Shared-input comparisons

The real-corpus comparison applies all four methods to 639 transitions using the same recordings and verified ROIs. The synthetic comparison uses 2,520 positive signals with prescribed source events and periods. It reports availability, accepted RFF values, and temporal displacement of selected cycle windows. The numerical reference is the source-period sequence saved before acoustic filtering. Temporal displacement includes waveform phase, filtering and window selection.

Signals accepted by all four methods are compared separately from each method's available set. Thus, changes in the accepted denominator can be distinguished from differences in the values returned for the same signal. Participant recordings and ratings are retained with the research materials and are not distributed in this software repository.

Definitions: [MATLAB smooth](https://www.mathworks.com/help/curvefit/smooth.html), [MATLAB prctile](https://www.mathworks.com/help/matlab/ref/prctile.html).
