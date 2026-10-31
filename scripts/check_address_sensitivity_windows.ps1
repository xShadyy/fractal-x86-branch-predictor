# Exploratory address-sensitivity pilot: build, archive, run and validate on native Windows.
param([uint32]$Seed = 0)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
$binary = Join-Path $out 'address-sensitivity-windows.exe'
$object = Join-Path $out 'address_sensitivity_branch_site.obj'

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
    } finally { $generator.Dispose() }
}
Write-Host "Preselected Address-sensitivity pilot seed: $runSeed"

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
foreach ($command in @('ml64.exe', 'cl.exe', 'link.exe')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Missing $command" }
}
New-Item -ItemType Directory -Path $out -Force | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$trace = Join-Path $out ('address-sensitivity-windows-{0}.log' -f $stamp)
$archivedBinary = Join-Path $out ('address-sensitivity-windows-{0}.exe' -f $stamp)
$buildLog = Join-Path $out ('address-sensitivity-windows-{0}.build.log' -f $stamp)
$provenanceFile = Join-Path $out ('address-sensitivity-windows-{0}.build.json' -f $stamp)
$disassembly = Join-Path $out ('address-sensitivity-windows-{0}.disasm.txt' -f $stamp)
foreach ($path in @($trace, $archivedBinary, $buildLog, $provenanceFile, $disassembly)) {
    if (Test-Path $path) { throw "Run timestamp collision: $stamp" }
}
$assembly = Join-Path $root 'programs\address_sensitivity_windows.asm'
$sources = @((Join-Path $root 'programs\address_sensitivity_windows.c'),
             (Join-Path $root 'programs\cpu_features.c'))
$analyzer = Join-Path $root 'scripts\analyze_address_sensitivity.py'
$scriptPath = $MyInvocation.MyCommand.Path
$sourceHashes = [ordered]@{}
foreach ($path in @($assembly) + $sources + @($analyzer, $scriptPath)) {
    $relative = $path.Substring($root.Length + 1)
    $sourceHashes[$relative] = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$tools = [ordered]@{}
foreach ($name in @('cl.exe', 'ml64.exe', 'link.exe')) {
    $toolPath = (Get-Command $name).Source
    $tools[$name] = [ordered]@{
        path = $toolPath
        file_version = (Get-Item $toolPath).VersionInfo.FileVersion
        product_version = (Get-Item $toolPath).VersionInfo.ProductVersion
    }
}
$gitHead = (& git -C $root rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Could not record Git HEAD.' }
$gitDirtyLines = @(& git -C $root status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Could not record Git working tree state.' }
$provenance = [ordered]@{
    version = 1
    study = 'exploratory_address_sensitivity'
    seed = $runSeed
    build_start_utc = $stamp
    git_head = $gitHead
    git_dirty = ($gitDirtyLines.Count -gt 0)
    git_status_porcelain = $gitDirtyLines
    source_sha256 = $sourceHashes
    tools = $tools
    assembly_command = @('ml64.exe', '/nologo', '/c', "/Fo$object", $assembly)
    compilation_command = @('cl.exe', '/nologo', '/std:c11', '/O2', '/W4', '/WX',
                            "/Fe$binary") + $sources + @($object)
    status = 'preselected'
}
function Save-Provenance {
    ($provenance | ConvertTo-Json -Depth 8) | Out-File -FilePath $provenanceFile -Encoding utf8
}
function Get-TextSha256([string]$Path) {
    [byte[]]$image = [IO.File]::ReadAllBytes($Path)
    if ($image.Length -lt 0x40) { throw 'Invalid PE header length.' }
    $pe = [BitConverter]::ToInt32($image, 0x3c)
    if ($pe -lt 0 -or $pe + 24 -gt $image.Length -or
        [Text.Encoding]::ASCII.GetString($image, $pe, 4) -ne ('PE' + [char]0 + [char]0)) {
        throw 'Invalid PE signature.'
    }
    $sections = [BitConverter]::ToUInt16($image, $pe + 6)
    $optionalSize = [BitConverter]::ToUInt16($image, $pe + 20)
    $table = $pe + 24 + $optionalSize
    for ($i = 0; $i -lt $sections; ++$i) {
        $entry = $table + 40 * $i
        if ($entry + 40 -gt $image.Length) { throw 'Truncated PE section table.' }
        $sectionName = [Text.Encoding]::ASCII.GetString($image, $entry, 8).Trim([char]0)
        if ($sectionName -eq '.text') {
            $rawSize = [BitConverter]::ToInt32($image, $entry + 16)
            $rawOffset = [BitConverter]::ToInt32($image, $entry + 20)
            if ($rawOffset -lt 0 -or $rawSize -le 0 -or
                $rawOffset + $rawSize -gt $image.Length) { throw 'Invalid .text section bounds.' }
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                return [BitConverter]::ToString(
                    $sha.ComputeHash($image, $rawOffset, $rawSize)).Replace('-', '').ToLowerInvariant()
            } finally { $sha.Dispose() }
        }
    }
    throw 'No .text section found in the executable.'
}
Save-Provenance
try {
    "Preselected run seed: $runSeed" | Out-File -FilePath $buildLog -Encoding ascii
    & ml64.exe /nologo /c "/Fo$object" $assembly 2>&1 | Tee-Object -FilePath $buildLog -Append
    if ($LASTEXITCODE -ne 0) { throw 'Address-sensitivity branch-site assembly failed.' }
    Push-Location $out
    try {
        & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources $object 2>&1 |
            Tee-Object -FilePath $buildLog -Append
        if ($LASTEXITCODE -ne 0) { throw 'Address-sensitivity compilation failed.' }
    } finally { Pop-Location }
    Copy-Item -Path $binary -Destination $archivedBinary
    $binaryHash = (Get-FileHash -Path $archivedBinary -Algorithm SHA256).Hash.ToLowerInvariant()
    $provenance['binary_sha256'] = $binaryHash
    $provenance['text_section_sha256'] = Get-TextSha256 $archivedBinary
    if (Get-Command dumpbin.exe -ErrorAction SilentlyContinue) {
        & dumpbin.exe /disasm $archivedBinary | Out-File -FilePath $disassembly -Encoding ascii
        if ($LASTEXITCODE -ne 0) { throw 'Could not save Windows executable disassembly.' }
        $provenance['disassembly_sha256'] = (Get-FileHash -Path $disassembly -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $provenance['status'] = 'built'
    Save-Provenance
    $runStartUtc = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $provenance['execution_start_utc'] = $runStartUtc
    Save-Provenance
    & $archivedBinary ([string]$runSeed) 2>&1 | Out-File -FilePath $trace -Encoding ascii
    if ($LASTEXITCODE -ne 0) { throw "Address-sensitivity run failed; inspect retained $trace" }
    $windowsBuild = (Get-CimInstance Win32_OperatingSystem -Property BuildNumber).BuildNumber
    if ([string]$windowsBuild -notmatch '^[0-9]+$') {
        throw 'Could not record Windows build number.'
    }
    Add-Content -Path $trace -Value "ADDR_HOST,windows_build=$windowsBuild,run_utc=$runStartUtc" -Encoding ascii
    Add-Content -Path $trace -Value "ADDR_BINARY,sha256=$binaryHash" -Encoding ascii
    $provenance['status'] = 'recorded'
    Save-Provenance
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        & py.exe -3 $analyzer $trace --strict
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        & python.exe $analyzer $trace --strict
    } else { throw 'Python 3 is required to analyze the raw trace.' }
    if ($LASTEXITCODE -ne 0) { throw "Address-sensitivity trace or controls inconclusive; inspect $trace" }
    $provenance['status'] = 'statistically_validated_instruction_audit_pending'
    Save-Provenance
    Write-Host "Binary SHA256: $binaryHash"
    Write-Host "Binary: $archivedBinary"
    Write-Host "Raw trace: $trace"
    Write-Host "Build provenance: $provenanceFile"
    Write-Host "EXE .text SHA256: $($provenance['text_section_sha256'])"
    Write-Host 'Instruction audit: PENDING manual review of this physical executable.'
    if (Test-Path $disassembly) { Write-Host "Disassembly: $disassembly" }
} catch {
    $provenance['status'] = 'failed_or_inconclusive'
    $provenance['failure'] = $_.Exception.Message
    Save-Provenance
    throw
}
