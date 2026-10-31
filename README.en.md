# Inkself

[简体中文](README.md) | **English**

Inkself is a **personal handwriting desktop application for Windows and macOS**. It generates new content from natural English and digit handwriting samples, imports Markdown, typesets mathematical notation, and exports handwritten PDFs. The app runs locally with a bundled CPU AI inference runtime. **This is a desktop preview: human validation is ongoing, and it has not met the quality threshold for a stable release.**

## Download the desktop preview

Download the [0.4.0-rc.1 desktop preview](https://github.com/Ruoyu-Tianyi/inkself/releases/tag/v0.4.0-rc.1), or browse all versions on [GitHub Releases](https://github.com/Ruoyu-Tianyi/inkself/releases):

- **Windows x64:** run `Inkself-Windows-x64-Setup.exe`, then open Inkself.
- **Mac Apple Silicon:** download `Inkself-macOS-arm64.dmg`.
- **Mac Intel:** download `Inkself-macOS-x86_64.dmg`.

On Mac, drag the app to Applications before opening it. Installers include the local CPU AI runtime; no separate Python installation or API key is required. Model files are downloaded separately during initial setup. Personal data is stored in your user directory, outside the application bundle.

The Windows installer is unsigned. Mac apps are ad-hoc signed, without an Apple Developer ID signature or notarization. Your operating system may block the first launch. Verify the official release and SHA-256 checksums, and read the [Mac installation guide](docs/macos-guide.md) or [Windows desktop guide](docs/desktop-guide.md), currently in Chinese. Do not disable system-wide security protections.

## Current capabilities

- English and digit samples, with optional mathematical symbols and Greek letters; PNG/JPEG/WebP upload, line segmentation, and line-type review.
- Multiple handwriting profiles, cached personal styles, and preferences for size, line spacing, and ink color.
- **New in the current source:** Natural, Neat, Compact, and Relaxed spacing presets plus custom adjustments for letters, words, lines, paragraphs, digits, symbols, word baseline movement, and spacing variation. Settings are saved with profiles and generated documents. The published `0.4.0-rc.1` installers do not include this feature; see the instructions and mode limitations below.
- Real offline CPU inference using a pinned VATr++ pretrained generator, including words, sentences, and digits absent from the sample.
- Source-image comparison, A4 previews, PDF export, document history, and human feedback.
- Line-based pagination for long documents, keeping question numbers, formulas, and explanations together where possible and reducing paragraph widows and orphans. The habit and reference modes accept up to 20,000 characters.
- Word gaps measured between visible strokes, with stored sample gap distributions and reproducible natural variation. Conservative estimates are identified when sample evidence is insufficient.
- Inline and display mathematics, superscripts and subscripts, fractions, roots, nested brackets, sums, integrals, and Greek letters. Brackets and roots use sample-informed stroke width and slant with slight variation. Missing mathematical glyphs require explicit permission to use supplemental handwriting glyphs.
- Markdown import: local parsing of headings, paragraphs, lists, emphasis, and formulas, with an editable preview, preserved source text, and conversion notices.
- Assignment output: numbered questions, choice columns, tables, text decision trees, common subscript notation, question-aware pagination, and repeated table headers. Optional first-page identification requires a reviewed personal glyph profile.
- A per-user Windows installer, Mac apps for both architectures, and a separate local CPU AI runtime. Initial setup downloads and verifies a pinned model; users do not need to configure Python or an API key, and personal data is stored separately.
- Reusable batch comparisons with fixed test texts, input snapshots, model/code fingerprints, HTML comparison pages, and file-by-file reproduction checks.
- Experimental habit adaptation: shared letter dimensions, some body-text allographs, pen lifts, and connection statistics fitted from manually reviewed word images. Some rules apply to unseen words.
- Symbol variation in habit mode: oversized percent signs and heavy slashes are corrected, with reproducible small shape variations and safeguards for decimal points, colons, and percent-sign loops at small sizes.
- An experimental source-glyph bank. After manual annotation and character review, choose reference-glyph fidelity or model width/slant calibration, with bounded shape and spacing variation for source digits. A developer currently prepares this bank; it is not built automatically from an uploaded image.

Generation and layout operate word by word, rather than producing continuous paragraph-level strokes. Habit adaptation still uses raster stroke skeletons from the source; it is not an end-to-end stroke trajectory generator, and arbitrary unannotated short samples cannot yet be cloned automatically. The default model does not substitute a generic font or require collecting every character individually. A separate, manually reviewed reference mode reuses observed words, fragments, and letters; it cannot infer unseen characters or joins.

## Spacing and writing rhythm (current source)

On the writing screen, choose a spacing style and expand the individual controls. You can make text more compact or increase space between lines and paragraphs, while separately adjusting how words move above and below the baseline and how much gaps vary. Editing a control selects Custom; restoring Natural resets the defaults. Changes apply the next time you generate, in both standard-document and assignment layouts.

| Control | Effect |
| --- | --- |
| Letter spacing | Gaps between letters within a word; habit and reference modes only |
| Word spacing | Gaps between the visible strokes of adjacent words |
| Line spacing | A multiplier on the base line spacing, with room retained for ink and formulas |
| Paragraph spacing | Space between existing paragraphs |
| Digit spacing | Gaps within digit sequences; habit and reference modes only |
| Symbol spacing | Horizontal spacing around symbols; habit and reference modes only |
| Word baseline movement | Vertical movement of words within a line |
| Spacing variation | Strength of gap variation, independent of glyph-shape variation |

Natural preserves the default settings. Neat reduces gap variation and baseline movement with slightly wider lines; Compact reduces spacing and vertical whitespace; Relaxed increases spacing and allows slightly stronger variation. A spacing value of `100%` means the default level. Set baseline movement or spacing variation to `0%` to turn off that added variation. Existing irregularities within the original handwriting image remain. For letter, symbol, line, and paragraph gaps that were previously fixed, extra variation starts above `100%`; lower values adjust existing word and digit gap variation.

**Fine adjustments inside words, numbers, and symbols require habit or reference mode.** The default neural model and model-calibrated mode generate complete word images; their internal-spacing controls are disabled. The other layout controls remain available. Changing internal spacing reconstructs affected captured words from reviewed glyphs, so their original joins may change. Pixel rounding, mathematical structure, and minimum clearance can limit the visible effect of a small adjustment.

Settings are saved with each generated document and become the selected profile's preferences for its next use. These are reproducible layout preferences, not evidence that the app has learned additional habits from the sample. The same input, profile, model, code, settings, and random seed reproduce the result. Width and height changes can alter wrapping, page count, and page breaks; check the generated preview before exporting. The [spacing guide](docs/spacing-controls.md) provides step-by-step instructions in Chinese.

## Quick start

After installing the full desktop app for your system:

1. Open Inkself and select “准备本地 AI” (prepare local AI). Initial setup downloads approximately 580 MB from a pinned model revision. After verification, generation can run offline.
2. Naturally copy the supplied English and digit prompt. Add the optional mathematics section if needed. Upload a photo and classify each line as English/digits, mathematics/Greek, or unused.
3. Enter new content or import Markdown, generate a trial, and compare it with the source character by character.
4. Export the PDF and record content accuracy, handwriting similarity, and naturalness.

The Windows build targets compatible Windows 10/11 x64 systems; separate Mac builds support Apple Silicon and Intel. Native window startup and PDF export have been checked for all three release packages. First-time installation, model setup, and personal handwriting quality still need human validation. Bundling resolves environment setup requirements; it does not establish high-fidelity cloning from arbitrary short samples. Initial downloading needs internet access but does not send your samples or documents. Markdown containing structured formulas still requires a reviewed personal glyph profile. See the [Windows desktop guide](docs/desktop-guide.md), [Mac installation guide](docs/macos-guide.md), [Markdown import guide](docs/markdown-import.md), and [AI workflow](docs/ai-workflow.md), currently in Chinese.

### Run from source (developers)

The following steps are for Windows development with Python **3.10–3.12**. Most users should use an installer above. `setup-web.ps1` retains its historical development-setup filename:

```powershell
git clone https://github.com/Ruoyu-Tianyi/inkself.git
cd inkself
./setup-web.ps1
./.local/model-env/Scripts/python.exe -m pip install -r desktop-requirements.txt
./.local/model-env/Scripts/python.exe desktop.py
```

Starting the desktop app from source also opens an application window. The legacy **Start Inkself.cmd** remains available for local interface debugging at `http://127.0.0.1:8765`. Downloading models and dependencies requires internet access and additional disk space. Follow your machine's PowerShell execution policy without disabling system-wide protections.

See the [development environment guide](docs/web-guide.md) for setup, stopping the debugging service, and troubleshooting.

A basic portable package can still be built with `python scripts/build_desktop.py`. Its menu supports importing old profiles and connecting an existing model environment; the basic package itself does not include the AI runtime.

## Validation status and limitations

| Area | Status |
| --- | --- |
| Local automated tests | Current source on Windows: 262 tests, 261 passed and one real-symlink test skipped because of Windows permissions; 5 UI state tests also passed. Spacing presets, a four-page document, a three-page answer sheet, and repeatable exports with fixed settings were checked. See GitHub Actions for native checks of the published Mac builds. |
| Real model inference | Both the source environment and the separate InkselfAI.exe have generated outputs, checking cache reuse, complete results, and job logs. This does not establish handwriting similarity. |
| Application flow | Sample import, confirmation, generation, preview, and PDF export have been exercised. Windows and both Mac architectures passed native-window and synthetic-sample export checks; see [release validation](https://github.com/Ruoyu-Tianyi/inkself/actions/runs/40683998555). |
| Personal similarity and generalization to other writers | **Validation is ongoing; no passing conclusion yet.** |
| Comprehensive content accuracy | **Not fully validated. Habit mode includes digit/symbol regression checks, but the default model can still write incorrect content.** |
| Independent OCR and automatic correction | Not integrated. Outputs require human review by default. |
| Remote multi-user service | Not deployed. The local service should not be exposed directly to the public internet. |

Current support covers uppercase and lowercase English, digits, and some punctuation in the model alphabet. The default neural model does not support Chinese, equals signs, dollar signs, or structured formulas. Mathematical input requires habit or reference mode and `$...$` / `$$...$$` delimiters. Supplemental paths can be explicitly enabled for unsampled mathematical glyphs; their specific shapes have not been learned from your sample. Successful generation, content logs, or downloads do not prove that the content is correct or that the handwriting resembles its owner.

## Development and structure

```sh
# Run inside the project's Python environment
python -m unittest discover -s tests -v
node --check web/static/app.js
node --test tests/test_spacing_ui.cjs
python -m uvicorn web.app:app --host 127.0.0.1 --port 8765
```

- `web/`: application interface, local API, sample processing, and the VATr++ inference adapter.
- `scripts/setup_model.py`: pinned model-asset downloading and large-file hash verification.
- `web/model_setup.py`, `web/model-assets.json`: first-use downloads, resuming interrupted downloads, and per-file verification.
- `ai_worker.py`, `packaging/`, `scripts/build_*.py`: the separate AI runtime, portable apps, and per-user installer. Public installers do not embed model weights.
- `engines/glyphs/`: individual-character capture and deterministic glyph-reuse tools for assistance and comparison, separate from the app's few-shot generation model.
- `tests/`: synthetic-sample and API tests, not evidence of validated human handwriting similarity.

See [habit-adaptation experiments](docs/habit-adapter.md) for the developer fitting workflow and validation boundaries, and the [reproducible comparison workflow](docs/experiment-workflow.md) for batch generation and rerunning input snapshots. The repository includes [three test-text sets](examples/evaluation-suite.json), with no personal handwriting.

The [mathematics and document guide](docs/math-and-documents.md) covers long text, formula input, supplemental-glyph sources, AI dependencies, and limitations.

Also see the [architecture](docs/architecture.md), [product roadmap](docs/roadmap.md), and [auxiliary glyph workflow](engines/glyphs/workflow.md). Supporting guides are currently primarily in Chinese.

## Models, data, and privacy

The app uses a pinned [VATr++](https://huggingface.co/blowing-up-groundhogs/vatrpp) generator. Sources, licenses, and adaptation details are documented in the [third-party model notice](docs/model-notice.md). Public installers bundle inference dependencies, but not weights, upstream model code, or character prototypes. Initial setup downloads those assets from the model source to the user's computer. They are not committed to this source repository.

Samples, transcriptions, style caches, documents, and reports containing full inputs are stored locally by default and excluded from Git tracking. Use only your own samples or samples you are authorized to use. The app does not provide signatures or identity verification.

Early experiments were inspired by [TypeScribe](https://github.com/rudyoactiv/typescribe-handwriting). The current app uses VATr++ for style-conditioned generation from static images, rather than TypeScribe's stroke-trajectory priming interface.

## License and commercial licensing

The project's own code uses [PolyForm Noncommercial 1.0.0](LICENSE). This is a source-available project with use restrictions. Noncommercial uses and institutional uses expressly permitted by the license are subject to its terms; commercial use outside that scope requires separate written authorization. The author retains commercial licensing rights. See the [commercial licensing notice](COMMERCIAL-LICENSE.md) and [contribution policy](CONTRIBUTING.md). Third-party components, fonts, and models retain their own licenses.
