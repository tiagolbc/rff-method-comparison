# Original-code provenance — v16

Authoritative source archives supplied by the user:

- `rff_auto_mb-main.zip` SHA-256: `A3577F25222417FF919119F88C8A7EBEFC94581886641216D019AEED43B2AE4E`
- `aRFF-AP_2024 FULL.zip` SHA-256: `ABECDAC68B03C8E0D860B79606A37FE4BE4F0AAE5B7512B7A89394D981533F49`

Verified unmodified active/original copies:

- AP `RFFoutput.m`: `56EBB34C2630183FF50C17269BC91A8F86204C0FA6BEAE4FF6070EA665E2ABC7`
- AP `calcRFF.m`: `1F65A8A38D9120EEA833EB1BD24B9D382B6A1797DB55FC00F93BC0B42124FB50`
- AP `find_RFFcycles_aswipep.m`: `C9CD5B34BF1EC929804DD9A2CBB166EA275AE5D0E521B73186DE179496729F6B`
- MB `RFF_auto_MB_original_unmodified.m`: `1DB33103F720387DA1953FDCD238BAE78828BC70805A5DDCFDA86C8D45AF7BB9`
- MB `get_pulses_slide_original.m`: `596E13261D9A0545285F5B5DC6364D5232F75B5F3192510CCEFB4706ABC8F652`

The active adapters are separate files. Original files above were not edited.

The AP native cycle adapter differs from the original cycle finder only in its function name, portable `fullfile` paths, and the substitution of `FricStart`/`FricEnd` for the original single automatically detected `pk_loc` anchor.

The MB native sliding helper is a copy of the original with only its function name and pulse-I/O function calls changed. Pulse I/O writes temporary text files for Windows reliability but performs the original Praat signal operations.

