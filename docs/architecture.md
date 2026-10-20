# Architecture

`profile.py` (standard library) manages local profiles, validated preferences, deduplicated sample copies and transcripts. `handwriting.py` handles A4 templates, computer vision, reviewed glyph libraries, layout, PDF/SVG output and validation. The Skill orchestrates these deterministic commands and inspects images.

Pipeline: template + paired manifest → user-filled scans → page marker detection/orientation/tag decode → perspective and illumination correction → labeled-cell connected-component extraction → draft library/contact sheets → visual review → active library → input coverage → deterministic glyph layout → PDF/SVG + provenance → raster and human inspection.

A template has four square-ring markers; one has a larger opening to determine orientation. Binary header tags encode a manifest identifier and page number. Labels/guides are outside the inner writing region or too light to survive the ink threshold. Extracted transparent PNGs preserve disconnected dots/components. Empty cells, tiny marks and border-touching strokes are rejected. These checks cannot recognize miswritten characters, so contact-sheet review is mandatory.

The renderer selects actual captured variants with a fixed PRNG seed. It scales text, digits and symbols consistently, applies restrained spacing/baseline/slant preferences, wraps and paginates, and positions structured subscripts/superscripts. Both SVG and PDF embed the same glyph bitmaps. No fallback computer font renders document content. Input letters are never inferred by a generative model.

Validation verifies exact character-to-glyph trace, content/PDF hashes, page count, bounds and visible pixels in each glyph region. It does not perform independent OCR and does not establish glyph identity, similarity, authentic authorship or mathematical correctness. The AI must still view every contact sheet/output page.

Python 3.10+, Pillow, NumPy, OpenCV headless, ReportLab and pypdfium2. OS font discovery is used only for template/contact labels and synthetic test fixtures. Pass `template --label-font` when no supported label font is installed. Personal samples and outputs never need a cloud service.

Version 1 deliberately uses isolated glyph capture. Freeform reference photos, natural ligatures, unsampled character inference and trajectory synthesis are separate research tracks. TypeScribe expects time-ordered pen strokes, so its existing priming API is not a direct static-photo style encoder. No upstream code/model is bundled.
