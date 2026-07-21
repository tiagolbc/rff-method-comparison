# GitHub release checklist

1. Confirm that no participant audio, identifiable metadata, real ROI tables, or generated output folders are included.
2. Review `README.md` and `THIRD_PARTY_NOTICES.md` to confirm that all required RFF-MB and aRFF-AP citations are visible.
3. Run `python validate_v25_regression.py`.
4. Optionally run `python audit_v25_output_consistency.py <output_folder>` on a completed local run.
5. Review `NATIVE_METHOD_PRESERVATION_v25.json`, `VALIDATION_REPORT_v25.txt`, and `SHA256SUMS.txt`.
6. Confirm the final repository name and update `repository-code` in `CITATION.cff` if necessary.
7. Create an empty public repository without adding a second README, `.gitignore`, or license.
8. Commit and push the GitHub-ready folder.
9. Create the tagged release `v25.0.0` using `RELEASE_NOTES_v25.0.0.md`.
10. Add the final repository and release URLs to the manuscript's Data and Code Availability section.
