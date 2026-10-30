# Image Sheet Splitter development handoff

## Current baseline

- Development version: 1.7.0
- App identity: Image Sheet Splitter
- Stable executable: Image Sheet Splitter.exe
- Repository: https://github.com/TechSavage1989/Image-Sheet-Splitter
- Repository visibility: public
- Default branch: main
- Repository state at baseline inspection: one initial commit containing only a placeholder README; no AGENTS.md, handoff, source, PRs, releases, or CI.
- Source baseline used for continuation: the latest v1.6.0 Sprite Sheet Splitter portable build kit created in the current ChatGPT conversation, because GitHub contained no newer source.
- Publication status: source is published on main. The first 1.7.0 release publication is explicitly approved, but the final release workflow dispatch remains pending because the connected GitHub tool cannot dispatch workflows or create releases directly.

## What changed in 1.7.0 development baseline

- Renamed the product identity to Image Sheet Splitter.
- Preserved the existing image detection, drag-and-drop, output naming, detachable Results, resizable panes, logging, Settings, Help, and hover-help behavior.
- Stable Windows launch filename is now Image Sheet Splitter.exe.
- Added migration of the legacy SpriteSheetSplitter config locator/default config into the new ImageSheetSplitter user-data identity.
- Added a token-free stable GitHub Releases updater using releases/latest/download/update-manifest.json.
- Update checks are scheduled at startup, every five minutes, and on native foreground return after two minutes since the previous attempt.
- Added ETag caching, offline/error handling, throttling/backoff, and manual-check cooldowns.
- Added explicit Download and Install and restart actions. Nothing downloads or restarts automatically.
- Added SHA-256 verification, HTTPS host allowlists, archive traversal/symlink/file-count/size/compression checks, single expected EXE validation, PE checks, and Windows ProductName/FileVersion checks.
- Added staged replacement, one rollback backup, relaunch health marker, rollback on failed health, and post-helper cleanup.
- Reorganized implementation into src/, assets/, build/, scripts/, tests/, docs/, and .github/.
- Added repository-root allowlist enforcement and a negative-control test.
- Added README content using the shared user-first structure requested for maintained apps.

## Paths

Default Windows user-data root:

    %LOCALAPPDATA%\ImageSheetSplitter

Subdirectories/files:

- Image_Sheet_Splitter.config.json: default configuration.
- config_location.txt: remembers a custom configuration path.
- Logs: optional file logs.
- Cache/update-state.json: update ETag/cache/backoff state.
- Downloads: verified update downloads before staging.
- Staging: extracted update and install-plan/health markers.
- Rollback/previous.exe: single retained rollback executable.

Legacy migration source:

    %LOCALAPPDATA%\SpriteSheetSplitter

A legacy custom config locator is preserved. A legacy default config is copied to the new default location when no new config exists.

## Update feed and release contract

Stable manifest:

https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/latest/download/update-manifest.json

Release tag format:

    v1.7.0

Stable assets:

- Image_Sheet_Splitter_Windows_x64_Portable.zip
- update-manifest.json
- SHA256SUMS.txt

The manifest contains app identity, version, concise notes, release/read-more URL, portable asset name/URL/size, SHA-256, and expected executable path. A matching hash verifies bytes but is not publisher code signing.

## Build and test commands

Cross-platform source checks:

    python scripts/check_root.py
    python -m unittest discover -s tests -v
    python -m compileall -q src/image_sheet_splitter scripts

Windows portable build:

    Build Portable EXE.bat

Source archive:

    python scripts/package_source.py

The Windows build wrapper installs pinned build dependencies into .build-venv, runs root/tests/version generation, generates the multi-resolution Windows ICO, runs PyInstaller, then creates the portable ZIP, update manifest, and hashes.

## Root allowlist

Enforced by scripts/check_root.py. The guard is filesystem-based and works in extracted source archives without .git. Generated directories such as release, dist, build-output, .build-venv, and cache directories are explicitly ignored.

Negative control: tests/test_root_guard.py creates an isolated allowed tree plus an unapproved root file and verifies the guard rejects it; the clean fixture must pass.

## Validation performed in this environment

- Repository metadata, ownership, visibility, main branch, exact initial commit, placeholder README, lack of PRs, and lack of releases were verified through the connected GitHub account.
- Repository root allowlist passed.
- README heading structure, navigation anchors, local documentation links, and icon asset path passed the documentation checker.
- Python syntax compilation passed for runtime and build/support scripts.
- 12 unit tests passed, covering known crop detection/naming, generic naming, legacy config migration, update-version comparison, HTTPS allowlisting, manifest identity, ETag 304 cache reuse, offline negative control, ZIP traversal rejection, and root-guard negative control.
- A source archive was generated, extracted into a clean directory with no .git metadata, and the root checker, documentation checker, syntax compilation, and all 12 tests passed again from that extracted archive.
- Release packaging logic was exercised with a disposable test executable; the generated portable ZIP had one top-level Image Sheet Splitter folder and the manifest/hash verification passed. This disposable package is not a release candidate and does not validate PE identity.
- Both GitHub Actions YAML files parsed successfully as YAML locally.
- Native Windows PyInstaller build completed successfully in hosted GitHub Actions on a windows-latest runner.
- Windows ProductName/FileVersion validation passed in hosted CI. Native Windows Explorer drag-and-drop, interactive GUI startup, in-place executable replacement, rollback, custom/legacy shortcut behavior, foreground detection, and visible-window post-update health confirmation remain interactive target-platform validations.
- The required previous-version-to-new-release end-to-end updater test cannot be performed yet because the repository has no prior published Image Sheet Splitter release. It must be performed on Windows before a later release is called fully verified.
- Hosted GitHub Actions run 41097395736 passed on commit 12f70d0edc7d257173ca3e6700e6f149402ba826, including Ubuntu tests, Windows tests, clean source-archive validation, native Windows PyInstaller build, Windows version-resource verification, release packaging, release verification, and artifact upload.

## Hosted CI and publication status

- Initial source baseline commit: 1eea9eb12beec4079083311df6e7aa146850515e.
- Negative-control CI run: 41097142040 failed on Windows only because the old validation command relied on Unix-style shell wildcard expansion for py_compile. Unit tests and earlier source checks passed before that failure.
- CI portability fix commit: 12f70d0edc7d257173ca3e6700e6f149402ba826, replacing the wildcard command with python -m compileall -q src/image_sheet_splitter scripts.
- Corrected CI run: 41097395736 completed successfully on the exact fix commit.
- Windows release-candidate artifact ID: 12996508402, name image-sheet-splitter-windows-release-candidate.
- The Windows job passed version metadata generation, deterministic multi-resolution icon generation, PyInstaller, verify_windows_build.py, package_release.py, verify_release.py, and artifact upload.
- Independent artifact inspection confirmed exactly three outer files: Image_Sheet_Splitter_Windows_x64_Portable.zip, update-manifest.json, and SHA256SUMS.txt.
- Portable ZIP SHA-256: 6821b8a50e192461afe1df5cc5e0b068abd741b9407673b8dc6b942489d9b2d0.
- update-manifest.json SHA-256: 44fe90fdc52e4b4eed61f4c73bfd992f1ce772da86b0d7da2ff466d4de5fca2b.
- Built Image Sheet Splitter.exe SHA-256: ce999bf2628b41757c6d69e26a762aa34c4ca651e5b4c8080b8fe8eeac536b7d.
- The portable ZIP contains one top-level Image Sheet Splitter folder with Image Sheet Splitter.exe and README.txt.
- The manifest identifies TechSavage1989.ImageSheetSplitter version 1.7.0 and its portable asset hash/size matches the verified ZIP.
- No GitHub release or v1.7.0 tag exists yet. The connected GitHub integration supports repository writes and CI inspection but does not expose workflow dispatch, release creation, release-asset upload, or tag creation. The prepared Publish stable release workflow must therefore be dispatched through GitHub after final-source CI passes.

## Known migration limitation

The previously distributed Sprite Sheet Splitter build does not contain the new updater, so its one-time rename cannot automatically rewrite legacy shortcuts. Users moving from that old manual build should recreate the shortcut once for Image Sheet Splitter.exe. From the first Image Sheet Splitter release onward, updater replacements preserve the running executable filename, including intentional custom filenames.

## Publication guidance

Source publication and the first 1.7.0 release were explicitly approved in the 2026-10-30 continuation. Before dispatching the prepared release workflow, verify CI on the exact final main commit. Run Publish stable release with tag v1.7.0, ref set to that exact commit, and confirmation value publish. The workflow refuses to overwrite an existing release or move an existing mismatched tag. After publication, verify all three release assets, the latest-release manifest URL, hashes, and the updater feed. The previous-release-to-new-release updater path cannot be fully tested for this first Image Sheet Splitter release because no previous Image Sheet Splitter release exists.
