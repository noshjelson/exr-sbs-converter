#!/usr/bin/env python3
"""
Build script for creating a standalone executable of SBS EXR Converter.
This creates a single .exe file that includes all dependencies.

Usage:
    python build_executable.py

Requirements:
    pip install pyinstaller
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_pyinstaller():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        return True
    except ImportError:
        return False

def install_pyinstaller():
    """Install PyInstaller if not available."""
    print("Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build_executable():
    """Build the standalone executable."""
    print("Building SBS EXR Converter executable...")
    
    # PyInstaller command
    cmd = [
        "pyinstaller",
        "--onefile",                    # Single executable file
        "--windowed",                   # No console window
        "--name=SBS-EXR-Converter",     # Output name
        "--icon=icon.ico",              # Icon (if available)
        "--add-data=requirements.txt;.", # Include requirements
        "--hidden-import=tkinter",      # Ensure tkinter is included
        "--hidden-import=tkinter.ttk",  # Ensure ttk is included
        "sbs_gui.py"                    # Main script
    ]
    
    # Remove icon parameter if icon doesn't exist
    if not os.path.exists("icon.ico"):
        cmd = [arg for arg in cmd if not arg.startswith("--icon")]
    
    try:
        subprocess.check_call(cmd)
        print("✅ Build successful!")
        print(f"📁 Executable created: dist/SBS-EXR-Converter.exe")
        print("\n🎉 You can now distribute the .exe file to users!")
        print("   No Python installation required on target machines.")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        return False
    
    return True

def create_installer_script():
    """Create a simple installer script."""
    installer_content = '''@echo off
echo SBS EXR Converter - Installer
echo =============================
echo.

echo Installing to Program Files...
if not exist "C:\\Program Files\\SBS-EXR-Converter" mkdir "C:\\Program Files\\SBS-EXR-Converter"

copy "SBS-EXR-Converter.exe" "C:\\Program Files\\SBS-EXR-Converter\\"
copy "README.md" "C:\\Program Files\\SBS-EXR-Converter\\"
copy "SETUP_GUIDE.md" "C:\\Program Files\\SBS-EXR-Converter\\"

echo Creating desktop shortcut...
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\SBS EXR Converter.lnk'); $Shortcut.TargetPath = 'C:\\Program Files\\SBS-EXR-Converter\\SBS-EXR-Converter.exe'; $Shortcut.Save()"

echo.
echo ✅ Installation complete!
echo 🎉 You can now run "SBS EXR Converter" from your desktop or Start menu.
echo.
pause
'''
    
    with open("install.bat", "w") as f:
        f.write(installer_content)
    
    print("📝 Created install.bat for easy distribution")

def main():
    """Main build process."""
    print("🔨 SBS EXR Converter - Build Script")
    print("=" * 40)
    
    # Check if PyInstaller is available
    if not check_pyinstaller():
        print("PyInstaller not found. Installing...")
        install_pyinstaller()
    
    # Build the executable
    if build_executable():
        create_installer_script()
        print("\n📦 Distribution package ready!")
        print("   Files to distribute:")
        print("   - dist/SBS-EXR-Converter.exe")
        print("   - install.bat")
        print("   - README.md")
        print("   - SETUP_GUIDE.md")
    else:
        print("\n❌ Build failed. Check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
