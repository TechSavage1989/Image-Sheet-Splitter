# Image Sheet Splitter development handoff

## Current baseline

- Version: 1.7.0; stable filename: Image Sheet Splitter.exe.
- Public repository: https://github.com/TechSavage1989/Image-Sheet-Splitter; default branch: main.
- Continued from prepared main commit d80ad901f729ade37b1e509532c2c67b465205ec, not from a new implementation.
- Source sync and first 1.7.0 release publication are authorized. This is not permission for visibility/access changes, credentials, unrelated features, or future releases.
- No release or v1.7.0 tag existed at the 2026-10-30 Desktop inspection. Release dispatch remains pending; do not advertise an asset as published until GitHub confirms it.

## Runtime and updater contract

The existing splitter, image naming, drag-and-drop, Results, settings, help, logging, and icon artwork remain intact. Default user state belongs in `%LOCALAPPDATA%\ImageSheetSplitter`, with a custom configuration locator supported. Migration from `%LOCALAPPDATA%\SpriteSheetSplitter` remains supported.

State includes `Image_Sheet_Splitter.config.json`, `config_location.txt`, `Logs`, `Cache/update-state.json`, `Downloads`, `Staging`, and exactly one retained rollback executable at `Rollback/previous.exe`.

Stable feed:

https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/latest/download/update-manifest.json

Checks run at startup, every five minutes, and on foreground return after two minutes. ETag caching, backoff, explicit download/install/restart actions, active-operation guards, HTTPS allowlists, SHA-256, archive limits, and Windows PE/product/version validation remain in place. No credentials are embedded. SHA-256 verifies bytes; it is not publisher code signing.

## Updater repairs

- Build one Windows-quoted launch command line with `subprocess.list2cmdline`, preserving health and plan paths containing spaces.
- Reject destination collisions before modifying the backup. Replace the current executable atomically; rollback cleanup only touches a target actually replaced by this attempt.
- Use an attempt-specific health token, expected version and executable path, and a live launched process/one-file child check. Marker existence alone is insufficient.
- Stop the complete PyInstaller process tree before restoring a failed candidate.
- Preserve generic and custom executable filenames, settings values, config locator, and existing shortcuts. Normal app startup still rewrites JSON formatting and updates app-version metadata.
- Reject Windows drive/alternate-stream/normalized archive paths and download filenames that could escape Downloads.
- Verify compiled x64 identity and all 11 icon images against the generated ICO; verify manifest size, ZIP hash, and both SHA256SUMS entries.

The legacy manual Sprite Sheet Splitter distribution has no updater. Its old shortcut must be recreated once when moving to Image Sheet Splitter.exe; it cannot be retroactively repaired by the new updater.

## Build and source checks

    python scripts/check_root.py
    python scripts/check_docs.py
    python -m unittest discover -s tests -v
    python -m compileall -q src/image_sheet_splitter scripts

Windows build:

    Build Portable EXE.bat

The wrapper installs pinned dependencies in `.build-venv`, runs source/native fixture tests, builds with PyInstaller, validates icons/version/x64 identity, runs compiled-app replacement tests, and packages/verifies release assets. CI and the manual release workflow also run compiled-app replacement tests.

Source archive:

    python scripts/package_source.py

Extract `release/Image_Sheet_Splitter_Source.zip` to a separate directory with no `.git`, repeat the source checks, then run its Windows build wrapper. The root allowlist applies to extracted archives as well as Git checkouts.

## Native validation evidence and limits

Native coverage lives in `tests/test_windows_updater.py` and `tests/fixtures/update_app.cs`. It uses temporary folders and redirected LOCALAPPDATA, never the user's installed app. The prior 1.6.0 executable is synthetic: there is no previous published Image Sheet Splitter release.

The suite covers successful replacement, generic/custom names, early exit, a full 45-second health timeout, wrong version/token/PID/malformed health responses, destination collisions, settings, real `.lnk` files, and one rollback backup. After a build, `ISS_TEST_COMPILED_EXE` enables two compiled-app tests covering three scenarios: success with generic name, success with custom name, and failed-health rollback that stops the one-file app's child process.

Desktop validation on 2026-10-30 uses Windows 11 and Python 3.14.5. Source/root/docs/compile checks, the native fixture tests, the clean-source Windows build, x64/product/version/11-icon validation, and compiled-app tests are the release gates. CI must also pass on the exact commit before dispatch; consult Actions for the final run rather than relying on historical baseline runs.

Completed locally: root/docs/compile checks; 19 source/native tests (the two post-build tests skipped until the EXE existed); clean archive extraction without `.git`; full Windows build from that extracted source; both compiled-app tests (three scenarios); and package/manifest/checksum verification. These passed. The extracted-source portable ZIP hash was `0da1ae94cdf9ca3b2932ba53f05dc41d77479bed0c3045cbc0c1db868d06eada`; this is a local validation artifact, not a published asset hash.

The compiled app reports a viewable Tk window and passes process/version/token health validation. This is programmatic native health evidence, not an interactive visual inspection. Explorer drag-and-drop, foreground behavior, and manual GUI inspection remain unverified in this continuation because Computer Use stopped on unsupported Windows Firefox URL-policy enforcement. No upgrade from a previously published Image Sheet Splitter release is claimed.

## Publication procedure and remaining access blocker

Use the corrected workflow:

https://github.com/TechSavage1989/Image-Sheet-Splitter/actions/workflows/release.yml

Verify that CI passed on the exact latest main commit. Then run **Publish stable release** on main with:

- tag: `v1.7.0`
- ref: `main`
- confirm: `publish`

Do not rerun historical failed workflow 41102816840 or release a historical commit with different workflow files. The corrected workflow creates the tag through GitHub Releases at verified current main, refuses existing releases/mismatched tags, uploads the assets, downloads them, and verifies checksums and the remote tag.

Expected assets:

- `Image_Sheet_Splitter_Windows_x64_Portable.zip`
- `update-manifest.json`
- `SHA256SUMS.txt`

The ZIP contains one `Image Sheet Splitter` folder holding the executable and README.txt. Upload all three assets together. Never overwrite an existing release.

The connected GitHub tools support source publication and CI inspection but expose no workflow dispatch or release creation. The Desktop has no detected GitHub CLI login or credential-manager GitHub account. Its existing Firefox session could not be used: Computer Use stopped with "browser URL policy enforcement is not yet supported for the current Windows browser." No dispatch was attempted and no credential was created. A supported authenticated browser or CLI is required for the already-authorized final dispatch.

After publication, verify the public release URL, exactly three assets, latest-release manifest, ZIP size and SHA-256, manifest SHA-256, and tag commit. Update README Download and this handoff only after those live checks pass.
