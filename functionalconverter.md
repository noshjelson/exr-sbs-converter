$in  = "D:\Boona Dropbox\Boona Slate\01_Active\Silver_SIL_JUL25_BS-144\Production\Output\Silver - Renders\Unreal Renders\Shots\01ST_0010_009"
$out = "${in}_SBS"
$oiio = "$env:USERPROFILE\vcpkg\installed\x64-windows\tools\openimageio\oiiotool.exe"

New-Item -ItemType Directory -Force -Path $out | Out-Null

Get-ChildItem -LiteralPath $in -Filter *.exr | ForEach-Object {
  $dst = Join-Path $out ($_.BaseName + "_SBS.exr")
  & $oiio $_.FullName --subimage 0 --fullpixels -d float --compression dwab:45 -o $dst
  if ($LASTEXITCODE -ne 0) { Write-Warning "FAILED -> $($_.FullName)" }
}
