"""Real native helper tests in disposable folders; no published prior release exists."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from image_sheet_splitter import paths, updater


@unittest.skipUnless(os.name == "nt", "Requires native Windows processes and filesystem")
class WindowsUpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="ISS native fixture ")
        cls.prior = Path(cls.build.name) / "prior.exe"
        cls.candidate = Path(cls.build.name) / "candidate.exe"
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        for target, define in ((cls.prior, "/define:PRIOR"), (cls.candidate, "/define:CANDIDATE")):
            subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64",
                            "/reference:System.Web.Extensions.dll", define, f"/out:{target}",
                            str(ROOT / "tests/fixtures/update_app.cs")], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def run_install(self, name="Image Sheet Splitter.exe", mode="healthy", collision=False, compiled=None):
        with tempfile.TemporaryDirectory(prefix="ISS update path with spaces ") as tmp:
            root = Path(tmp)
            install = root / "Portable app [test]"
            install.mkdir()
            old = install / name
            shutil.copy2(self.prior, old)
            old_bytes = old.read_bytes()
            candidate = root / "Staged candidate.exe"
            shutil.copy2(compiled or self.candidate, candidate)
            target = install / "Image Sheet Splitter.exe" if collision else old
            if collision:
                target.write_bytes(b"unrelated existing target must survive")
            target_before = target.read_bytes()
            settings = root / "Custom settings.json"
            settings.write_text(json.dumps({
                "output_dir": str(root / "My output"), "open_export_folder": False,
                "tolerance": 17, "min_width": 13, "min_height": 11,
                "logging_enabled": False, "log_dir": str(root / "My logs"),
                "app_name": "Image Sheet Splitter", "app_version": "1.6.0",
            }))
            shortcut = root / "Existing shortcut.lnk"
            env = {
                "LOCALAPPDATA": str(root / "Local app data"),
                "ISS_TEST_MODE": mode,
                "ISS_TEST_ARGS": str(root / "arguments.json"),
                "ISS_TEST_ROLLBACK": str(root / "rollback.json"),
                "ISS_TEST_SHORTCUT": str(shortcut), "ISS_TEST_TARGET": str(old),
            }
            with mock.patch.dict(os.environ, env):
                paths.write_config_locator(settings)
                locator = paths.config_locator_path()
                subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ISS_TEST_SHORTCUT);"
                                "$s.TargetPath=$env:ISS_TEST_TARGET; $s.Save()"], check=True, capture_output=True)
                unchanged = {p: p.read_bytes() for p in (settings, locator, shortcut)}
                manager = updater.UpdateManager("1.6.0")
                with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", str(old)):
                    plan_path = manager.make_install_plan({"exe": candidate, "stage_root": root / "Staging area",
                                                          "archive": root / "Update archive.zip", "version": "1.7.0"})
                plan = json.loads(plan_path.read_text())
                # The real installed app has exited; use a PID that is no longer alive.
                plan["old_pid"] = 2147483647
                if compiled and mode == "version":
                    plan["to_version"] = "9.9.9"  # Force rejection of the actual app's health response.
                updater._atomic_json_write(plan_path, plan)
                backup = Path(plan["backup_exe"])
                backup.write_bytes(b"older rollback replaced only after preflight")
                prior_backup = backup.read_bytes()
                processes = []
                real_popen = subprocess.Popen
                helper_output = (root / "helper.log").open("wb")
                def capture(*args, **kwargs):
                    kwargs["stdout"] = helper_output
                    kwargs["stderr"] = subprocess.STDOUT
                    proc = real_popen(*args, **kwargs)
                    processes.append(proc)
                    return proc
                try:
                    with mock.patch.object(updater.subprocess, "Popen", side_effect=capture):
                        manager.launch_install_helper(plan_path)
                    code = processes[0].wait(timeout=70)
                    helper_output.flush()
                    output = (root / "helper.log").read_text(errors="replace")
                    if code not in (0, 30):
                        print(f"Unexpected update helper exit {code}; native helper log:\n{output}", file=sys.stderr, flush=True)
                    if mode == "healthy" and not collision:
                        self.assertEqual(code, 0, output)
                        self.assertEqual(old.read_bytes(), candidate.read_bytes())
                        self.assertEqual(backup.read_bytes(), old_bytes)
                        if not compiled:
                            args = json.loads(Path(env["ISS_TEST_ARGS"]).read_text())
                            self.assertEqual(args["--post-update-health"], plan["health_marker"])
                            self.assertEqual(args["--post-update-plan"], str(plan_path.resolve()))
                            self.assertEqual(args["--post-update-token"], plan["health_token"])
                        health = json.loads(Path(plan["health_marker"]).read_text())
                        self.assertEqual(health["version"], "1.7.0")
                        self.assertEqual(health["token"], plan["health_token"])
                    else:
                        self.assertEqual(code, 30, output)
                        self.assertEqual(old.read_bytes(), old_bytes)
                        if collision:
                            self.assertEqual(target.read_bytes(), target_before)
                            self.assertEqual(backup.read_bytes(), prior_backup)
                        else:
                            if not compiled:
                                self.assertTrue(Path(env["ISS_TEST_ARGS"]).is_file(), "Candidate never launched")
                            else:
                                self.assertTrue(Path(plan["health_marker"]).is_file(), "Compiled candidate never reported health")
                            self.assertEqual(backup.read_bytes(), old_bytes)
                        deadline = time.monotonic() + 10
                        while not Path(env["ISS_TEST_ROLLBACK"]).exists() and time.monotonic() < deadline:
                            time.sleep(0.1)
                        rollback_args = json.loads(Path(env["ISS_TEST_ROLLBACK"]).read_text())
                        self.assertEqual(len(rollback_args), 2)
                        self.assertEqual(rollback_args[0], "--post-update-rollback")
                        self.assertIn("previous application", rollback_args[1])
                    for path, content in unchanged.items():
                        if compiled and path == settings:
                            # Normal startup rewrites JSON formatting; all settings must survive.
                            expected = json.loads(content)
                            expected["app_version"] = "1.7.0"
                            self.assertEqual(json.loads(path.read_bytes()), expected)
                        else:
                            self.assertEqual(path.read_bytes(), content, str(path))
                    self.assertEqual(list(backup.parent.iterdir()), [backup])
                    self.assertFalse(list(install.glob("*.new")))
                finally:
                    helper_output.close()
                    # A PyInstaller one-file EXE has a parent bootloader and a
                    # separate child. Killing only the health-reporting child
                    # leaves the parent holding the image file on Windows.
                    # Scope cleanup strictly to this disposable test's EXE path.
                    cleanup_script = r"""
                    $target = [IO.Path]::GetFullPath($env:ISS_TEST_TARGET)
                    $deadline = (Get-Date).AddSeconds(20)
                    do {
                        $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                            Where-Object { $_.ExecutablePath -and
                                [string]::Equals($_.ExecutablePath, $target, [StringComparison]::OrdinalIgnoreCase) })
                        if ($running.Count -eq 0) { break }
                        foreach ($item in $running) {
                            & "$env:SystemRoot\\System32\\taskkill.exe" /PID $item.ProcessId /T /F 2>$null | Out-Null
                        }
                        Start-Sleep -Milliseconds 250
                    } while ((Get-Date) -lt $deadline)
                    """
                    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                                    "-Command", cleanup_script], capture_output=True, timeout=30)
                    # The rollback fixture can still be closing. On success,
                    # the application must no longer lock its temporary EXE.
                    health = updater._load_json(plan["health_marker"], {})
                    if health.get("pid"):
                        subprocess.run(["taskkill.exe", "/PID", str(health["pid"]), "/T", "/F"],
                                       capture_output=True)
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=10)
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        try:
                            with old.open("r+b"):
                                pass
                            break
                        except PermissionError:
                            time.sleep(0.25)
                    else:
                        self.fail(f"The disposable EXE remains locked after process cleanup: {old}")

    def test_success_preserves_generic_name_settings_and_shortcut(self):
        self.run_install()

    def test_success_preserves_custom_name_settings_and_shortcut(self):
        self.run_install(name="My custom splitter.exe")

    def test_failed_health_restores_previous_executable(self):
        self.run_install(mode="exit")

    def test_missing_health_times_out_and_rolls_back(self):
        self.run_install(mode="timeout")

    def test_wrong_version_token_pid_and_malformed_health_are_rejected(self):
        for mode in ("version", "token", "pid", "malformed"):
            with self.subTest(mode=mode):
                self.run_install(mode=mode)

    def test_collision_preserves_both_executables_and_existing_backup(self):
        self.run_install(name="Sprite Sheet Splitter.exe", collision=True)

    @unittest.skipUnless(os.environ.get("ISS_TEST_COMPILED_EXE"), "Run after building the portable executable")
    def test_compiled_app_reports_health_with_generic_and_custom_names(self):
        for name in ("Image Sheet Splitter.exe", "My custom splitter.exe"):
            with self.subTest(name=name):
                self.run_install(name=name, compiled=Path(os.environ["ISS_TEST_COMPILED_EXE"]))

    @unittest.skipUnless(os.environ.get("ISS_TEST_COMPILED_EXE"), "Run after building the portable executable")
    def test_compiled_app_failed_health_stops_child_and_restores_previous_exe(self):
        self.run_install(mode="version", compiled=Path(os.environ["ISS_TEST_COMPILED_EXE"]))


if __name__ == "__main__":
    unittest.main()
