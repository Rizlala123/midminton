# Target-PC validation handoff

Created: 12 November 2026, 13:15:49 IST (UTC+05:30). Scope: first Phase 1 desktop implementation. **All checks are NOT RUN.** The authoring PC must not run the application, tests, builds, model tools or dependency installs.

1. Transfer/clone the committed project to the testing PC. Preserve the source commit ID in your result record. No GitHub remote is configured by this work.
2. Follow [requirements and setup](requirements.md), including icon generation and local Python selection. First verify manual scoring without any model.
3. Run the target-only static/unit/build commands using the supplied script. Read the script before invoking it; it requires an explicit target-machine confirmation switch and installs nothing.
4. Complete [manual, media, CV and performance cases](test_cases.md). Use your original Midminton recordings, including a background/spectator crossing, with permission already established by ownership.
5. Copy [the results template](results_template.md), fill measured results, attach locally retained evidence and list failures. Never turn NOT RUN into PASS merely because source looks correct.
6. After resolving dependencies on this PC, review and commit `package-lock.json`, `src-tauri/Cargo.lock`, authored icon assets and a dependency-version record. Do not commit weights, recordings, caches, private projects, environments or API keys. Push only when Riz supplies and authorises the repository.

From the project root on the **testing PC only**, after prerequisites/setup:

```powershell
.\testing\2026-11-12_13-15-49_IST\run_checks.ps1 -ConfirmTargetMachine
$env:MIDMINTON_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm run desktop
```

The script runs Python unit tests, TypeScript checking/frontend build and `cargo check`. It does not open the app, download a model, do inference or build the installer. Installer validation is a separate manual step. The source remains an unverified development build until all relevant cases pass on the target PC.
