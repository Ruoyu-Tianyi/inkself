# Profile and document contract

Profile ID: 1–64 lowercase ASCII letters/digits, interior hyphens allowed. Storage `<store>/<id>/profile.json`, schema_version 1. Creation starts `reference-only`; reviewed usable library sets `glyph-ready`. Sample import alone never changes readiness.

Profile fields: id, name, timestamps, preferences, samples; optional draft_library and active_library point to separate immutable-version library folders. Source samples are copied and hashed. `library.json` stores each character's variants, PNG path/hash, ascent/descent, dimensions, source image hash/page/crop, extraction version and review status. Review activates the current draft after visual inspection. Re-extraction produces another draft, preserving the prior active library until review.

| Preference | Default | Allowed |
| --- | --- | --- |
| ink_color | #172E52 | #RRGGBB |
| font_size_pt | 13 | 8–32 |
| line_spacing | 1.5 | 1–2.5 |
| slant_deg | 0 | −20–20 |
| baseline_jitter_pt | 0.5 | 0–3 |
| glyph_variation | 0.3 | 0–1, frequency of choosing another captured variant |
| spacing_variation | 0.05 | 0–0.3 |
| seed | 1 | integer 0–2147483647 |
| missing_glyph | error | renderer only implements error |

The profile manager also recognizes reserved `annotated-fallback`; the renderer explicitly rejects it. No silent replacement font. Preferences are user tuning, not inferred physical handwriting statistics. Existing variant outlines are retained; ink color is normalized to the saved color.

Input `.txt`: UTF-8, CRLF normalized, tabs become four spaces. Or `.json`:

```json
{"blocks":[{"type":"paragraph","runs":[{"text":"C"},{"text":"1","subscript":true},{"text":" = 10; x"},{"text":"2","superscript":true},{"text":" = 4."}]}]}
```

Each block has type heading/paragraph and text or runs. A run has text and optional subscript/superscript boolean (not both true). Whitespace is laid out, all other characters require reviewed glyphs. No Markdown, LaTeX or DOCX parser. Limits: input 2 MB/120,000 characters/10,000 blocks; scans 60 million pixels per image/90 million total; manifests up to 128 pages. Realistic print/scan conditions are required; severe blur or curved pages can fail.

PDF report schema_version 1 includes exact normalized content, content and PDF SHA-256, preferences snapshot, active library ID, source glyph mapping, page geometry and output paths. It contains private document text. Validation tests mapping and rendered ink, not semantic glyph identity or similarity. Reports and manifests are local trusted metadata, not cryptographically signed evidence.
