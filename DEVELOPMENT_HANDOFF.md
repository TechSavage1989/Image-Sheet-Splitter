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
- Publication status: this 1.7.0 source/release baseline has not been published to GitHub. Publication requires explicit approval.

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
- Native Windows PyInstaller build was not performed in this Linux environment.
- Native Windows Explorer drag-and-drop, Windows version-resource validation, in-place executable replacement, rollback, custom/legacy shortcut behavior, foreground detection, and visible-window health confirmation remain target-platform validations.
- The required previous-version-to-new-release end-to-end updater test cannot be performed yet because the repository has no prior published Image Sheet Splitter release. It must be performed on Windows before a later release is called fully verified.
- Hosted GitHub Actions cannot be reported as passing until this baseline is explicitly published and the workflow actually runs.

## Known migration limitation

The previously distributed Sprite Sheet Splitter build does not contain the new updater, so its one-time rename cannot automatically rewrite legacy shortcuts. Users moving from that old manual build should recreate the shortcut once for Image Sheet Splitter.exe. From the first Image Sheet Splitter release onward, updater replacements preserve the running executable filename, including intentional custom filenames.

## Publication guidance

Do not push this baseline, create a tag, or publish a GitHub release unless the user explicitly approves source/release publication. Once approved, sync the full source tree, verify CI on the exact commit, create the matching tag, build from a clean checkout/archive, publish all three update assets together, and verify the latest-release manifest URL and updater path from the previous release.
