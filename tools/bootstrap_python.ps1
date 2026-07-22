[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Version = "3.14.5"
$PackageName = "python.$Version.nupkg"
$DownloadUrl = "https://www.nuget.org/api/v2/package/python/$Version"
$ExpectedSha256 = "03ad5810986afd8273a34a28c15cb594300ba7f4749f24362d69206fa1b6ac15"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root "runtime"
$DownloadDir = Join-Path $RuntimeDir "downloads"
$TargetDir = Join-Path $RuntimeDir "python-$Version"
$PythonExe = Join-Path $TargetDir "python.exe"
$PackagePath = Join-Path $DownloadDir $PackageName
$PartialPath = "$PackagePath.part"

if (Test-Path -LiteralPath $PythonExe) {
    Write-Output "[BOOTSTRAP][5/5] Project Python is already installed."
    & $PythonExe --version
    exit 0
}

New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

Write-Output "[BOOTSTRAP][1/5] Preparing isolated Python $Version download."
if (-not (Test-Path -LiteralPath $PackagePath)) {
    Remove-Item -LiteralPath $PartialPath -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $PartialPath -UseBasicParsing
    Move-Item -LiteralPath $PartialPath -Destination $PackagePath -Force
} else {
    Write-Output "[BOOTSTRAP][2/5] Reusing the verified package cache."
}

Write-Output "[BOOTSTRAP][3/5] Verifying the isolated Python package."
$ActualSha256 = (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item -LiteralPath $PackagePath -Force -ErrorAction SilentlyContinue
    throw "Python package hash verification failed. The invalid file was removed."
}

Write-Output "[BOOTSTRAP][4/5] Extracting the isolated project Python. Keep the application open."
$StagingDir = Join-Path $RuntimeDir ("python-stage-" + [Guid]::NewGuid().ToString("N"))
$ArchivePath = Join-Path $StagingDir "python.zip"
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
Copy-Item -LiteralPath $PackagePath -Destination $ArchivePath
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $StagingDir
$ExtractedTools = Join-Path $StagingDir "tools"
if (-not (Test-Path -LiteralPath (Join-Path $ExtractedTools "python.exe"))) {
    throw "The isolated Python package does not contain tools\\python.exe."
}
if (Test-Path -LiteralPath $TargetDir) {
    $InvalidTarget = "$TargetDir.invalid-$([DateTime]::Now.ToString('yyyyMMddHHmmss'))"
    Move-Item -LiteralPath $TargetDir -Destination $InvalidTarget
}
Move-Item -LiteralPath $ExtractedTools -Destination $TargetDir
Remove-Item -LiteralPath $StagingDir -Recurse -Force
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python was not found after extraction: $PythonExe"
}

Write-Output "[BOOTSTRAP][5/5] Isolated Python installation completed."
& $PythonExe --version
