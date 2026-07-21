# Contributing

Contributions that improve reproducibility, portability, documentation, validation, or clearly separated experimental features are welcome.

Before opening a pull request:

1. Do not add participant audio, identifiable metadata, real ROI tables, or protected outputs.
2. Preserve the public/internal method-label mapping described in the README.
3. Do not silently alter native RFF-MB or aRFF-AP calculations.
4. Document every change to pulse detection, cycle selection, rejection, fallback, normalization, or STI calculation.
5. Run:

```bash
python validate_v25_regression.py
```

6. Add or update a regression test for numerical changes.
7. Update `CHANGELOG.md`.

Bug reports should include the operating system, Python version, MATLAB version when relevant, exact error text, and a minimal nonidentifiable example whenever possible.
