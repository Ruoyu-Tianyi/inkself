# Inkself for macOS (preview)

Download [0.5.0-rc.1](https://github.com/Ruoyu-Tianyi/inkself/releases/tag/v0.5.0-rc.1). Choose `Inkself-macOS-arm64.dmg` for Apple Silicon, or `Inkself-macOS-x86_64.dmg` for Intel. Open the DMG and drag Inkself.app to Applications before launching. No Python installation is required. The app includes a CPU AI runtime; model files download separately on first setup and retain their own licenses.

This preview is ad-hoc signed, not signed with Apple Developer ID and not notarized. Gatekeeper may block it. Only after verifying the GitHub release and checksum, use System Settings > Privacy & Security > Open Anyway if available. Do not disable Gatekeeper globally. Corporate security policies may prevent launching this preview.

Personal data is stored in `~/Library/Application Support/Inkself/data`, outside the app bundle. Updating the application does not replace this folder. The current text and layout settings are stored in `compose-draft.json` within this directory. Wait for “草稿已保存在本机” (draft saved locally), close the app, then back up the entire folder before migration or deletion. The draft contains your input text and should be kept private along with your samples.

Version 0.5.0 includes Natural (自然), Neat (工整), Compact (紧凑), and Relaxed (宽松) spacing buttons, plus individual adjustment controls. Click Generate after selecting a style to see its effect. Fine adjustments within words and numbers require a reviewed glyph profile in habit or reference mode. See the [English spacing overview](../README.en.md#spacing-and-writing-rhythm).

Drafts survive restarts even when the desktop app selects a different local port. Completing a generation preserves edits made while waiting. Opening history asks before replacing an unsent draft. Markdown import also preserves edits made while the file is being read. A temporary loss of the local connection triggers status retries, with a manual retry available; do not resubmit merely because status updates paused. If draft saving fails, keep the window open and retry saving.

In assignment mode, `$$...$$` or `\[...\]` formulas occupy their own centered lines. Opted-in supplemental symbols can appear directly beside digits, such as `12×34`. Escape literal currency dollar signs as `\$`; a `$` glyph must still be present in the profile. Use `USD 12.50` if it is unavailable.

CI checks cover native architecture, ad-hoc signature integrity, local server startup, synthetic handwriting export and native window load. See this version's [release page](https://github.com/Ruoyu-Tianyi/inkself/releases/tag/v0.5.0-rc.1) for the results of each architecture. Similarity to your own handwriting and first-time Gatekeeper behavior require human testing on your Mac. AI model weights and personal handwriting are not included. Do not use the preview for signatures or identity authentication.
