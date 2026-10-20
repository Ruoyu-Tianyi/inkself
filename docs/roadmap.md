# Release 1.0 acceptance

Implemented: profile/sample/preference management; printable labeled templates; image/PDF correction and extraction; versioned drafts, contact sheets and explicit review; coverage gate; deterministic personal-glyph PDF/SVG with sub/superscripts; provenance and visible-ink validation; self-contained AI Skill, dependency list, packaging tool and examples.

Local automated acceptance: 18 unittest cases pass on Windows, Python 3.12.14 bundled runtime. They cover profile validation, sample deduplication, no side effects for invalid transcripts, extraction with full default character set, ring-shaped-letter localization regression, blank/missing cells, wrong manifests, 90-degree orientation with perspective/shadow, review gating, absent glyphs, deterministic output, temporary preferences, tamper detection, multipage layout invalid document structures, extreme slant wrapping and preventing preview from bypassing review.

A complete default three-page computer-filled synthetic sheet was extracted, reviewed as a known fixture, rendered to a one-page English/numeric/math document and raster-validated. The demo output and all three blank template pages were visually inspected. This confirms the controlled workflow, not real handwriting similarity. CI declares Linux/Python 3.10 and 3.12; remote results must be checked separately before claiming that matrix passed.

Real-owner acceptance remains data-dependent: have the owner fill the sampling sheets naturally, capture every page, inspect all extracted glyph contact sheets, compare an unfamiliar generated passage with a genuinely handwritten passage, then tune preferences and save the accepted profile. Do not claim this step passed without those samples.

Future experiments (outside 1.0): freeform word alignment, captured ligatures, contextual joining and a static-image-conditioned generative adapter. Any generative route must still preserve document text/numbers and pass visible review before adoption. No promise of exact reconstruction from an arbitrary short photo.
