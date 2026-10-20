---
name: personal-handwriting
description: Manage a user's local English and numeric handwriting samples and saved style preferences, and coordinate faithful handwritten document generation when a validated glyph renderer is available. Use for creating, selecting, or updating personal handwriting profiles and rendering with an established profile; do not treat generic font randomization as learning the user's handwriting.
---

# Personal handwriting

Keep the requested text, digits, symbols, and subscripts exact while using one coherent personal handwriting profile. Read [the profile contract](references/profile-contract.md) when creating or editing a profile.

## Current capability

This version includes a working local profile manager. It does **not** yet contain image-to-glyph extraction, handwriting training, or a personal glyph renderer. You may save reference samples and preferences now. Do not claim a sample has become a usable personal font, or produce generic-font output described as an exact imitation.

## Intake and profile management

For a new profile, ask for a handwritten English/numeric sample and a transcription if it is not supplied. Save it locally with the script. If only a freeform image is available, describe it as a reference sample; request a labeled sampling sheet later if a renderer needs character coverage. No style-readiness status is implied by successful sample import.

Use a storage directory outside the installed skill package, normally `<working-directory>/.local/profiles`, or a location chosen by the user. Do not put private data in a source repository or upload it without destination-specific authorization.

```sh
python scripts/profile.py --store <store> create <id> --name "<display name>"
python scripts/profile.py --store <store> add-sample <id> --file <sample.png> --kind freeform --transcript <transcript.txt>
python scripts/profile.py --store <store> update <id> --preferences <preferences.json>
python scripts/profile.py --store <store> show <id>
python scripts/profile.py --store <store> list
```

Resolve `scripts/profile.py` relative to this skill. Return the selected profile ID, saved preferences and actual supported state, without exposing private sample contents unnecessarily. Updating preferences is not model training.

## Future rendering handoff

Only render in a personal style after confirming a compatible installed engine and trusted glyph coverage. Until then, explain the missing engine and finish any requested profile work that is possible. Never invent a successful engine run.

When rendering becomes available:

- Take the user's text or structured runs as content truth; preserve identity fields, calculations, signs and subscripts.
- Check required characters first. Default to an explicit missing-glyph error, not silent font substitution. If the user accepts a fallback, disclose which characters are affected.
- Use the same profile for prose, digits and mathematical symbols. Preferences can change measured layout variation; they cannot stand in for the user's missing glyphs.
- Show a short fixed-seed preview before a large export when the user is choosing a new style. Continue with an already accepted profile without repeatedly asking.
- Validate the visible output as well as text/mapping logs. Inspect every PDF page for clipping, overlap and numeric ambiguity. Do not use hidden text extraction alone as proof that visible generated handwriting is correct.

## Boundaries

Use samples supplied or authorized by the user. This workflow does not copy signatures or create authentication/identity attestations. Do not include personal samples, profile exports, homework or identity fields in code commits or public examples by default.
