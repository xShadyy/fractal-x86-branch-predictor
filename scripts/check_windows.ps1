# Build and run the Windows x64 cache controls from a VS Code task.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputDirectory = Join-Path $projectRoot 'out'
$binary = Join-Path $outputDirectory 'cache-probe-windows.exe'
$trace = Join-Path $outputDirectory ('cache-probe-windows-{0}.log' -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) {
    throw 'MSVC Build Tools not found. Install the Desktop development with C++ workload.'
}
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) {
    throw 'MSVC x64 tools not found. Install the Desktop development with C++ workload.'
}
$developerCommand = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path $developerCommand)) {
    throw "Developer command script not found: $developerCommand"
}

# Import the build environment for this process only. No global PATH changes.
$setup = 'call "' + $developerCommand + '" -arch=x64 >nul && set'
$environmentLines = & cmd.exe /d /c $setup
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment initialization failed.' }
foreach ($line in $environmentLines) {
    if ($line -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw 'cl.exe is unavailable.' }

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$sources = @(
    (Join-Path $projectRoot 'programs\utest.c'),
    (Join-Path $projectRoot 'programs\cpu_features.c'),
    (Join-Path $projectRoot 'programs\cache_probe_windows.c')
)
Push-Location $outputDirectory
try {
    & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources
    if ($LASTEXITCODE -ne 0) { throw 'Cache probe compilation failed.' }
} finally {
    Pop-Location
}

& $binary | Out-File -FilePath $trace -Encoding ascii
if ($LASTEXITCODE -ne 0) { throw "Cache probe failed; inspect $trace" }

$analyzer = Join-Path $projectRoot 'scripts\analyze_cache_probe.py'
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3 $analyzer $trace --strict
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    & python.exe $analyzer $trace --strict
} else {
    throw 'Python 3 is required to analyze the raw trace.'
}
if ($LASTEXITCODE -ne 0) { throw "Cache controls failed; inspect $trace" }
Write-Host "Raw trace: $trace"
