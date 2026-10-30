# Build, run and validate the native Windows user-mode branch-history probe.
param([uint32]$Seed = 0)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
$binary = Join-Path $out 'history-probe-windows.exe'
$object = Join-Path $out 'history_probe_windows.obj'

if ($PSBoundParameters.ContainsKey('Seed')) {
    if ($Seed -eq 0) { throw 'Specify a nonzero 32-bit seed.' }
    $runSeed = $Seed
} else {
    $randomBytes = New-Object byte[] 4
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $generator.GetBytes($randomBytes)
            $runSeed = [BitConverter]::ToUInt32($randomBytes, 0)
        } while ($runSeed -eq 0)
    } finally {
        $generator.Dispose()
    }
}
Write-Host "Preselected run seed: $runSeed"

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
& ml64.exe /nologo /c "/Fo$object" (Join-Path $root 'programs\history_probe_windows.asm')
if ($LASTEXITCODE -ne 0) { throw 'History-site assembly failed.' }
$sources = @(
    (Join-Path $root 'programs\history_probe_windows.c'),
    (Join-Path $root 'programs\cpu_features.c')
)
Push-Location $out
try {
    & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources $object
    if ($LASTEXITCODE -ne 0) { throw 'History probe compilation failed.' }
} finally {
    Pop-Location
}

$runStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$trace = Join-Path $out ('history-probe-windows-{0}.log' -f $runStamp)
$archivedBinary = Join-Path $out ('history-probe-windows-{0}.exe' -f $runStamp)
if ((Test-Path $trace) -or (Test-Path $archivedBinary)) {
    throw "Run timestamp collision: $runStamp"
}
Copy-Item -Path $binary -Destination $archivedBinary
$binaryHash = (Get-FileHash -Path $archivedBinary -Algorithm SHA256).Hash.ToLowerInvariant()
& $archivedBinary ([string]$runSeed) | Out-File -FilePath $trace -Encoding ascii
if ($LASTEXITCODE -ne 0) {
    throw "History probe run failed; inspect $trace and retained $archivedBinary"
}
$windowsBuild = (Get-CimInstance Win32_OperatingSystem -Property BuildNumber).BuildNumber
if ([string]$windowsBuild -notmatch '^[0-9]+$') {
    throw 'Could not record the Windows build number.'
}
Add-Content -Path $trace -Value "HISTORY_HOST,windows_build=$windowsBuild,run_utc=$runStamp" -Encoding ascii
Add-Content -Path $trace -Value "HISTORY_BINARY,sha256=$binaryHash" -Encoding ascii
$analyzer = Join-Path $root 'scripts\analyze_history_probe.py'
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3 $analyzer $trace --strict
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    & python.exe $analyzer $trace --strict
} else {
    throw 'Python 3 is required to analyze the raw trace.'
}
if ($LASTEXITCODE -ne 0) { throw "History probe trace validation failed; inspect $trace" }
Write-Host "Binary SHA256: $binaryHash"
Write-Host "Binary: $archivedBinary"
Write-Host "Raw trace: $trace"
