# Convert-SBS-CLI.ps1
# CLI-only. Paste or pass shot folders. Converts to SBS into <shot>_SBS folders (or -InPlace).
# Shows overall + per-shot progress bars. Uses OpenImageIO oiiotool.

[CmdletBinding()]
param(
  # Pass one or more folders, or leave empty to paste them interactively
  [string[]]$InputDirs,

  # Options
  [ValidateSet("zip","dwaa","dwab","none")]
  [string]$Compression = "dwab",
  [int]$DwaLevel = 45,
  [ValidateSet("float","half")]
  [string]$DataType = "float",
  [switch]$Recurse,        # include subfolders
  [switch]$InPlace,        # overwrite originals (writes temp, then swaps)
    [switch]$FirstSubimage,  # legacy: only subimage 0
  [switch]$Quiet           # less console chatter
)

$ErrorActionPreference = 'Stop'

function Die([string]$msg){ Write-Error $msg; exit 1 }

function Wait-UnlockedAndReplace {
  param(
    [Parameter(Mandatory)][string]$TempPath,
    [Parameter(Mandatory)][string]$FinalPath,
    [int]$TimeoutSeconds = 30
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      if (Test-Path -LiteralPath $FinalPath) {
        Remove-Item -LiteralPath $FinalPath -Force
      }
      Move-Item -LiteralPath $TempPath -Destination $FinalPath -Force
      return $true
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  return $false
}

# Locate oiiotool
$OiiotoolPath = $null
try {
  $guess = Join-Path $env:USERPROFILE 'vcpkg\installed'
  $found = Get-ChildItem -Path $guess -Recurse -Filter oiiotool.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
  if ($found) { $OiiotoolPath = $found }
} catch {}
if (-not $OiiotoolPath -or -not (Test-Path -LiteralPath $OiiotoolPath)) {
  Die "oiiotool.exe not found. Install via: .\vcpkg install openimageio[tools] --recurse"
}
if (-not $Quiet) { Write-Host "Using oiiotool: $OiiotoolPath" }

# Gather inputs (no GUI)
if (-not $InputDirs -or $InputDirs.Count -eq 0) {
  Write-Host "Paste one or more SHOT folder paths. Press Enter on a blank line to finish."
  $lines = @()
  while ($true) {
    $p = Read-Host "Path"
    if ([string]::IsNullOrWhiteSpace($p)) { break }
    $lines += $p
  }
  if (-not $lines) { Die "No folders provided." }
  $InputDirs = $lines
}

# Normalize & validate
$Shots = @()
foreach ($p in $InputDirs) {
  if (-not (Test-Path -LiteralPath $p)) {
    Write-Warning "Skip (not found): $p"
    continue
  }
  $Shots += (Resolve-Path -LiteralPath $p).Path
}
if ($Shots.Count -eq 0) { Die "No valid shot folders." }

# Build compression args once
$compArgs = @()
switch ($Compression) {
  'zip'  { $compArgs = @('--compression','zip') }
  'none' { $compArgs = @('--compression','none') }
  'dwaa' { $compArgs = @('--compression',"dwaa:$DwaLevel") }
  'dwab' { $compArgs = @('--compression',"dwab:$DwaLevel") }
}

$totShots = $Shots.Count
$grandOK = 0; $grandFail = 0

for ($s=0; $s -lt $totShots; $s++) {
  $shotPath = $Shots[$s]
  $shotName = Split-Path $shotPath -Leaf
  $parent   = Split-Path $shotPath -Parent
  $destRoot = if ($InPlace) { $shotPath } else { Join-Path $parent ($shotName + '_SBS') }
  if (-not $InPlace) { New-Item -ItemType Directory -Force -Path $destRoot | Out-Null }

  # Collect EXRs (optionally recurse); if not InPlace, skip any already inside *_SBS
  $gci = @{ Path=$shotPath; Filter='*.exr'; File=$true; ErrorAction='SilentlyContinue' }
  if ($Recurse) { $gci.Recurse = $true }
  $frames = Get-ChildItem @gci | Sort-Object FullName
  if (-not $InPlace) {
    $frames = $frames | Where-Object { $_.DirectoryName -notmatch '\\[^\\]*_SBS(\\|$)' }
    
    # Skip frames that are already converted (resume functionality)
    if (Test-Path -LiteralPath $destRoot) {
      $existingSbs = Get-ChildItem -Path $destRoot -Filter "*.exr" -ErrorAction SilentlyContinue | 
        ForEach-Object { $_.Name }
      $frames = $frames | Where-Object { 
        $sbsName = $_.BaseName + "_SBS.exr"
        $sbsName -notin $existingSbs
      }
    }
  }

  $total = $frames.Count
  if ($total -eq 0) {
    Write-Progress -Id 1 -Activity "Shots" -Status "[$($s+1)/$totShots] $shotName (no EXRs to convert)" -PercentComplete ([int](100*($s+1)/$totShots))
    if (-not $Quiet) { Write-Host "  $shotName: No frames to convert (already complete?)" }
    continue
  }
  
  if (-not $Quiet) { Write-Host "  $shotName: Converting $total frames..." }

  $ok=0; $fail=0
  $shotRoot = (Resolve-Path -LiteralPath $shotPath).Path

  $maxProcs = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
  $running = @()
  $convertedFiles = @{}

  for ($i=0; $i -lt $total; $i++) {
    $f = $frames[$i]
    $src = (Resolve-Path -LiteralPath $f.FullName).Path

    # Mirror subfolders (even for InPlace we write to same folder)
    $rel    = $src.Substring($shotRoot.Length).TrimStart('\')
    $relDir = Split-Path $rel -Parent
    $dstDir = if ($relDir -and -not $InPlace) { Join-Path $destRoot $relDir } else { Split-Path $src -Parent }
    if (-not $InPlace) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }

    $base   = [System.IO.Path]::GetFileNameWithoutExtension($src)
    $dstNew = Join-Path $dstDir ($base + "_SBS.NEW.exx") # Use a different extension to avoid conflicts
    $dst    = if ($InPlace) { Join-Path $dstDir ($base + ".exr") } else { Join-Path $dstDir ($base + "_SBS.exr") }

    # Progress bars
    $overallPct = [int](100*$s/$totShots)
    Write-Progress -Id 1 -Activity "Shots" -Status "[$($s+1)/$totShots] $shotName" -PercentComplete $overallPct
    $filePct = [int](100*$i/$total)
    Write-Progress -Id 2 -ParentId 1 -Activity "Converting frames" -Status "$($i+1)/$total  $($f.Name)" -PercentComplete $filePct

    # Build args and run
    $args = @($src) + (if ($FirstSubimage) { @('--subimage','0') } else { @('-a') }) + @('--fullpixels','-d',$DataType) + $compArgs + @('-o',$dstNew)

    $proc = Start-Process -FilePath $OiiotoolPath -ArgumentList $args -NoNewWindow -PassThru
    $running += $proc
    $convertedFiles[$proc.Id] = @{ Src = $src; Dst = $dst; DstNew = $dstNew }

    if ($running.Count -ge $maxProcs) {
        $procToWait = Wait-Process -Process $running -Any
        $running = $running | Where-Object { $_.Id -ne $procToWait.Id }
    }
  }

  # Wait for remaining processes
  foreach ($proc in $running) {
    $proc.WaitForExit()
  }

  # Now handle the results
  foreach ($procId in $convertedFiles.Keys) {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $fileInfo = $convertedFiles[$procId]
    $src = $fileInfo.Src
    $dst = $fileInfo.Dst
    $dstNew = $fileInfo.DstNew

    if ($proc -and $proc.ExitCode -eq 0) {
        if ($InPlace) {
            $bak = $src -replace '.exr

  Write-Progress -Id 2 -ParentId 1 -Completed
  $overallPctDone = [int](100*($s+1)/$totShots)
  Write-Progress -Id 1 -Activity "Shots" -Status "[$($s+1)/$totShots] $shotName done — OK:$ok Fail:$fail  ->  $destRoot" -PercentComplete $overallPctDone
}

Write-Progress -Id 1 -Completed
Write-Host "ALL DONE. Shots: $totShots   Converted: $grandOK   Failed: $grandFail"
if ($InPlace) {
  Write-Host "In-place mode used. Original files were backed up as *.orig.exr in the same folders."
}
, '.orig.exr'
            try {
                if (-not (Test-Path -LiteralPath $bak)) {
                    Rename-Item -LiteralPath $src -NewName ([System.IO.Path]::GetFileName($bak))
                } else {
                    Remove-Item -LiteralPath $src -Force
                }
                if (Wait-UnlockedAndReplace -TempPath $dstNew -FinalPath $dst) {
                    $ok++; $grandOK++
                    if (-not $Quiet) { Write-Host " OK -> $dst" }
                } else {
                    Write-Warning "Could not replace $dst (locked?); left $dstNew"
                    $fail++; $grandFail++
                }
            } catch {
                Write-Warning "InPlace swap failed for $src : $($_.Exception.Message)"
                $fail++; $grandFail++
                if (Test-Path -LiteralPath $dstNew) { Remove-Item -LiteralPath $dstNew -ErrorAction SilentlyContinue }
            }
        } else {
            if (Wait-UnlockedAndReplace -TempPath $dstNew -FinalPath $dst) {
                $ok++; $grandOK++
                if (-not $Quiet) { Write-Host " OK -> $dst" }
            } else {
                Write-Warning "Could not replace $dst (locked?); left $dstNew"
                $fail++; $grandFail++
            }
        }
    } else {
        $fail++; $grandFail++
        if (Test-Path -LiteralPath $dstNew) { Remove-Item -LiteralPath $dstNew -ErrorAction SilentlyContinue }
        if (-not $Quiet) { Write-Warning " FAIL ($($proc.ExitCode)) -> $src" }
    }
  }

  Write-Progress -Id 2 -ParentId 1 -Completed
  $overallPctDone = [int](100*($s+1)/$totShots)
  Write-Progress -Id 1 -Activity "Shots" -Status "[$($s+1)/$totShots] $shotName done — OK:$ok Fail:$fail  ->  $destRoot" -PercentComplete $overallPctDone
}

Write-Progress -Id 1 -Completed
Write-Host "ALL DONE. Shots: $totShots   Converted: $grandOK   Failed: $grandFail"
if ($InPlace) {
  Write-Host "In-place mode used. Original files were backed up as *.orig.exr in the same folders."
}
