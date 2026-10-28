# Build the fixed branch site, run paired trials, and validate the trace.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
$binary = Join-Path $out 'spec-probe-windows.exe'
$object = Join-Path $out 'spec_branch_windows.obj'
$trace = Join-Path $out ('spec-probe-windows-{0}.log' -f (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'))

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { throw 'Install MSVC Build Tools with Desktop development with C++.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'MSVC x64 tools not found.' }
$developerCommand = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
if (-not (Test-Path $developerCommand)) { throw "Missing $developerCommand" }
$setup = 'call "' + $developerCommand + '" -arch=x64 >nul && set'
$environmentLines = & cmd.exe /d /c $setup
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment initialization failed.' }
foreach ($line in $environmentLines) {
    if ($line -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
if (-not (Get-Command ml64.exe -ErrorAction SilentlyContinue)) { throw 'ml64.exe is unavailable.' }
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { throw 'cl.exe is unavailable.' }

New-Item -ItemType Directory -Path $out -Force | Out-Null
& ml64.exe /nologo /c "/Fo$object" (Join-Path $root 'programs\spec_branch_windows.asm')
if ($LASTEXITCODE -ne 0) { throw 'Branch-site assembly failed.' }
$sources = @(
    (Join-Path $root 'programs\spec_probe_windows.c'),
    (Join-Path $root 'programs\cpu_features.c'),
    (Join-Path $root 'programs\cache_probe_windows.c')
)
Push-Location $out
try {
    & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources $object
    if ($LASTEXITCODE -ne 0) { throw 'Speculative probe compilation failed.' }
} finally {
    Pop-Location
}

& $binary | Out-File -FilePath $trace -Encoding ascii
if ($LASTEXITCODE -ne 0) { throw "Speculative probe failed; inspect $trace" }
$analyzer = Join-Path $root 'scripts\analyze_spec_probe.py'
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3 $analyzer $trace --strict
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    & python.exe $analyzer $trace --strict
} else {
    throw 'Python 3 is required to analyze the raw trace.'
}
if ($LASTEXITCODE -ne 0) { throw "Branch trace validation failed; inspect $trace" }
Write-Host "Raw trace: $trace"
