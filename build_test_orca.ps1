param(
    [string]$Configuration = "Release",
    [string]$Target = "OrcaSlicer",
    [switch]$NoLaunch,
    [switch]$NoClose
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$testExe = Join-Path $repoRoot "build\src\$Configuration\orca-slicer.exe"
$vsDevCmd = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat"

if (-not (Test-Path $vsDevCmd)) {
    throw "Visual Studio developer command file was not found: $vsDevCmd"
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

$buildTemp = Join-Path $repoRoot "build\codex-temp"
$env:TEMP = $buildTemp
$env:TMP = $buildTemp
New-Item -ItemType Directory -Force -Path $buildTemp | Out-Null

Set-Location $repoRoot

$dllPath = Join-Path $repoRoot "build\src\$Configuration\OrcaSlicer.dll"
$beforeTimestamp = if (Test-Path $dllPath) { (Get-Item $dllPath).LastWriteTime } else { $null }

$buildCommand = "call `"$vsDevCmd`" -arch=x64 >nul && cmake --build build --config $Configuration --target $Target -- /nodeReuse:false /p:TrackFileAccess=false"
cmd /c $buildCommand

if ($LASTEXITCODE -ne 0) {
    throw "Build failed with exit code $LASTEXITCODE"
}

Write-Host "Build succeeded."

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
