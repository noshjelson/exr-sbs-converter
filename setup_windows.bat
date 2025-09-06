@echo off
echo SBS EXR Converter - Windows Setup
echo =================================
echo.

echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo Python found! Installing Python dependencies...
pip install -r requirements.txt

echo.
echo Checking for OpenImageIO tools...
python -c "import subprocess, os, shutil; print('oiiotool found!' if shutil.which('oiiotool') or shutil.which('oiiotool.exe') else 'oiiotool not found')"

echo.
echo Setup complete! You can now run:
echo   - sbs_gui.py (for GUI)
echo   - Convert-SBS-Interactive.ps1 (for PowerShell GUI)
echo   - Convert-SBS-CLI.ps1 (for command line)
echo.
echo If you get "oiiotool not found" errors, you'll need to install OpenImageIO.
echo See the README for detailed instructions.
echo.
pause
