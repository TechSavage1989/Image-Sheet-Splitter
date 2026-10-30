# Image Sheet Splitter agent guide

Read this file and DEVELOPMENT_HANDOFF.md before changing the project.

## Baseline rules

- The GitHub repository is the authoritative source after the first approved sync. Before that sync, the local 1.7.0 development baseline in the current handoff is newer than the repository placeholder.
- Preserve working splitter, drag-and-drop, Results, settings, logging, help, hover-help, and output-naming behavior unless a change is requested.
- Stable Windows launch name: Image Sheet Splitter.exe.
- Default user state belongs under per-user LocalAppData/ImageSheetSplitter, not beside the executable.
- Keep only one rollback executable in the app-owned Rollback directory.
- Do not embed GitHub credentials or API tokens.
- Do not publish source, tags, releases, or binaries unless the user explicitly approves that publication scope.
- Never overwrite an existing published release.

## Repository map

- src/image_sheet_splitter: runtime source.
- assets/icons: current PNG and editable SVG icon. Generate the ICO during the Windows build; do not track generated ICO output.
- build/windows: PyInstaller files and Windows metadata.
- scripts: build/release/source packaging and repository checks.
- tests: unit and negative-control tests.
- docs/releases: release history.
- .github/workflows: CI and manual release workflows.

## Approved root entries

The tracked root is limited to the entries enforced by scripts/check_root.py. Required exceptions are README.md, AGENTS.md, DEVELOPMENT_HANDOFF.md, Build Portable EXE.bat, pyproject.toml, requirements-build.txt, .gitignore, and the conventional project directories listed above.

A genuinely required new root entry must be reviewed, documented here and in DEVELOPMENT_HANDOFF.md, and added to the allowlist in scripts/check_root.py in the same change.

## Validation

Run before handoff:

    python scripts/check_root.py
    python -m unittest discover -s tests -v
    python -m py_compile src/image_sheet_splitter/*.py scripts/*.py

On Windows also run:

    Build Portable EXE.bat

For archive validation:

    python scripts/package_source.py

Extract release/Image_Sheet_Splitter_Source.zip to a clean directory with no .git folder and repeat the root, unit, and compile checks. A Windows release candidate also requires a build from that extracted source.

## Updater contract

Stable feed:

https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/latest/download/update-manifest.json

The updater must remain manual for download and restart. Scheduled checks are allowed, but no automatic download/install/restart. Preserve HTTPS allowlists, ETag caching, backoff, SHA-256 validation, archive safety checks, PE/product/version validation, one rollback backup, active-operation guards, and post-relaunch health validation.

Release packaging must upload these assets together for a stable release:

- Image_Sheet_Splitter_Windows_x64_Portable.zip
- update-manifest.json
- SHA256SUMS.txt

The manifest version and release tag must match vMAJOR.MINOR.PATCH.
