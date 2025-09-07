# SBS EXR Converter - Easy Fix for Unreal Engine Panoramas

## 🎯 What This Tool Does (In Simple Terms)

**The Problem:** When you render panoramic (360°) videos in Unreal Engine, sometimes only half the image shows up in video editors like After Effects or Premiere Pro. This happens because the file format is confused about how big the image should be.

**The Solution:** This tool fixes those files so you can see the full panoramic image everywhere.

## 🚀 Quick Start (Easiest Method)

### Option 1: Automatic Setup (Recommended for Beginners) ⭐

**Step 1:** Download Python
- Go to [python.org](https://www.python.org/downloads/)
- Download Python 3.8 or newer
- **IMPORTANT:** During installation, check "Add Python to PATH"

**Step 2:** Download This Tool
- Download all files from this project
- Put them in a folder (like `C:\SBS-Converter\`)

**Step 3:** Run Automatic Setup
- Double-click `setup_windows.bat`
- Wait for it to install everything automatically
- If it says "oiiotool not found", see Option 2 below

**Step 4:** Start Converting
- Double-click `sbs_gui.py`
- Click "Select Shots Folder"
- Choose the folder containing your EXR files
- Select which shots to convert
- Click "Convert Selected"
- Wait for it to finish!

### Option 2: PowerShell Scripts (Most Reliable) 🔧

**If the Python GUI doesn't work - uses built-in Windows tools**

1. **Download This Tool** - Get all files from this project
2. **Install OpenImageIO** - See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed instructions
3. **Run the Tool** - Right-click `Convert-SBS-Interactive.ps1` → "Run with PowerShell"

### Option 3: Pre-built Executable (Coming Soon)

We're working on a single `.exe` file that includes everything. No installation needed - just download and run!

## 📚 Need More Help?

- **Complete Setup Guide:** See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed instructions
- **Troubleshooting:** Common problems and solutions are covered in the setup guide
- **Multiple Methods:** If one approach doesn't work, try another!

## 📁 What You Need

### Your Files
- EXR files from Unreal Engine (the ones that only show half the image)
- Put them in folders (one folder per "shot" or scene)

### Your Computer
- Windows 10 or 11
- At least 4GB of free disk space
- Internet connection (for downloading tools)

## 🔧 Advanced Setup (If You Want to Understand)

### What Each Tool Does

**`sbs_gui.py`** - The main program with a visual interface
- Shows you all your shots
- Lets you pick which ones to convert
- Shows progress bars
- Easiest to use

**`Convert-SBS-Interactive.ps1`** - PowerShell version with file picker
- Same as above but uses Windows file dialogs
- Might crash on some computers

**`Convert-SBS-CLI.ps1`** - Command-line version
- For people who like typing commands
- More reliable but harder to use

### Technical Requirements

The tool needs these programs to work:
- **Python 3.8+** (for the GUI)
- **OpenImageIO** (for processing EXR files)

## 📖 How to Use (Step by Step)

### Using the Python GUI

1. **Start the Program**
   - Double-click `sbs_gui.py`
   - A window should open

2. **Load Your Shots**
   - Click "Select Shots Folder"
   - Navigate to where your EXR files are
   - Select the folder and click "OK"

3. **Choose What to Convert**
   - You'll see a list of your shots (use the mouse wheel to scroll)
   - Check the boxes next to shots you want to convert
   - Shots already converted will be grayed out

4. **Set Options (Optional)**
   - **Compression:** Leave as "dwab:45" (good balance of quality and file size)
   - **Pixel Type:** Leave as "float" (best quality)

5. **Convert**
   - Click "Convert Selected"
   - Watch the progress bars with estimated time remaining and CPU thread usage
   - Wait for "All conversions complete" message
   - The tool processes multiple frames in parallel, using all available CPU cores

6. **Find Your Results**
   - Look for new folders named `[YourShotName]_SBS`
   - These contain your fixed EXR files

### Using PowerShell Scripts

1. **Right-click** on `Convert-SBS-Interactive.ps1`
2. **Select** "Run with PowerShell"
3. **Choose** your shots folder when prompted
4. **Wait** for conversion to complete

## 🎛️ Settings Explained

### Compression Options
- **dwab:45** - Good quality, smaller files (recommended)
- **dwaa:45** - Similar to dwab, slightly different algorithm
- **zip** - No quality loss, larger files, faster to open in some programs
- **none** - No compression, huge files, fastest to process

### Pixel Type
- **float** - Best quality, larger files (recommended)
- **half** - Good quality, smaller files

## 📂 What Gets Created

### Output Files
- **Location:** New folders next to your original shots
- **Name:** `[OriginalFolderName]_SBS`
- **Files:** `[OriginalFileName]_SBS.exr`

### Example
```
Your Shots/
├── Shot_001/           (original)
│   ├── frame_001.exr
│   └── frame_002.exr
└── Shot_001_SBS/       (created by tool)
    ├── frame_001_SBS.exr
    └── frame_002_SBS.exr
```

## 🛠️ Troubleshooting

### "Python not found" or "Can't run sbs_gui.py"
- **Solution:** Install Python and make sure to check "Add Python to PATH" during installation
- **Alternative:** Use the PowerShell scripts instead

### "oiiotool executable not found"
- **Solution:** The tool needs OpenImageIO installed
- **Quick fix:** Use the PowerShell scripts (they handle this automatically)
- **Manual fix:** Install vcpkg and OpenImageIO (see Advanced Setup below)

### "Nothing to convert" or "No shots selected"
- **Solution:** Make sure you selected a folder that contains EXR files
- **Check:** Look for files ending in `.exr` in your selected folder

### Tool crashes or freezes
- **Solution:** Try the PowerShell version instead
- **Alternative:** Use the command-line version

### Files are still showing only half the image
- **Check:** Make sure you're using the `_SBS.exr` files, not the originals
- **Verify:** The new files should be in folders ending with `_SBS`

## 🔧 Advanced Setup (For Technical Users)

### Installing OpenImageIO (Required for Python GUI)

1. **Install Git** (if not already installed)
   - Download from [git-scm.com](https://git-scm.com/download/win)

2. **Install vcpkg**
   ```cmd
   git clone https://github.com/microsoft/vcpkg.git "%USERPROFILE%\vcpkg"
   cd "%USERPROFILE%\vcpkg"
   .\bootstrap-vcpkg.bat
   ```

3. **Install OpenImageIO**
   ```cmd
   .\vcpkg install openimageio[tools] --recurse
   ```

4. **Test the GUI**
   - Run `sbs_gui.py` again
   - It should now find the required tools

### Command Line Usage

For advanced users who prefer typing commands:

```powershell
# Convert a single shot
powershell -NoLogo -ExecutionPolicy Bypass -File "Convert-SBS-CLI.ps1" -InputDirs "C:\Your\Shot\Folder"

# Convert multiple shots
powershell -NoLogo -ExecutionPolicy Bypass -File "Convert-SBS-CLI.ps1" -InputDirs "C:\Shot1","C:\Shot2"

# Convert with custom settings
powershell -NoLogo -ExecutionPolicy Bypass -File "Convert-SBS-CLI.ps1" -InputDirs "C:\Your\Shot" -Compression zip -DataType half
```

## ❓ Frequently Asked Questions

**Q: Do I need to know programming to use this?**
A: No! Just download Python and double-click the GUI file.

**Q: Will this work with files from other programs besides Unreal?**
A: Yes, as long as the files have the same problem (half-width display window).

**Q: Does this change my original files?**
A: No! It creates new files with `_SBS` in the name. Your originals stay safe.

**Q: How long does conversion take?**
A: Depends on file size and number of files. Usually a few seconds per frame.

**Q: What if I have thousands of files?**
A: The tool handles large batches. Just select the folder and let it run.

**Q: Can I use this on a Mac or Linux?**
A: The Python GUI should work, but you'll need to install OpenImageIO differently.

## 📞 Getting Help

If you run into problems:

1. **Check this README** - Most issues are covered here
2. **Try the PowerShell version** - It's more reliable than the Python GUI
3. **Check your files** - Make sure you have EXR files in the folder you selected
4. **Restart** - Close everything and try again

## 🎉 Success!

Once everything is working, you should see:
- New folders with `_SBS` in the name
- EXR files that show the full panoramic image
- Files that work properly in After Effects, Premiere, and other video editors

Enjoy your fixed panoramic renders! 🌟