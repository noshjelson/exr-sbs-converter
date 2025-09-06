# Convert-SBS-Interactive.ps1
# Pick one or more shot folders, convert EXR sequences to true SBS into <shot>_SBS folders,
# showing progress bars. Uses oiiotool (OpenImageIO).

[CmdletBinding()]
param(
  # If you want to skip the folder picker, you can pass paths here:
  [string[]]$InputDirs,

  # Options
  [ValidateSet("zip","dwaa","dwab","none")] [string]$Compression = "dwab",
  [int]$DwaLevel = 45,
  [ValidateSet("float","half")] [string]$DataType = "float",
  [switch]$Recurse
)

function Die($msg){ Write-Error $msg; exit 1 }

# Find oiiotool automatically (vcpkg)
$OiiotoolPath = $null
$guess = Join-Path $env:USERPROFILE "vcpkg\installed"
$found = Get-ChildItem -Path $guess -Recurse -Filter oiiotool.exe -ErrorAction SilentlyContinue |
         Select-Object -First 1 -ExpandProperty FullName
if ($found) { $OiiotoolPath = $found }
if (-not $OiiotoolPath -or -not (Test-Path -LiteralPath $OiiotoolPath)) {
  Die "oiiotool.exe not found. Install via: `.\vcpkg install openimageio[tools] --recurse`"
}

# If no input dirs passed, open a folder picker repeatedly to gather multiple shots
if (-not $InputDirs -or $InputDirs.Count -eq 0) {
  Add-Type -AssemblyName System.Windows.Forms
  $folders = @()
  while ($true) {
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "Pick a SHOT folder to convert (click Cancel when finished selecting)"
    $dlg.ShowNewFolderButton = $false
    $res = $dlg.ShowDialog()
    if ($res -ne [System.Windows.Forms.DialogResult]::OK) { break }
    if ($dlg.SelectedPath) { $folders += $dlg.SelectedPath }
  }
  if ($folders.Count -eq 0) { Die "No folders selected." }
  $InputDirs = $folders
}

# Normalize and validate
$Shots = @()
foreach ($p in $InputDirs) {
  if (-not (Test-Path -LiteralPath $p)) { Write-Warning "Skip (not found): $p"; continue }
  $Shots += (Resolve-Path -LiteralPath $p).Path
}
if ($Shots.Count -eq 0) { Die "No valid shot folders." }

# Build compression args once
$compArgs = @()
switch ($Compression) {
  "zip"  { $compArgs = @("--compression","zip") }
  "none" { $compArgs = @("--compression","none") }
  "dwaa" { $compArgs = @("--compression","dwaa:$DwaLevel") }
  "dwab" { $compArgs = @("--compression","dwab:$DwaLevel") }
}

$totShots = $Shots.Count
$shotIdx  = 0
$grandOK = 0; $grandFail = 0

foreach ($shotPath in $Shots) {
  $shotIdx++
  $shotName  = Split-Path $shotPath -Leaf
  $parent    = Split-Path $shotPath -Parent
  $destRoot  = Join-Path $parent ($shotName + "_SBS")
  New-Item -ItemType Directory -Force -Path $destRoot | Out-Null

  # Gather EXRs (optionally recurse), and skip anything already inside *_SBS
  $gci = @{ Path=$shotPath; Filter="*.exr"; File=$true; ErrorAction="SilentlyContinue" }
  if ($Recurse) { $gci.Recurse = $true }
  $frames = Get-ChildItem @gci | Where-Object { $_.DirectoryName -notmatch '\\[^\\]*_SBS(\\|$)' } | Sort-Object FullName

  $total = $frames.Count
  if ($total -eq 0) {
    Write-Progress -Id 1 -Activity "Shots" -Status "[$shotId]()
