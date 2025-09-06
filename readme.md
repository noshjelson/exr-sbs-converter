\# SBS Fixer for Unreal Panoramic EXRs



\## What problem are we solving?



Unreal’s \*\*Panoramic Render Pass\*\* can output stereoscopic panoramas where the pixel \*\*dataWindow\*\* contains the full \*\*side-by-side (SBS)\*\* image, but the \*\*displayWindow\*\* is still half-width. Many viewers/compositors (AE, Premiere, DJV, Resolve) honor `displayWindow` — so they only show the \*\*left half\*\*, hiding the right eye. PNGs often appear fine, but EXRs don’t.



\*\*Goal:\*\* make SBS frames viewable everywhere \*\*without manually re-rendering\*\* or hand-fixing each frame.



\## What this tool does



\* Reads your EXR frames and writes a \*\*fixed\*\* EXR where `displayWindow == dataWindow` using `--fullpixels`.

\* Copies \*\*all subimages\*\* (depth, lighting, etc.) by default. Use `-FirstSubimage` to keep only the first pass.

\* Writes results into \*\*sibling\*\* folders named `<Shot>\_SBS`, mirroring any subfolders.

\* Lets you pick \*\*compression\*\* (`dwab`/`dwaa`/`zip`/`none`) and \*\*pixel data type\*\* (`float` or `half`).

\* Optional \*\*in-place\*\* mode: replaces originals safely (backs up as `.orig.exr`).



> Why not “just edit metadata”?

> In EXR, `displayWindow`/`dataWindow` affect how pixel data is interpreted on disk. Changing them safely requires a proper rewrite of the file header and, in practice, re-emitting the image. The reliable and portable fix is to \*\*rewrite\*\* with `--fullpixels`.



---



\## Scripts included



\* \*\*`Convert-SBS-CLI.ps1`\*\* — \*\*recommended\*\* (no GUI, won’t crash on STA/MTA issues)



&nbsp; \* Paste or pass one/more shot folders; shows \*\*overall\*\* + \*\*per-shot\*\* progress bars

&nbsp; \* Writes `<shot>\_SBS` by default; or `-InPlace` to overwrite

\* \*\*`Convert-SBS-Interactive.ps1`\*\* — optional GUI picker



&nbsp; \* Same behavior, but uses a folder picker (requires \*\*STA\*\*; may crash in some shells). Use only if you prefer a dialog.



> If you only need to process a \*\*single shot\*\*, see the “One-liner” in Examples.



---



\## Dependencies (Windows)



1\. \*\*vcpkg\*\* (package manager)



```powershell

git clone https://github.com/microsoft/vcpkg.git "$env:USERPROFILE\\vcpkg"

cd "$env:USERPROFILE\\vcpkg"

.\\bootstrap-vcpkg.bat

```



2\. \*\*OpenImageIO tools\*\* (provides `oiiotool.exe`)



```powershell

cd "$env:USERPROFILE\\vcpkg"

.\\vcpkg install openimageio\[tools] --recurse

```



3\. (Optional) \*\*OpenEXR tools\*\* (for `exrheader.exe` sanity checks)



```powershell

.\\vcpkg install openexr\[tools] --recurse

```



> The scripts auto-locate `oiiotool.exe` under `~\\vcpkg\\installed\\...`. If it’s elsewhere, pass `-OiiotoolPath` (Interactive script) or edit the variable in your one-liner.



---



\## Usage



\### A) Recommended: CLI tool (no GUI)



Run the script and \*\*paste paths\*\* when prompted:



```powershell

powershell -NoLogo -ExecutionPolicy Bypass -File "D:\\tools\\Convert-SBS-CLI.ps1"

```



Run with \*\*arguments\*\*:



```powershell

\# Single shot, recurse into subfolders, DWAB:45, float

powershell -NoLogo -ExecutionPolicy Bypass -File "D:\\tools\\Convert-SBS-CLI.ps1" `

&nbsp; -InputDirs "D:\\...\\Shots\\01ST\_0010\_009" -Recurse -Compression dwab -DwaLevel 45 -DataType float

```



Multiple shots:



```powershell

powershell -NoLogo -ExecutionPolicy Bypass -File "D:\\tools\\Convert-SBS-CLI.ps1" `

&nbsp; -InputDirs "D:\\...\\Shots\\01ST\_0010\_009","D:\\...\\Shots\\01ST\_0030\_015" -Recurse

```



\*\*In-place\*\* (overwrites originals, backups as `.orig.exr`):



```powershell

powershell -NoLogo -ExecutionPolicy Bypass -File "D:\\tools\\Convert-SBS-CLI.ps1" `

&nbsp; -InputDirs "D:\\...\\Shots\\01ST\_0010\_009" -InPlace -Compression dwab -DwaLevel 45 -DataType float

```



\*\*Flags\*\*



\* `-Compression`: `dwab` (default) | `dwaa` | `zip` | `none`

\* `-DwaLevel`: integer (typical \*\*35–55\*\*, default \*\*45\*\*) for DWAA/DWAB

\* `-DataType`: `float` (default) or `half`

\* `-Recurse`: include subfolders

\* `-InPlace`: overwrite originals (safe swap)



\### B) Optional: Interactive script with folder picker



If you prefer a dialog:



```powershell

\# Ensure STA (Windows PowerShell 5.1 or pass -STA to pwsh)

powershell -NoLogo -ExecutionPolicy Bypass -STA -File "D:\\tools\\Convert-SBS-Interactive.ps1"

```



Pick one or more shot folders. Progress bars will appear.



> If it crashes instantly, use the \*\*CLI\*\* version above.



\### C) One-liner for a single shot (what you tested)



```powershell

$in  = "D:\\...\\Shots\\01ST\_0010\_009"

$out = "${in}\_SBS"

$oiio = "$env:USERPROFILE\\vcpkg\\installed\\x64-windows\\tools\\openimageio\\oiiotool.exe"



New-Item -ItemType Directory -Force -Path $out | Out-Null



Get-ChildItem -LiteralPath $in -Filter \*.exr | ForEach-Object {

&nbsp; $dst = Join-Path $out ($\_.BaseName + "\_SBS.exr")

&nbsp; \& $oiio $\_.FullName -a --fullpixels -d float --compression dwab:45 -o $dst

&nbsp; if ($LASTEXITCODE -ne 0) { Write-Warning "FAILED -> $($\_.FullName)" }

}

```



---



\## What gets written



\* Output EXR: \*\*all subimages retained\*\*, SBS visible everywhere

\* The file name: `<OriginalBase>\_SBS.exr`

\* Folder structure: \*\*mirrors\*\* the source shot inside `<Shot>\_SBS`

\* Compression: \*\*DWAB:45\*\* by default (changeable)

\* Data type: \*\*float\*\* by default (use `-d half` if you want smaller files)



\*\*Note:\*\* By default all subimages (e.g., depth, detail lighting) are preserved. Use `-FirstSubimage` for legacy single-pass output.



---



\## Verifying an output



Use `exrheader` (optional) to confirm:



```powershell

\& "$env:USERPROFILE\\vcpkg\\installed\\x64-windows\\tools\\openexr\\exrheader.exe" `

&nbsp; "D:\\...\\01ST\_0010\_009\_SBS\\01ST\_0010\_009\_.1640\_SBS.exr" | Select-String "dataWindow|displayWindow|compression"

```



You should see:



\* `displayWindow` and `dataWindow` covering the \*\*full\*\* SBS width

\* `compression` equals your choice (e.g., `dwab`, level shown)



---



\## Best practices \& tips



\* \*\*Keep compression consistent per shot.\*\* Avoid mixing ZIP with DWA within the same sequence.

\* \*\*Performance vs size:\*\*



&nbsp; \* `dwab`/`dwaa`: small files, lossy; good for review/editorial

&nbsp; \* `zip`: lossless, often \*\*faster decode\*\* in AE/Premiere, but larger files

&nbsp; \* `-d half` can cut size significantly if full 32-bit float isn’t required

\* \*\*Cloud sync (Dropbox/Drive)\*\* can lock files. If you see `.temp.exr` issues or random failures, pause sync while converting.

\* \*\*Spaces in paths\*\* are handled; we pass arguments as arrays, not quoted strings.



---



\## Troubleshooting



\* \*\*“Invalid option `--datatype`”\*\*

&nbsp; Use `-d float` / `-d half` (OIIO 3.x).

\* \*\*“Could not find format writer for `-o:compression=zip`”\*\*

&nbsp; In OIIO 3.x, use `--compression zip` (or `--compression dwab:45`) \*\*before\*\* `-o`.

\* \*\*It crashes immediately\*\*

&nbsp; Use the \*\*CLI\*\* script (`Convert-SBS-CLI.ps1`). The GUI picker requires STA threading and may crash in some shells.

\* \*\*No outputs / zeros converted\*\*

&nbsp; Check that your path(s) are correct and contain `.exr`. If using the folder picker, select the \*\*shot folder\*\*, not the parent “Shots” directory.

\* \*\*Still only seeing one eye\*\*

&nbsp; Verify with `exrheader` that `displayWindow == dataWindow`. If yes and the app still crops, try re-importing or force re-interpret in your app.



---



\## FAQ



\*\*Q: Can’t we just edit the EXR header to flip a bit?\*\*

A: Not safely/portably. EXR’s full/data windows affect image layout. We fix it robustly by rewriting with `--fullpixels`.



\*\*Q: Can I preserve all subimages (depth, lighting, etc.)?\*\*

A: Yes, all subimages are preserved. Use `-FirstSubimage` to emit only the first pass if needed.



\*\*Q: Does this work on non-Unreal EXRs?\*\*

A: Yes, as long as subimage 0 contains an SBS image and the mismatch is `displayWindow` vs `dataWindow`.



---



\## Tested environment



\* Windows 11 (24H2)

\* PowerShell 5.1 \& PowerShell 7+

\* vcpkg 2025-07-21, OpenImageIO 3.0.9.1, OpenEXR 3.3.5



---



\## License



Internal production utility. Adapt as needed for your pipeline. (Add your studio’s license text here.)



---



If you want this bundled as a tiny `.exe` wrapper or with a simple WinForms picker (no STA surprises), I can generate that as well.



