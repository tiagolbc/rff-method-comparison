# Original source provenance

The retained third-party routines in RFF Method Comparison v25 are checked against the supplied source archives:

- rff_auto_mb-main.zip SHA-256: a3577f25222417ff919119f88c8a7ebefc94581886641216d019aeed43b2ae4e
- aRFF-AP_2024 FULL.zip SHA-256: abecdac68b03c8e0d860b79606a37fe4be4f0aae5b7512b7a89394d981533f49

tests/original_source_baseline.json contains fixed baseline hashes derived from these archives. Text line endings and UTF-8 BOMs are normalized for the source comparison; the AP parameter MAT file is checked byte for byte.

Original entry points are retained separately from the ROI adapters. The adapters supply external boundaries, coordinate batch input/output, and use the documented numerical helper call forms. [Method provenance](METHOD_PROVENANCE.md) describes these input conditions; the [compatibility tests](../tests/README.md) check the original and adapted routines with matched preparation and anchors.

NATIVE_METHOD_PRESERVATION_v25.json records the actual distributed source hashes. The independent original-source baseline and the current-file inventory answer separate questions: retention of supplied routines and identification of the implementation used for computation.
