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

Synthetic tests check exclusion, inference without whole-word lookup, digit preservation, bounded symbol variation, deterministic occurrence rendering, margins, source/parameter validation and API gating without VATr++ weights. They do not establish personal similarity.

Use identical held-out text, size and ink for reference-versus-adapter comparisons. Include new letter combinations, repeated words, digits and operators. Inspect actual PDFs and obtain owner feedback. Small development word sets or raster-distance metrics are diagnostic only; they must not be advertised as handwriting similarity percentages. Do not make this mode the default on that evidence.

## Renderer integrity improvements

The fitter now requires a connected component crossing a candidate boundary before counting a positive join. Inference requires repeated supporting evidence and stronger agreement for generalized letter families; unobserved capital-letter joins are rejected. Robust glyph aggregates with collapsed or excessively filled stroke masks fall back to the reviewed glyph. These are quality safeguards, not a new neural trajectory model.

Learned rasters and curves remain at three times native resolution through word composition. Baseline and em-height metadata scale together, so PDF physical size remains stable. Nonletters keep their native proportions per character, including grouped numbers, time separators and tiny punctuation inside mixed tokens.

Web jobs capture input hashes when queued. If a bank or fitted adapter changes before execution, the job fails instead of silently using different inputs. Reports include a path-neutral input fingerprint and renderer code fingerprint.

## Symbols in the habit renderer

`symbol_style.py` applies small deterministic changes to reviewed punctuation and operators. Seed, token occurrence and character index determine the variant. Digits keep their captured geometry; the reference renderer remains an unchanged control. This is procedural variation, not learned pen pressure, stroke order or additional character recognition.

An oversized percent can be scaled relative to the sample's digits. When two loops and a separate diagonal are unambiguous, an excessively thick slash is rebuilt along its captured centerline at a width derived from the loops. Loop placement and slash curvature vary slightly, alongside bounded rotation, scale and offset. Other symbols vary conservatively; decimal points and colon dots receive minimal contrast/support protection against disappearing during downsampling.

Connected components and holes are checked before accepting a symbol. Percent candidates are also checked as isolated layers at their actual position on a fixed word canvas, across UI font sizes 10–26. Deterministic retries leave digit positions, canvas dimensions and baselines fixed. If no candidate passes, the normalized base is returned with its actual `canvas_guard_passed` status; false means still unverified. Reports expose source hashes, normalization, transformations and the chosen attempt. Visual review remains necessary: topology is not OCR or a similarity score.

Use [the symbol suite](../examples/symbol-evaluation-suite.json) with the experiment runner. Every character must already exist in the reviewed bank; unavailable math signs are not silently replaced with a generic font. Both web jobs and experiment fingerprints include the symbol renderer code.

## 数字自然变化

习惯模式和模型校准模式中的数字保留审核样本笔迹，按种子、出现次数和位置施加有界旋转、宽高和基线变化；相邻数字使用共享节奏与局部扰动的正间距。正文、表格和公式均生效，原稿对照模式不变。变化带有来源哈希，保留连通分量和孔洞；不合格候选回退原图。小数点、百分号沿用各自的可读性保护。

这属于对已有数字的程序化变化，尚不是从多个真实数字样本学到的不同写法，也不是笔顺或压力建模。仍需人工检查 0/6/8/9 等易混数字及小字号输出。
