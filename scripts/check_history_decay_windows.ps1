# Study D: fixed-work intervening same-site branches, native Windows.
param([uint32]$Seed = 0)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
$binary = Join-Path $out 'history-decay-windows.exe'
$object = Join-Path $out 'history_decay_branch_site.obj'
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
Write-Host "Preselected Study D seed: $runSeed"

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

& ml64.exe /nologo /c "/Fo$object" (Join-Path $root 'programs\history_decay_windows.asm')
if ($LASTEXITCODE -ne 0) { throw 'History-decay assembly failed.' }
$sources = @(
    (Join-Path $root 'programs\history_decay_windows.c'),
    (Join-Path $root 'programs\cpu_features.c')
)
Push-Location $out
try {
    & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources $object
    if ($LASTEXITCODE -ne 0) { throw 'History-decay compilation failed.' }
} finally {
    Pop-Location
}

$runStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$trace = Join-Path $out ('history-decay-windows-{0}.log' -f $runStamp)
$archivedBinary = Join-Path $out ('history-decay-windows-{0}.exe' -f $runStamp)
$metadata = Join-Path $out ('history-decay-windows-{0}.build.json' -f $runStamp)
if ((Test-Path $trace) -or (Test-Path $archivedBinary) -or (Test-Path $metadata)) {
    throw "Run timestamp collision: $runStamp"
}
Copy-Item -Path $binary -Destination $archivedBinary
$binaryHash = (Get-FileHash -Path $archivedBinary -Algorithm SHA256).Hash.ToLowerInvariant()
$clCommand = Get-Command cl.exe
$mlCommand = Get-Command ml64.exe
$linkCommand = Get-Command link.exe
$gitHead = & git -C $root rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot record Git HEAD.' }
$gitDirty = @(& git -C $root status --porcelain).Count -gt 0
if ($LASTEXITCODE -ne 0) { throw 'Cannot record Git status.' }
$fileHashes = @{}
foreach ($relative in @('programs/history_decay_windows.c', 'programs/history_decay_windows.asm', 'programs/cpu_features.c', 'scripts/analyze_history_decay.py', 'scripts/check_history_decay_windows.ps1')) {
    $fileHashes[$relative] = (Get-FileHash -Path (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
@{
    run_utc = $runStamp
    seed = $runSeed
    git_head = "$gitHead"
    git_dirty = $gitDirty
    executable_sha256 = $binaryHash
    sources_sha256 = $fileHashes
    ml64_path = "$($mlCommand.Source)"
    ml64_version = "$((Get-Item $mlCommand.Source).VersionInfo.FileVersion)"
    cl_path = "$($clCommand.Source)"
    cl_version = "$((Get-Item $clCommand.Source).VersionInfo.FileVersion)"
    link_path = "$($linkCommand.Source)"
    link_version = "$((Get-Item $linkCommand.Source).VersionInfo.FileVersion)"
    compile_flags = '/nologo /std:c11 /O2 /W4 /WX'
    assembler_flags = '/nologo /c'
} | ConvertTo-Json -Depth 5 | Out-File -FilePath $metadata -Encoding utf8

& $archivedBinary ([string]$runSeed) | Out-File -FilePath $trace -Encoding ascii
if ($LASTEXITCODE -ne 0) { throw "History-decay run failed; inspect $trace" }
$windowsBuild = (Get-CimInstance Win32_OperatingSystem -Property BuildNumber).BuildNumber
if ([string]$windowsBuild -notmatch '^[0-9]+$') { throw 'Could not record Windows build number.' }
Add-Content -Path $trace -Value "DECAY_HOST,windows_build=$windowsBuild,run_utc=$runStamp" -Encoding ascii
Add-Content -Path $trace -Value "DECAY_BINARY,sha256=$binaryHash" -Encoding ascii
$analyzer = Join-Path $root 'scripts\analyze_history_decay.py'
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3 $analyzer $trace --strict
} elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
    & python.exe $analyzer $trace --strict
} else {
    throw 'Python 3 is required for trace validation.'
}
if ($LASTEXITCODE -ne 0) { throw "History-decay controls or validation failed; preserve $trace and $archivedBinary" }
Write-Host "Binary SHA256: $binaryHash"
Write-Host "Binary: $archivedBinary"
Write-Host "Raw trace: $trace"
Write-Host "Build provenance: $metadata"
