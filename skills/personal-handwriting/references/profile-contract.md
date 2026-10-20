# Profile contract v1

The storage layout is `<store>/<safe-id>/profile.json` and `samples/<sha256>.<extension>`. IDs are lowercase letters/numbers with interior hyphens, at most 64 characters. Raw samples are copied locally and hashed; scripts do not infer stroke order or a complete glyph set from them.

`schema_version` is 1. `status` is `reference-only` in this implementation. `samples` record SHA-256, relative path, kind, optional paired transcript path/hash and import time. `preferences` contain:

| Field | Type/range | Meaning |
| --- | --- | --- |
| ink_color | #RRGGBB | Ink colour |
| font_size_pt | 8–32 | Nominal body size |
| line_spacing | 1.0–2.5 | Relative line spacing |
| slant_deg | -20–20 | Preferred slant |
| baseline_jitter_pt | 0–3 | Limit on baseline variation |
| glyph_variation | 0–1 | Preference for real glyph alternatives |
| spacing_variation | 0–0.3 | Relative spacing variation |
| seed | integer 0–2147483647 | Reproducibility |
| missing_glyph | error / annotated-fallback | Explicit missing-character handling |

These are saved user settings, not measured handwriting attributes. Rendering behaviour is a future engine contract. One-off render overrides should not be persisted without user intent. No field may silently replace unknown input characters with spaces.
