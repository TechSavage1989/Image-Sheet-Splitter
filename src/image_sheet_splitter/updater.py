import hashlib
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .paths import downloads_dir, rollback_dir, staging_dir, update_state_path
from .version import (
    APP_ID,
    APP_NAME,
    APP_VERSION,
    MANIFEST_ASSET_NAME,
    PORTABLE_ASSET_KEY,
    PORTABLE_EXE_NAME,
    RELEASES_URL,
    UPDATE_MANIFEST_URL,
)

CHECK_INTERVAL_SECONDS = 300
FOCUS_RECHECK_SECONDS = 120
MANUAL_COOLDOWN_SECONDS = 15
HTTP_TIMEOUT_SECONDS = 10
MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 900 * 1024 * 1024
MAX_FILE_COUNT = 200
MAX_COMPRESSION_RATIO = 250

_ALLOWED_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


@dataclass
class UpdateResult:
    status: str
    installed_version: str
    latest_version: str = ""
    message: str = ""
    notes: tuple = ()
    read_more_url: str = ""
    asset_name: str = ""
    asset_url: str = ""
    asset_sha256: str = ""
    asset_size: int = 0
    cached: bool = False
    retry_after_seconds: int = 0

    @property
    def available(self):
        return self.status == "available"


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        ensure_allowed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ensure_allowed_url(url):
    parsed = urllib.parse.urlparse(str(url))
    if parsed.scheme.lower() != "https":
        raise ValueError("Update URLs must use HTTPS.")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise ValueError(f"Update URL host is not approved: {host or '(missing host)'}")
    return str(url)


def _parse_version(value):
    text = str(value or "").strip()
    if text.startswith("v"):
        text = text[1:]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[.-]([0-9A-Za-z.-]+))?", text)
    if not match:
        raise ValueError(f"Unsupported version format: {value}")
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    suffix = match.group(4)
    stable_rank = 1 if suffix is None else 0
    return major, minor, patch, stable_rank, suffix or ""


def is_newer_version(candidate, installed):
    c = _parse_version(candidate)
    i = _parse_version(installed)
    if c[:3] != i[:3]:
        return c[:3] > i[:3]
    if c[3] != i[3]:
        return c[3] > i[3]
    return c[4] > i[4]


def _atomic_json_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _load_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {} if fallback is None else fallback


def _retry_after_seconds(headers, default=300):
    value = headers.get("Retry-After") if headers else None
    if value:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            pass
    reset = headers.get("X-RateLimit-Reset") if headers else None
    if reset:
        try:
            return max(1, int(float(reset) - time.time()))
        except (TypeError, ValueError):
            pass
    return default


def _build_opener():
    context = ssl.create_default_context()
    https = urllib.request.HTTPSHandler(context=context)
    return urllib.request.build_opener(SafeRedirectHandler(), https)


def _request_json(url, etag=None, timeout=HTTP_TIMEOUT_SECONDS):
    ensure_allowed_url(url)
    headers = {
        "User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    }
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = _build_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            ensure_allowed_url(response.geturl())
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError("Update manifest is unexpectedly large.")
            payload = json.loads(raw.decode("utf-8"))
            return payload, response.headers.get("ETag"), False
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, etag, True
        raise


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("Update manifest is not a JSON object.")
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported update manifest schema.")
    if manifest.get("app_id") != APP_ID:
        raise ValueError("Update manifest is for a different application.")
    version = str(manifest.get("version", "")).strip()
    _parse_version(version)
    if bool(manifest.get("prerelease", False)):
        raise ValueError("Stable updater will not install prerelease manifests.")
    release_url = ensure_allowed_url(manifest.get("release_url", ""))
    notes = manifest.get("notes") or []
    if not isinstance(notes, list):
        raise ValueError("Update notes must be a list.")
    notes = tuple(str(item).strip() for item in notes if str(item).strip())[:5]
    assets = manifest.get("assets")
    if not isinstance(assets, dict) or PORTABLE_ASSET_KEY not in assets:
        raise ValueError("Windows portable update asset is missing from the manifest.")
    asset = assets[PORTABLE_ASSET_KEY]
    if not isinstance(asset, dict):
        raise ValueError("Windows portable update asset is invalid.")
    name = str(asset.get("name", "")).strip()
    if not name.lower().endswith(".zip") or any(char in name for char in '/\\:') or name != name.rstrip(' .'):
        raise ValueError("Portable update asset must be a ZIP archive.")
    asset_url = ensure_allowed_url(asset.get("url", ""))
    digest = str(asset.get("sha256", "")).lower().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Portable update asset SHA-256 is invalid.")
    size = int(asset.get("size", 0) or 0)
    if size <= 0 or size > MAX_ARCHIVE_BYTES:
        raise ValueError("Portable update asset size is invalid.")
    entry_exe = str(asset.get("entry_exe", "")).replace("\\", "/").strip("/")
    if not entry_exe or PurePosixPath(entry_exe).name != PORTABLE_EXE_NAME:
        raise ValueError("Portable update manifest has the wrong application executable.")
    return {
        "version": version,
        "release_url": release_url,
        "notes": notes,
        "read_more_url": ensure_allowed_url(manifest.get("read_more_url") or release_url),
        "asset_name": name,
        "asset_url": asset_url,
        "asset_sha256": digest,
        "asset_size": size,
        "entry_exe": entry_exe,
    }


def _safe_zip_member(info):
    normalized = info.filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {info.filename}")
    # Windows drive paths, alternate data streams and normalized aliases must not
    # escape the staging directory or overwrite a different member on extraction.
    if any(":" in part or part != part.rstrip(" .") for part in path.parts):
        raise ValueError(f"Unsafe Windows archive path: {info.filename}")
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and (mode & 0o170000) == 0o120000:
        raise ValueError(f"Symbolic links are not allowed in updates: {info.filename}")
    return path


def validate_pe_header(path):
    path = Path(path)
    with path.open("rb") as fh:
        header = fh.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise ValueError("Downloaded application does not have a valid Windows PE header.")
        pe_offset = int.from_bytes(header[60:64], "little")
        if pe_offset <= 0 or pe_offset > 16 * 1024 * 1024:
            raise ValueError("Downloaded application has an invalid PE offset.")
        fh.seek(pe_offset)
        if fh.read(4) != b"PE\0\0":
            raise ValueError("Downloaded application does not contain a valid PE signature.")


def _windows_version_value(path, key):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    translation_ptr = ctypes.c_void_p()
    translation_len = wintypes.UINT()
    if not version.VerQueryValueW(buffer, r"\VarFileInfo\Translation", ctypes.byref(translation_ptr), ctypes.byref(translation_len)):
        return None
    if translation_len.value < 4:
        return None
    language, codepage = ctypes.cast(translation_ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
    query = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{key}"
    value_ptr = ctypes.c_void_p()
    value_len = wintypes.UINT()
    if not version.VerQueryValueW(buffer, query, ctypes.byref(value_ptr), ctypes.byref(value_len)):
        return None
    return ctypes.wstring_at(value_ptr, max(0, value_len.value - 1))


def validate_windows_identity(path, expected_version):
    validate_pe_header(path)
    if os.name != "nt":
        return False
    product = _windows_version_value(path, "ProductName")
    file_version = _windows_version_value(path, "FileVersion")
    if product != APP_NAME:
        raise ValueError(f"Downloaded executable identity is wrong: {product or 'unknown product'}")
    if file_version != expected_version:
        raise ValueError(f"Downloaded executable version is wrong: {file_version or 'unknown version'}")
    return True


class UpdateManager:
    def __init__(self, installed_version=APP_VERSION):
        self.installed_version = installed_version
        self.state_path = update_state_path()
        self._lock = threading.Lock()
        self._inflight = False
        self._state = _load_json(self.state_path, {})

    @property
    def inflight(self):
        return self._inflight

    def _save_state(self):
        try:
            _atomic_json_write(self.state_path, self._state)
        except OSError:
            pass

    def check(self, manual=False):
        with self._lock:
            if self._inflight:
                return UpdateResult("busy", self.installed_version, message="An update check is already running.")
            self._inflight = True
        try:
            now = time.time()
            backoff_until = float(self._state.get("backoff_until", 0) or 0)
            if backoff_until > now:
                remaining = max(1, int(backoff_until - now))
                return UpdateResult(
                    "throttled",
                    self.installed_version,
                    message=f"Update checks are temporarily paused. Try again in about {remaining} seconds.",
                    retry_after_seconds=remaining,
                )

            etag = str(self._state.get("etag", "") or "")
            try:
                payload, new_etag, not_modified = _request_json(UPDATE_MANIFEST_URL, etag=etag)
                if not_modified:
                    payload = self._state.get("manifest")
                    if not isinstance(payload, dict):
                        payload, new_etag, _ = _request_json(UPDATE_MANIFEST_URL, etag=None)
                parsed = validate_manifest(payload)
                self._state.update({
                    "etag": new_etag or etag,
                    "manifest": payload,
                    "last_success": now,
                    "last_error": "",
                    "backoff_until": 0,
                })
                self._save_state()
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    self._state.update({"last_error": "No stable release is published.", "backoff_until": 0})
                    self._save_state()
                    return UpdateResult("no_release", self.installed_version, message="No stable release is published yet.")
                if exc.code in (403, 429, 503):
                    retry = _retry_after_seconds(exc.headers)
                    self._state.update({"last_error": f"HTTP {exc.code}", "backoff_until": now + retry})
                    self._save_state()
                    return UpdateResult(
                        "throttled",
                        self.installed_version,
                        message=f"The update service asked the app to slow down. Try again in about {retry} seconds.",
                        retry_after_seconds=retry,
                    )
                self._state.update({"last_error": f"HTTP {exc.code}"})
                self._save_state()
                return UpdateResult("error", self.installed_version, message=f"Update check failed with HTTP {exc.code}.")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._state.update({"last_error": str(exc)})
                self._save_state()
                return UpdateResult("error", self.installed_version, message="Unable to reach the update service. Your installed version was not changed.")
            except (ValueError, json.JSONDecodeError, TypeError) as exc:
                self._state.update({"last_error": str(exc)})
                self._save_state()
                return UpdateResult("error", self.installed_version, message=f"The update information was rejected: {exc}")

            if is_newer_version(parsed["version"], self.installed_version):
                return UpdateResult(
                    "available",
                    self.installed_version,
                    latest_version=parsed["version"],
                    notes=parsed["notes"],
                    read_more_url=parsed["read_more_url"],
                    asset_name=parsed["asset_name"],
                    asset_url=parsed["asset_url"],
                    asset_sha256=parsed["asset_sha256"],
                    asset_size=parsed["asset_size"],
                )
            return UpdateResult(
                "current",
                self.installed_version,
                latest_version=parsed["version"],
                message=f"{APP_NAME} {self.installed_version} is the latest stable version.",
            )
        finally:
            with self._lock:
                self._inflight = False

    def download_and_stage(self, result, progress=None):
        if not result or not result.available:
            raise ValueError("No downloadable update is selected.")
        ensure_allowed_url(result.asset_url)
        download_root = downloads_dir()
        stage_root = staging_dir() / result.latest_version
        download_root.mkdir(parents=True, exist_ok=True)
        if stage_root.exists():
            shutil.rmtree(stage_root, ignore_errors=True)
        stage_root.mkdir(parents=True, exist_ok=True)

        destination = download_root / result.asset_name
        temp = destination.with_suffix(destination.suffix + ".part")
        if temp.exists():
            temp.unlink()

        request = urllib.request.Request(
            result.asset_url,
            headers={"User-Agent": f"{APP_NAME.replace(' ', '-')}/{APP_VERSION}", "Accept": "application/octet-stream"},
            method="GET",
        )
        opener = _build_opener()
        digest = hashlib.sha256()
        received = 0
        with opener.open(request, timeout=30) as response, temp.open("wb") as fh:
            ensure_allowed_url(response.geturl())
            length = response.headers.get("Content-Length")
            if length:
                declared = int(length)
                if declared > MAX_ARCHIVE_BYTES:
                    raise ValueError("Update archive is too large.")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_ARCHIVE_BYTES:
                    raise ValueError("Update archive exceeded the maximum allowed size.")
                digest.update(chunk)
                fh.write(chunk)
                if progress:
                    progress(received, result.asset_size)

        if result.asset_size and received != result.asset_size:
            temp.unlink(missing_ok=True)
            raise ValueError(f"Update download size mismatch: expected {result.asset_size}, received {received}.")
        actual_hash = digest.hexdigest().lower()
        if actual_hash != result.asset_sha256.lower():
            temp.unlink(missing_ok=True)
            raise ValueError("Update SHA-256 verification failed.")
        os.replace(temp, destination)

        exe_path = self._validate_and_extract_archive(destination, stage_root, result.latest_version)
        return {
            "version": result.latest_version,
            "archive": str(destination),
            "stage_root": str(stage_root),
            "exe": str(exe_path),
            "identity_verified": os.name == "nt",
        }

    def _validate_and_extract_archive(self, archive, stage_root, expected_version):
        total = 0
        exe_members = []
        with zipfile.ZipFile(archive, "r") as zf:
            infos = zf.infolist()
            if not infos or len(infos) > MAX_FILE_COUNT:
                raise ValueError("Update archive has an invalid file count.")
            for info in infos:
                path = _safe_zip_member(info)
                if info.is_dir():
                    continue
                total += info.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Update archive expands beyond the allowed size.")
                if info.compress_size == 0 and info.file_size > 0:
                    ratio = float("inf")
                elif info.file_size == 0:
                    ratio = 1
                else:
                    ratio = info.file_size / max(1, info.compress_size)
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ValueError("Update archive has a suspicious compression ratio.")
                if path.suffix.lower() == ".exe":
                    exe_members.append((info, path))
            if len(exe_members) != 1 or exe_members[0][1].name != PORTABLE_EXE_NAME:
                raise ValueError("Update archive contains an unexpected executable set.")

            for info in infos:
                path = _safe_zip_member(info)
                target = stage_root.joinpath(*path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)

        exe_path = stage_root.joinpath(*exe_members[0][1].parts)
        validate_windows_identity(exe_path, expected_version)
        return exe_path

    def make_install_plan(self, staged):
        if not getattr(sys, "frozen", False):
            raise RuntimeError("Install and restart is available only from the packaged Windows executable.")
        current_exe = Path(sys.executable).resolve()
        target_exe = current_exe
        if current_exe.name.lower() == "sprite sheet splitter.exe":
            target_exe = current_exe.with_name(PORTABLE_EXE_NAME)

        rollback_root = rollback_dir()
        rollback_root.mkdir(parents=True, exist_ok=True)
        backup = rollback_root / "previous.exe"
        health = staging_dir() / "post-update-health.json"
        plan_path = staging_dir() / "install-plan.json"
        plan = {
            "old_pid": os.getpid(),
            "old_exe": str(current_exe),
            "target_exe": str(target_exe),
            "staged_exe": str(Path(staged["exe"]).resolve()),
            "stage_root": str(Path(staged["stage_root"]).resolve()),
            "archive": str(Path(staged["archive"]).resolve()),
            "backup_exe": str(backup.resolve()),
            "health_marker": str(health.resolve()),
            "from_version": self.installed_version,
            "to_version": staged["version"],
            "health_token": secrets.token_hex(32),
        }
        # Start-Process joins array arguments without Windows command-line quoting.
        # Construct one correctly quoted command line before crossing into PowerShell.
        plan["launch_arguments"] = subprocess.list2cmdline([
            "--post-update-health", str(health.resolve()),
            "--post-update-from", self.installed_version,
            "--post-update-plan", str(plan_path.resolve()),
            "--post-update-token", plan["health_token"],
        ])
        _atomic_json_write(plan_path, plan)
        return plan_path

    def launch_install_helper(self, plan_path):
        if os.name != "nt":
            raise RuntimeError("Install and restart is supported only on Windows.")
        script = r'''$ErrorActionPreference = 'Stop';
$plan = Get-Content -Raw -LiteralPath $env:ISS_UPDATE_PLAN | ConvertFrom-Json;
$deadline = (Get-Date).AddSeconds(120);
while ((Get-Date) -lt $deadline) {
  if (-not (Get-Process -Id ([int]$plan.old_pid) -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 250
}
if (Get-Process -Id ([int]$plan.old_pid) -ErrorAction SilentlyContinue) { exit 20 }
$tempTarget = $plan.target_exe + '.update-' + $plan.health_token + '.new';
$tempBackup = $plan.backup_exe + '.new';
$replaced = $false;
$proc = $null;
try {
  if (($plan.old_exe -ne $plan.target_exe) -and (Test-Path -LiteralPath $plan.target_exe)) { throw 'The stable target executable already exists; refusing to overwrite it.' }
  $backupDir = Split-Path -Parent $plan.backup_exe;
  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null;
  Copy-Item -LiteralPath $plan.old_exe -Destination $tempBackup -Force;
  Move-Item -LiteralPath $tempBackup -Destination $plan.backup_exe -Force;
  Copy-Item -LiteralPath $plan.staged_exe -Destination $tempTarget -Force;
  if ($plan.old_exe -eq $plan.target_exe) {
    [System.IO.File]::Replace($tempTarget, $plan.target_exe, [NullString]::Value);
  } else {
    # File.Move refuses a collision that appears after the initial check.
    [System.IO.File]::Move($tempTarget, $plan.target_exe);
  }
  $replaced = $true;
  if (Test-Path -LiteralPath $plan.health_marker) { Remove-Item -LiteralPath $plan.health_marker -Force }
  $proc = Start-Process -FilePath $plan.target_exe -ArgumentList $plan.launch_arguments -PassThru;
  $healthDeadline = (Get-Date).AddSeconds(45);
  $healthy = $false;
  while ((Get-Date) -lt $healthDeadline) {
    if (Test-Path -LiteralPath $plan.health_marker) {
      try {
        $health = Get-Content -Raw -LiteralPath $plan.health_marker | ConvertFrom-Json;
        $healthProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$health.pid);
        # A PyInstaller one-file app reports from its child, not its bootloader PID.
        $launchedProcess = $healthProcess -and (($healthProcess.ProcessId -eq $proc.Id) -or ($healthProcess.ParentProcessId -eq $proc.Id));
        $healthy = ($health.status -ceq 'healthy') -and ($health.version -ceq $plan.to_version) -and ($health.token -ceq $plan.health_token) -and ($health.executable -eq $plan.target_exe) -and $launchedProcess -and ($healthProcess.ExecutablePath -eq $plan.target_exe) -and (-not $proc.HasExited);
      } catch { $healthy = $false }
      if (-not $healthy) { throw 'The updated application returned an invalid health response.' }
      break
    }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 300
  }
  if (-not $healthy) { throw 'The updated application did not report a healthy visible window.' }
  if (($plan.old_exe -ne $plan.target_exe) -and (Test-Path -LiteralPath $plan.old_exe)) { Remove-Item -LiteralPath $plan.old_exe -Force }
  exit 0
} catch {
  [Console]::Error.WriteLine($_.Exception.ToString());
  if ($proc) {
    # Only terminate a reported child when its image and parent belong to
    # the application launched by this particular update attempt.
    if (Test-Path -LiteralPath $plan.health_marker) {
      try {
        $candidate = Get-Content -Raw -LiteralPath $plan.health_marker | ConvertFrom-Json;
        $candidatePid = [int]$candidate.pid;
        $child = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $candidatePid) -ErrorAction Stop;
        if ($child -and ($child.ExecutablePath -eq $plan.target_exe) -and
            (($child.ParentProcessId -eq $proc.Id) -or ($child.ProcessId -eq $proc.Id))) {
          & "$env:SystemRoot\System32\taskkill.exe" /PID $candidatePid /T /F 2>$null | Out-Null;
        }
      } catch { }
    }
    if (-not $proc.HasExited) {
      try { & "$env:SystemRoot\System32\taskkill.exe" /PID $proc.Id /T /F 2>$null | Out-Null } catch { }
    }
    try { $proc.WaitForExit(10000) | Out-Null } catch { }
  }
  if ($replaced) {
    # A killed PyInstaller child can briefly leave the image file locked.
    $restored = $false;
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
      try {
        if (($plan.old_exe -ne $plan.target_exe) -and (Test-Path -LiteralPath $plan.target_exe)) {
          Remove-Item -LiteralPath $plan.target_exe -Force -ErrorAction Stop;
        }
        Copy-Item -LiteralPath $plan.backup_exe -Destination $plan.old_exe -Force -ErrorAction Stop;
        $restored = $true;
        break;
      } catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $restored) {
      [Console]::Error.WriteLine('Rollback backup retained, but the executable is still locked.');
      exit 31;
    }
  }
  try {
    Start-Process -FilePath $plan.old_exe -ArgumentList '--post-update-rollback "The update could not be verified or installed. The previous application was kept or restored."' | Out-Null;
  } catch {
    [Console]::Error.WriteLine('Previous executable was restored but could not be relaunched.');
    exit 32;
  }
  exit 30
} finally {
  Remove-Item -LiteralPath $tempTarget, $tempBackup -Force -ErrorAction SilentlyContinue;
}'''
        env = os.environ.copy()
        env["ISS_UPDATE_PLAN"] = str(plan_path)
        creationflags = 0x08000000 if os.name == "nt" else 0
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            env=env,
            creationflags=creationflags,
            close_fds=True,
        )
        try:
            plan = _load_json(plan_path, {})
            plan["helper_pid"] = int(process.pid)
            _atomic_json_write(plan_path, plan)
        except (OSError, TypeError, ValueError):
            pass
        return process.pid


def create_release_manifest(version, asset_name, asset_sha256, asset_size, notes):
    tag = f"v{version}"
    release_url = f"https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/tag/{tag}"
    asset_url = f"https://github.com/TechSavage1989/Image-Sheet-Splitter/releases/download/{tag}/{asset_name}"
    return {
        "schema": 1,
        "app_id": APP_ID,
        "version": version,
        "prerelease": False,
        "release_url": release_url,
        "read_more_url": release_url,
        "notes": list(notes),
        "assets": {
            PORTABLE_ASSET_KEY: {
                "name": asset_name,
                "url": asset_url,
                "sha256": asset_sha256,
                "size": int(asset_size),
                "entry_exe": f"Image Sheet Splitter/{PORTABLE_EXE_NAME}",
            }
        },
        "hash_notice": "SHA-256 verifies the downloaded asset bytes. It does not prove publisher code signing.",
        "releases_index": RELEASES_URL,
        "manifest_asset": MANIFEST_ASSET_NAME,
    }
