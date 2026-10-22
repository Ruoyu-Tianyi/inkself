# Inkself auxiliary glyph workflow

This is the independent character-sampling utility, not the web app's few-shot generation workflow. For the main product, see [the web guide](https://github.com/Ruoyu-Tianyi/inkself/blob/main/docs/web-guide.md).

Run scripts relative to this engine directory. Requires Python 3.10+ and `python -m pip install -r requirements.txt`. Read [profile contract](references/profile-contract.md) for schemas and preference ranges. Use a store outside the engine directory, normally `<working-directory>/.local/profiles`.

## Capture a profile

1. Create a profile and sampling PDF. Default: three A4 pages with uppercase/lowercase English, digits, punctuation and math symbols; three variants each.

```sh
python scripts/profile.py --store <store> create <id> --name "<name>"
python scripts/handwriting.py template --output <sampling.pdf>
```

2. Give the PDF and adjacent `.json` to the user. Ask them to print at actual size, write each labeled character naturally in each of its three boxes in dark ink, leave the gray guides and corner markers visible, keep strokes inside boxes, and scan/photograph every whole page. Do not imitate a font while sampling. Keep the matching manifest. English samples do not imply Chinese coverage.
3. Extract the supplied scans (PNG/JPEG or PDF). The program corrects rotation and moderate perspective, decodes page IDs, archives source images, and emits a **draft**, contact sheets and rejection/coverage reports. Wrong pages, missing markers or unsupported scans fail explicitly.

```sh
python scripts/handwriting.py --store <store> extract <id> --manifest <sampling.json> --pages <page1.png> <page2.png> <page3.png>
python scripts/handwriting.py --store <store> review <id>
```

4. Open **every** returned contact sheet. Check labels against visible glyph identity, dots, punctuation and digits, crop completeness and stray marks. Request corrected samples for bad glyphs. Only after actual inspection, run `review <id> --accept` to activate the draft. This is an inspection attestation, an assertion that the glyphs were actually inspected. Never accept an unseen library. Missing characters may remain, but rendering text using them will fail.
5. Archive arbitrary freeform images only as references using `profile.py add-sample <id> --file <image> --kind freeform [--transcript <utf8.txt>]`. Do not label them trained/usable glyphs. No neural model training is performed.

## Generate a document

Use UTF-8 `.txt`, or structured JSON with `blocks` of `heading`/`paragraph`, each containing `text` or `runs`. Runs support `text` and one of `subscript: true` / `superscript: true`. Preserve requested numbers, signs and content exactly. Convert unsupported document formats to this explicit content first; no automatic DOCX/LaTeX parsing is provided.

```sh
python scripts/handwriting.py --store <store> coverage <id> --input <document.json>
python scripts/handwriting.py --store <store> render <id> --input <document.json> --output <result.pdf> --seed 42
python scripts/handwriting.py validate --report <result.report.json> --render-dir <inspection-directory>
```

Coverage must pass. No silent generic-font substitution. Letters, digits and symbols use the same reviewed library. Outputs include PDF, one embedded-image SVG per page and a provenance/content report. Existing output files are not overwritten. For an unfamiliar style, render a short separate input with `--preview`; inspect it before the full export. `--preview` marks the report and does not truncate input.

Open every rendered page image. Check clipping, overlap, numeric ambiguity, subscripts and page breaks against the requested content. Automated checks verify hashes, glyph mapping, page bounds and visible ink, **not OCR identity, personal similarity or correctness of user labels**. Report these limits accurately. Fix errors and repeat affected checks before delivery.

## Save preferences

```sh
python scripts/profile.py --store <store> update <id> --preferences <preferences.json>
python scripts/profile.py --store <store> show <id>
python scripts/profile.py --store <store> list
```

Use `render --preferences <json>` for temporary overrides; it does not update the saved profile. Prefer small variations that retain coherent proportions across text and digits. Changing variation is layout tuning, not learning handwriting. Missing glyph policy must be `error`; annotated fallback is reserved and not implemented.

## Privacy and scope

Keep samples, transcripts, glyph libraries and document reports local; reports contain full document text. Do not commit/upload personal data by default. Use authorized samples, never claim signature/authentication functionality. This auxiliary engine reuses isolated real glyphs; natural word-level joining and reconstruction of unseen characters from a short freeform photo are outside this release.
