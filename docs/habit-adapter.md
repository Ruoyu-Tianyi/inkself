# Sample habit adapter (experimental)

The product goal remains handwriting imitation from a short natural reference. This adapter is an intermediate experiment, not completion of that goal.

## What is learned

From an existing reviewed, transcribed word/glyph bank, the fitter estimates shared character width/height coefficients, robust canonical rasters for sufficiently observed letters, pen-lift frequencies, simple connector curvature/height statistics and bounded word baseline slopes. Sparse letter-pair evidence can back off to predefined letter-shape families. Shape families, confidence thresholds and renderer safeguards are engineering priors, not learned motor behavior.

New words are rendered character by character using fitted parameters, not by returning a matching captured word or fragment. Glyph rasters remain the scaffold; the model does not recover stroke order, pen pressure or unseen characters. Connector hypotheses can be wrong. The reference renderer and VATr++ modes remain available for comparison.

## Local fitting

A developer must first prepare and visually verify a reference bank. Upload alone does not yet create this bank automatically. No personal assets belong in Git.

```powershell
python scripts/fit_habits.py --bank .local/example/reference-bank/bank.json --output .local/example/habit-model.json --exclude validationword
```

The bank contains source hashes, a reviewed flag, glyph PNGs with baselines, and transcribed word PNGs. The fitter estimates constrained column alignments, rejects uncertain examples, and records training/excluded words and source hashes. Exclusions are supplied by the evaluator; all matching word images are excluded from geometry, shape and connector fitting. Check estimated alignments and held-out renders before attaching the artifact to a profile.

To enable the experimental web mode for a locally reviewed profile, set `reference_bank` and `habit_model` in its private profile JSON to profile-relative paths. `habit_model` must point to the fitted JSON. The API checks containment, source identity, bank hash, numeric parameters and training reference hashes. This is a developer workflow until automatic transcription/alignment and a review UI are implemented.

## Validation

Synthetic tests check exclusion, inference without whole-word lookup, numeric/operator pixel preservation, deterministic occurrence rendering, margins, source/parameter validation and API gating without VATr++ weights. They do not establish personal similarity.

Use identical held-out text, size and ink for reference-versus-adapter comparisons. Include new letter combinations, repeated words, digits and operators. Inspect actual PDFs and obtain owner feedback. Small development word sets or raster-distance metrics are diagnostic only; they must not be advertised as handwriting similarity percentages. Do not make this mode the default on that evidence.
