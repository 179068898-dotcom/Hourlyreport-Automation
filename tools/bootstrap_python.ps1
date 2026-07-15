[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Version = "3.14.6"
$InstallerName = "python-$Version-amd64.exe"
$DownloadUrl = "https://www.python.org/ftp/python/$Version/$InstallerName"
$ExpectedSha256 = "14b3e9a710a3fcf0bd9b55ab6b60412bd91227563f813fc49040cabc0209e0bd"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root "runtime"
$DownloadDir = Join-Path $RuntimeDir "downloads"
$TargetDir = Join-Path $RuntimeDir "python"
$PythonExe = Join-Path $TargetDir "python.exe"
$InstallerPath = Join-Path $DownloadDir $InstallerName
$PartialPath = "$InstallerPath.part"

if (Test-Path -LiteralPath $PythonExe) {
    Write-Output "[BOOTSTRAP][5/5] Project Python is already installed."
    & $PythonExe --version
    exit 0
}

New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

Write-Output "[BOOTSTRAP][1/5] Preparing Python $Version download."
if (-not (Test-Path -LiteralPath $InstallerPath)) {
    Remove-Item -LiteralPath $PartialPath -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $PartialPath -UseBasicParsing
    Move-Item -LiteralPath $PartialPath -Destination $InstallerPath -Force
} else {
    Write-Output "[BOOTSTRAP][2/5] Reusing the verified installer cache."
}

Write-Output "[BOOTSTRAP][3/5] Verifying the Python installer."
$ActualSha256 = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item -LiteralPath $InstallerPath -Force -ErrorAction SilentlyContinue
    throw "Python installer hash verification failed. The invalid file was removed."
}

Write-Output "[BOOTSTRAP][4/5] Installing project Python silently. Keep the application open."
New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
$Arguments = @(
    "/quiet",
    "InstallAllUsers=0",
    "TargetDir=$TargetDir",
    "PrependPath=0",
    "Include_launcher=0",
    "Include_pip=1",
    "Include_test=0",
    "Include_doc=0",
    "Include_tcltk=0",
    "Include_dev=0",
    "AssociateFiles=0",
    "Shortcuts=0"
)
$Process = Start-Process -FilePath $InstallerPath -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
if ($Process.ExitCode -ne 0) {
    throw "Python installer exit code: $($Process.ExitCode)"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python was not found after installation: $PythonExe"
}

Write-Output "[BOOTSTRAP][5/5] Python installation completed."
& $PythonExe --version
