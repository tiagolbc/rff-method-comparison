# aRFF-AP ROI bridge

This folder retains the supplied aRFF-AP source files and dependencies together with separate ROI-adapter functions. The adapter replaces automatic fricative localization with externally verified `FricStart` and `FricEnd` boundaries and uses native pitch estimation, cycle selection, cycle-level rejection, and RFF calculation. Vowel-probability screening controls the samples pooled for pitch and pitch-strength estimates. It does not remove supplied ROI pairs from the candidate list.

Required citations are listed in the repository root `README.md` and `THIRD_PARTY_NOTICES.md`.
