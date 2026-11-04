param(
    [string]$Version = "0.1.1"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$libraryPath = Join-Path $projectRoot "3DPrintedClocksGithub\3DPrintedClocks"
$appName = "Parametric3DPrintedClockGenerator"
$distRoot = Join-Path $projectRoot "dist"
$workRoot = Join-Path $projectRoot "build\pyinstaller-work"
$specRoot = Join-Path $projectRoot "build\pyinstaller-spec"
$appOutput = Join-Path $distRoot $appName
$archivePath = Join-Path $distRoot "$appName-v$Version-win64.zip"
$upstreamArchive = Join-Path $projectRoot "build\upstream-library.tar"

Set-Location $projectRoot

if (-not (Test-Path $libraryPath -PathType Container)) {
    throw "Clock-library submodule is missing. Run: git submodule update --init --recursive"
}

$expectedLibraryLine = git ls-tree HEAD -- 3DPrintedClocksGithub/3DPrintedClocks
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the pinned clock-library revision from Git."
}
$expectedLibraryCommit = ($expectedLibraryLine -split "\s+")[-2]
$actualLibraryCommit = git -C $libraryPath rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualLibraryCommit -ne $expectedLibraryCommit) {
    throw "The clock-library checkout does not match the revision pinned by this project commit."
}

$pythonVersion = py -3.14 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $pythonVersion.Trim() -ne "3.14") {
    throw "Python 3.14 is required to build the Windows release bundle."
}

if (Test-Path $appOutput) {
    Remove-Item -LiteralPath $appOutput -Recurse -Force
}
if (Test-Path $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $workRoot) -Force | Out-Null

py -3.14 -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name $appName `
    --distpath $distRoot `
    --workpath $workRoot `
    --specpath $specRoot `
    --collect-all cadquery `
    main.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build the Windows application."
}

Copy-Item (Join-Path $projectRoot "README.md") $appOutput
Copy-Item (Join-Path $projectRoot "LICENSE") $appOutput

$libraryDestination = Join-Path $appOutput "_internal\3DPrintedClocksGithub\3DPrintedClocks"
New-Item -ItemType Directory -Path $libraryDestination -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path $upstreamArchive) -Force | Out-Null
if (Test-Path $upstreamArchive) {
    Remove-Item -LiteralPath $upstreamArchive -Force
}
git -C $libraryPath archive --format=tar --output=$upstreamArchive HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Could not export the pinned clock-library source."
}
tar -xf $upstreamArchive -C $libraryDestination
if ($LASTEXITCODE -ne 0) {
    throw "Could not package the pinned clock-library source."
}
Remove-Item -LiteralPath $upstreamArchive -Force

Compress-Archive -Path (Join-Path $appOutput "*") -DestinationPath $archivePath
if (-not (Test-Path $archivePath -PathType Leaf)) {
    throw "The portable ZIP archive was not created."
}

$archive = Get-Item $archivePath
Write-Output "Build complete: $($archive.FullName)"
Write-Output ("Archive size: {0:N1} MiB" -f ($archive.Length / 1MB))
