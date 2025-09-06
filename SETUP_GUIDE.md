# 🚀 Complete Setup Guide for SBS EXR Converter

## TL;DR - Super Quick Start

1. **Download Python** from [python.org](https://www.python.org/downloads/)
2. **Download this tool** (all files)
3. **Double-click `setup_windows.bat`**
4. **Double-click `sbs_gui.py`**
5. **Done!**

---

## 📋 What You Need

### Required
- **Windows 10 or 11**
- **Internet connection** (for downloading tools)
- **4GB free disk space**

### Optional (for advanced users)
- **Git** (for manual OpenImageIO installation)
- **Visual Studio** (for compiling from source)

---

## 🎯 Three Ways to Get Started

### Method 1: Automatic Setup (Easiest) ⭐

**For absolute beginners - everything automated!**

1. **Install Python**
   - Go to [python.org/downloads](https://www.python.org/downloads/)
   - Download Python 3.8 or newer
   - **CRITICAL:** Check "Add Python to PATH" during installation
   - Click "Install Now"

2. **Download This Tool**
   - Download all files from this project
   - Put them in a folder (like `C:\SBS-Converter\`)

3. **Run Setup**
   - Double-click `setup_windows.bat`
   - Wait for it to finish
   - If it says "oiiotool not found", see Method 2

4. **Start Converting**
   - Double-click `sbs_gui.py`
   - Follow the on-screen instructions

### Method 2: PowerShell Scripts (Most Reliable) 🔧

**If the Python GUI doesn't work - uses built-in Windows tools**

1. **Download This Tool**
   - Get all files from this project

2. **Install OpenImageIO (Required)**
   - Open Command Prompt as Administrator
   - Copy and paste these commands one by one:
   ```cmd
   git clone https://github.com/microsoft/vcpkg.git "%USERPROFILE%\vcpkg"
   cd "%USERPROFILE%\vcpkg"
   .\bootstrap-vcpkg.bat
   .\vcpkg install openimageio[tools] --recurse
   ```

3. **Run the Tool**
   - Right-click `Convert-SBS-Interactive.ps1`
   - Select "Run with PowerShell"
   - Choose your EXR folder when prompted

### Method 3: Manual Installation (For Experts) 🛠️

**Full control over everything**

1. **Install Python 3.8+**
2. **Install Git**
3. **Install vcpkg and OpenImageIO** (see Method 2)
4. **Install Python dependencies:**
   ```cmd
   pip install -r requirements.txt
   ```
5. **Run the tool:**
   ```cmd
   python sbs_gui.py
   ```

---

## 🔍 Troubleshooting

### "Python not found" or "Can't run sbs_gui.py"

**Problem:** Python isn't installed or not in PATH

**Solutions:**
1. **Reinstall Python** - Make sure to check "Add Python to PATH"
2. **Use PowerShell version** - Right-click `Convert-SBS-Interactive.ps1` → "Run with PowerShell"
3. **Manual PATH fix** - Add Python to Windows PATH manually

### "oiiotool executable not found"

**Problem:** OpenImageIO tools aren't installed

**Solutions:**
1. **Use PowerShell version** - It handles this automatically
2. **Install OpenImageIO manually** (see Method 2 above)
3. **Use the bundled version** (coming soon)

### "Nothing to convert" or "No shots selected"

**Problem:** No EXR files found

**Solutions:**
1. **Check your folder** - Make sure it contains `.exr` files
2. **Check file names** - Files should end with `.exr`
3. **Try a different folder** - Test with a folder you know has EXR files

### Tool crashes or freezes

**Problem:** GUI issues or system conflicts

**Solutions:**
1. **Use PowerShell version** - More reliable
2. **Restart your computer** - Clear any system issues
3. **Check Windows updates** - Make sure you're up to date
4. **Try command-line version** - `Convert-SBS-CLI.ps1`

### "Access denied" or "Permission denied"

**Problem:** Windows security blocking the tool

**Solutions:**
1. **Run as Administrator** - Right-click → "Run as administrator"
2. **Check antivirus** - Temporarily disable if needed
3. **Move to different folder** - Try `C:\temp\` instead of Desktop

---

## 📁 File Structure After Setup

```
SBS-Converter/
├── sbs_gui.py                    # Main GUI program
├── Convert-SBS-Interactive.ps1   # PowerShell GUI
├── Convert-SBS-CLI.ps1          # Command-line version
├── requirements.txt              # Python dependencies
├── setup_windows.bat            # Automatic setup script
├── tools/                       # Downloaded tools (created automatically)
│   └── oiiotool.exe            # OpenImageIO tool (if downloaded)
└── README.md                    # This file
```

---

## 🎯 What Each File Does

| File | Purpose | Best For |
|------|---------|----------|
| `sbs_gui.py` | Visual interface with progress bars | Beginners, visual learners |
| `Convert-SBS-Interactive.ps1` | Windows file picker interface | Windows users, reliable |
| `Convert-SBS-CLI.ps1` | Command-line interface | Advanced users, automation |
| `setup_windows.bat` | Automatic setup script | First-time users |
| `requirements.txt` | Python dependencies list | Developers |

---

## 🚀 Next Steps

Once everything is working:

1. **Test with a small folder** - Try converting 1-2 EXR files first
2. **Check the results** - Look for `_SBS` folders with converted files
3. **Open in your video editor** - Verify the full panoramic image shows
4. **Convert your full project** - Process all your shots

---

## 💡 Pro Tips

- **Start small** - Test with a few files before processing hundreds
- **Keep backups** - The tool creates new files, but keep originals safe
- **Use consistent settings** - Pick compression/quality settings and stick with them
- **Monitor disk space** - EXR files can be large, especially with multiple subimages
- **Pause cloud sync** - Dropbox/OneDrive can interfere with file operations

---

## 🆘 Still Having Problems?

1. **Check this guide again** - Most issues are covered here
2. **Try Method 2** - PowerShell version is more reliable
3. **Check Windows version** - Tool works best on Windows 10/11
4. **Restart everything** - Close all programs and try again
5. **Ask for help** - Include error messages and what you tried

---

## 🎉 Success!

When everything works, you should see:
- ✅ Tool opens without errors
- ✅ Can select folders with EXR files
- ✅ Conversion completes successfully
- ✅ New `_SBS` folders appear
- ✅ Full panoramic images show in video editors

**Happy converting!** 🌟
