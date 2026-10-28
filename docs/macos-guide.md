# Inkself for macOS (preview)

Choose arm64 for Apple Silicon, or x86_64 for Intel. Open the DMG and drag Inkself.app to Applications before launching. No Python installation is required. The app includes a CPU AI runtime; model files download separately on first setup and retain their own licenses.

This preview is ad-hoc signed, not signed with Apple Developer ID and not notarized. Gatekeeper may block it. Only after verifying the GitHub release and checksum, use System Settings > Privacy & Security > Open Anyway if available. Do not disable Gatekeeper globally. Corporate security policies may prevent launching this preview.

Personal data is stored in ~/Library/Application Support/Inkself/data, outside the app bundle. Updating the application does not replace this folder. Back up this folder before migration or deletion.

CI checks include native architecture, ad-hoc signature integrity, local server startup, synthetic handwriting export and native window load. Similarity to your own handwriting and first-time Gatekeeper behavior require human testing on your Mac. AI model weights and personal handwriting are not included. Do not use the preview for signatures or identity authentication.
