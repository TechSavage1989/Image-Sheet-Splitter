# Image Sheet Splitter development handoff

## Current baseline

- Published baseline: v1.7.0. Current development candidate: v1.7.1 on fix/v1.7.1-updater, not yet released; stable filename remains Image Sheet Splitter.exe.
- Public repository: https://github.com/TechSavage1989/Image-Sheet-Splitter; default branch: main.
- Continued from prepared main commit d80ad901f729ade37b1e509532c2c67b465205ec, not from a new implementation.
- Source sync and first 1.7.0 release publication are authorized. This is not permission for visibility/access changes, credentials, unrelated features, or future releases.
- Published baseline: v1.7.0 GitHub stable release created on 2026-10-30 at 19:27:23 UTC, tag pointing to d80ad901f729ade37b1e509532c2c67b465205ec. Main has subsequent unpublished source/updater validation changes and release-pipeline fixes; do not treat main as identical to the already published 1.7.0 binary.

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

## Published v1.7.0 release and follow-up

The public stable release is [v1.7.0](https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/tag/v1.7.0), published 2026-10-30T19:27:23Z with these exact three assets:

- Image_Sheet_Splitter_Windows_x64_Portable.zip (19,337,910 bytes, GitHub SHA-256 ec48c07e54e5ca4488b8e7b4094af24c0acbae88f9325f896496361c844e9375)
- update-manifest.json (1,663 bytes, GitHub SHA-256 1f0b1549e885a8106a70dfcb6b30eb94e1450bf485144c23ac9bc5d8bbc4a17e)
- SHA256SUMS.txt (201 bytes, GitHub SHA-256 a3bebffbd1449e521aea8dccdcd1877643a1b5ee9f7847842623e85da11875ac)

Tag v1.7.0 resolves to d80ad901f729ade37b1e509532c2c67b465205ec; this is the published build's source, not newer main. The release workflow run 41115259781 verified the Windows EXE/build/package, created the release and tag, then failed on its final remote digest verification. Cause: SHA256SUMS.txt had Windows CRLF line endings and GNU sha256sum -c on Git Bash interpreted the CR as part of each filename. This did not itself indicate any hash mismatch; release asset metadata provides digests, but the remote checksum verification step failed. Do not rerun the existing tag or overwrite its assets. Release verification now strips CR from a downloaded *local copy* before checking; scripts/package_release.py emits LF endings for future assets. Current code version remains 1.7.0 because this change only repairs release automation/documentation.

A later v1.7.1 application release must be approved separately and incorporate newer main's updater fixes. To establish the first end-to-end version-to-version updater test, install the published v1.7.0 portable app first, then publish v1.7.1 from a newly versioned, validated source commit. Test update notification, explicit Download, SHA-256 verification, Install and restart, stable filename, settings preservation, rollback and healthy relaunch on Windows. No such v1.7.0-to-v1.7.1 test has occurred yet.

Updater manifest feed:
https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/latest/download/update-manifest.json

Hosted CI on the final source/doc fix commit must be checked before declaring these later automation changes validated.
## v1.7.1 update-test candidate

The user confirmed that the installed, published v1.7.0 application launches and works. v1.7.1 is a small visibly identifiable update, showing its version beside the main-window title. Source/project/Windows version metadata are all 1.7.1. All existing splitter and packaging features, icon, settings paths, and stable executable filename are preserved.

Native Windows CI run 41115966710 failed in the compiled updater tests. A diagnostic branch run 41117416383 confirmed that the compiled rollback test passed but the success tests left PyInstaller bootloader processes holding disposable test EXEs open. The test harness now terminates all test-owned processes, including the parent, and waits for the file to unlock. Updater rollback is also hardened with process/parent validation, a bounded restore retry, and an explicit retained-backup failure if restoration remains blocked. Compiled-test expectations use the candidate app version while synthetic fixtures continue to model 1.6.0 to 1.7.0.

These changes require fresh hosted Windows CI validation on the exact candidate commit before merge or publication. The initial published v1.7.0 updater predates improvements to quoted paths, process/health validation, and rollback. The real v1.7.0-to-v1.7.1 update must be tested on Windows and may require a manual portable replacement if the older helper fails, especially when account paths contain spaces. Do not claim that end-to-end upgrade is verified until the actual test succeeds.

After the development PR passes, merge without overwriting newer main work, verify CI on the exact merged commit, and publish a new distinct v1.7.1 release only with approval. Never overwrite the v1.7.0 release.
