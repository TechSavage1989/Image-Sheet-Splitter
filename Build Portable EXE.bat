@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Image Sheet Splitter - Portable EXE Builder

set "VENV=.build-venv"
set "PYTHON=%VENV%\Scripts\python.exe"

where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3"
    goto :python_found
)
where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
    goto :python_found
)

echo ERROR: Python 3 was not found.
echo Install a supported 64-bit Python 3 version, then run this file again.
exit /b 1

:python_found
%PY% -c "import sys,struct; ok=(sys.version_info.major==3 and sys.version_info.minor in (10,11,12,13,14,15) and struct.calcsize('P')*8==64); print('Python',sys.version.split()[0]); raise SystemExit(0 if ok else 1)"
if errorlevel 1 (
    echo ERROR: This build requires 64-bit Python 3.10 through 3.15.
    exit /b 1
)

if not exist "%PYTHON%" (
    %PY% -m venv "%VENV%" || goto :failed
)

"%PYTHON%" -m pip install --upgrade pip || goto :failed
"%PYTHON%" -m pip install -r requirements-build.txt || goto :failed
"%PYTHON%" scripts\check_root.py || goto :failed
"%PYTHON%" -m unittest discover -s tests -v || goto :failed
"%PYTHON%" scripts\write_version_info.py || goto :failed

"%PYTHON%" scripts\generate_icon.py || goto :failed

if exist build-output rmdir /s /q build-output
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release

"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build-output build\windows\Image_Sheet_Splitter.spec || goto :failed
if not exist "dist\Image Sheet Splitter.exe" goto :failed

"%PYTHON%" scripts\verify_windows_build.py "dist\Image Sheet Splitter.exe" || goto :failed
set "ISS_TEST_COMPILED_EXE=%CD%\dist\Image Sheet Splitter.exe"
"%PYTHON%" -m unittest discover -s tests -p test_windows_updater.py -k test_compiled_app -v || goto :failed
set "ISS_TEST_COMPILED_EXE="
"%PYTHON%" scripts\package_release.py --exe "dist\Image Sheet Splitter.exe" || goto :failed
"%PYTHON%" scripts\verify_release.py || goto :failed

echo.
echo BUILD COMPLETE
echo Portable executable: dist\Image Sheet Splitter.exe
echo Release assets: release\
start "" release
exit /b 0

:failed
echo.
echo BUILD FAILED
exit /b 1
