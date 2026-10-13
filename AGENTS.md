# HDR2KTX2 maintenance

- This app's release version lives in `version.json` and is displayed in the UI.
- Every AI-authored change to the app must increment the version (for example, `v1.0` to `v1.1`) and add a short entry to `CHANGELOG.md`.
- Rebuild the one-file executable with `build.ps1` after changing the application.
- Keep the bundled CLI, sampler DLL, KTX DLL, and shader files together under `bundle/`; PyInstaller embeds that directory into the executable.
- HDR processing creates an IBL-prefiltered six-face cubemap KTX2, not a same-sized lat-long conversion. Preserve this distinction in user-facing text.
