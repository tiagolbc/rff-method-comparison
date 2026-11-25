# Original source provenance

The retained third-party routines in RFF Method Comparison v25 are checked against the supplied source archives:

- rff_auto_mb-main.zip SHA-256: a3577f25222417ff919119f88c8a7ebefc94581886641216d019aeed43b2ae4e
- aRFF-AP_2024 FULL.zip SHA-256: abecdac68b03c8e0d860b79606a37fe4be4f0aae5b7512b7a89394d981533f49

tests/original_source_baseline.json contains fixed baseline hashes derived from these archives. Text line endings and UTF-8 BOMs are normalized for the source comparison; the AP parameter MAT file is checked byte for byte.

Original entry points are retained separately from the ROI adapters. The adapters supply external boundaries, coordinate batch input/output, and use the documented numerical helper call forms. [Method provenance](METHOD_PROVENANCE.md) describes these input conditions; the [compatibility tests](../tests/README.md) check the original and adapted routines with matched preparation and anchors.

NATIVE_METHOD_PRESERVATION_v25.json records the source hashes for the [evaluated snapshot](https://github.com/tiagolbc/rff-method-comparison/tree/ee19c521a2de43d84f8c59fb850aeb9c2bbff96a). [SHA256SUMS.txt](../SHA256SUMS.txt) inventories the Git-stored bytes in the current tree. Tests use the independent original-archive baseline to verify retention of the supplied routines.
