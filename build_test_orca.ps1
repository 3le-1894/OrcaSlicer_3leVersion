param(
    [string]$Configuration = "Release",
    [string]$Target = "OrcaSlicer",
    [switch]$NoLaunch,
    [switch]$NoClose,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$testExe = Join-Path $repoRoot "build\src\$Configuration\orca-slicer.exe"
$vsDevCmd = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"
$buildTemp = Join-Path $repoRoot "build\codex-temp"
$safeTargetName = $Target -replace '[^A-Za-z0-9_.-]', '_'
$buildStatePath = Join-Path $buildTemp "last-successful-build-state-$Configuration-$safeTargetName.txt"

if (-not (Test-Path $vsDevCmd)) {
    throw "Visual Studio developer command file was not found: $vsDevCmd"
}

Set-Location $repoRoot

function Get-SourceState {
    $sourceFiles = (& git ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read Git-visible source files. Run this script from inside the OrcaSlicer Git repository."
    }

    $sourceFiles |
        Sort-Object |
        ForEach-Object {
            $path = $_
            $item = Get-Item -LiteralPath (Join-Path $repoRoot $path) -ErrorAction SilentlyContinue
            if ($item -and -not $item.PSIsContainer) {
                "$path`t$($item.Length)`t$($item.LastWriteTimeUtc.Ticks)"
            }
        } |
        Out-String
}

New-Item -ItemType Directory -Force -Path $buildTemp | Out-Null
$sourceState = Get-SourceState

if (-not $Force -and (Test-Path $buildStatePath)) {
    $lastBuildState = Get-Content -Raw $buildStatePath
    if ($sourceState.TrimEnd() -eq $lastBuildState.TrimEnd()) {
        Write-Host "No Git-visible source changes since the last successful $Configuration/$Target build. Skipping build."
        Write-Host "Use .\build_test_orca.ps1 -Force to rebuild anyway."
        exit 0
    }
}

if (-not $NoClose) {
    $running = Get-CimInstance Win32_Process -Filter "name = 'orca-slicer.exe'" |
        Where-Object { $_.ExecutablePath -eq $testExe }

    if ($running) {
        $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
        Write-Host "Closed test OrcaSlicer process(es): $((($running | ForEach-Object ProcessId) -join ', '))"
    } else {
        Write-Host "No test OrcaSlicer process found at expected path."
    }
}

$env:TEMP = $buildTemp
$env:TMP = $buildTemp

$dllPath = Join-Path $repoRoot "build\src\$Configuration\OrcaSlicer.dll"
$beforeTimestamp = if (Test-Path $dllPath) { (Get-Item $dllPath).LastWriteTime } else { $null }

$buildCommand = "call `"$vsDevCmd`" -arch=x64 >nul && cmake --build build --config $Configuration --target $Target -- /nodeReuse:false /p:TrackFileAccess=false"
cmd /c $buildCommand

if ($LASTEXITCODE -ne 0) {
    throw "Build failed with exit code $LASTEXITCODE"
}

Write-Host "Build succeeded."
Set-Content -Path $buildStatePath -Value $sourceState -Encoding UTF8

if (Test-Path $dllPath) {
    $afterTimestamp = (Get-Item $dllPath).LastWriteTime
    Write-Host "DLL timestamp before: $beforeTimestamp"
    Write-Host "DLL timestamp after:  $afterTimestamp"
}

if (-not $NoLaunch) {
    if (-not (Test-Path $testExe)) {
        throw "Test OrcaSlicer executable was not found: $testExe"
    }

    Start-Process -FilePath $testExe -WorkingDirectory (Split-Path $testExe)
    Write-Host "Reopened test OrcaSlicer."
}
