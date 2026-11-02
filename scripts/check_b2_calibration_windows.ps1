# Standalone B2 v2 apparatus calibration. It does not measure a Fractal effect.
param([uint32]$Seed = 0)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null

if ($PSBoundParameters.ContainsKey('Seed')) {
    if ($Seed -eq 0) { throw 'Specify a nonzero 32-bit seed.' }
    $runSeed = $Seed
} else {
    $bytes = New-Object byte[] 4
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $rng.GetBytes($bytes)
            $runSeed = [BitConverter]::ToUInt32($bytes, 0)
        } while ($runSeed -eq 0)
    } finally { $rng.Dispose() }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$name = "b2-calibration-windows-$stamp"
$trace = Join-Path $out "$name.log"
$binary = Join-Path $out "$name.exe"
$object = Join-Path $out "$name.branch.obj"
$buildLog = Join-Path $out "$name.build.log"
$provenanceFile = Join-Path $out "$name.build.json"
$disassembly = Join-Path $out "$name.disasm.txt"
$analysisFile = Join-Path $out "$name.analysis.json"
$strictLog = Join-Path $out "$name.strict.log"
$manifestFile = Join-Path $out "$name.manifest.json"
$archive = Join-Path $out "$name.zip"
foreach ($path in @($trace, $binary, $object, $buildLog, $provenanceFile, $disassembly,
                  $analysisFile, $strictLog, $manifestFile, $archive)) {
    if (Test-Path $path) { throw "Run timestamp collision: $name" }
}

$assembly = Join-Path $root 'programs\history_b2_windows.asm'
$sources = @((Join-Path $root 'programs\b2_calibration_windows.c'),
             (Join-Path $root 'programs\cpu_features.c'))
$analyzer = Join-Path $root 'scripts\analyze_b2_calibration.py'
$sourceFiles = @($assembly) + $sources + @($analyzer, $MyInvocation.MyCommand.Path,
                                          (Join-Path $root 'programs\cpu_features.h'),
                                          (Join-Path $root 'scripts\analyze_branch_batch.py'),
                                          (Join-Path $root 'scripts\analyze_cache_probe.py'),
                                          (Join-Path $root '.vscode\tasks.json'),
                                          (Join-Path $root 'protocols\B2_CALIBRATION_V2.md'))
$provenance = [ordered]@{
    schema = 1
    study = 'b2_v2_apparatus_calibration_only'
    seed = [uint64]$runSeed
    build_start_utc = $stamp
    git_head = $null
    git_clean = $null
    git_status_porcelain = @()
    source_sha256 = [ordered]@{}
    tools = [ordered]@{}
    assembly_command = @('ml64.exe', '/nologo', '/c', "/Fo$object", $assembly)
    compilation_command = @('cl.exe', '/nologo', '/std:c11', '/O2', '/W4', '/WX',
                            "/Fe$binary") + $sources + @($object)
    build_runtime_status = 'preselected'
    collection_stage = 'preselected'
    control_status = 'not_evaluated'
    selected_candidate = $null
    instruction_audit = 'pending manual review of archived executable disassembly'
}
function Save-Provenance {
    $provenance | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $provenanceFile -Encoding UTF8
}
function File-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
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
            $size = [BitConverter]::ToInt32($image, $entry + 16)
            $offset = [BitConverter]::ToInt32($image, $entry + 20)
            if ($offset -lt 0 -or $size -le 0 -or $offset + $size -gt $image.Length) {
                throw 'Invalid .text section bounds.'
            }
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                return [BitConverter]::ToString(
                    $sha.ComputeHash($image, $offset, $size)).Replace('-', '').ToLowerInvariant()
            } finally { $sha.Dispose() }
        }
    }
    throw 'No .text section found in executable.'
}

$failure = $null
"Preselected B2 v2 calibration seed: $runSeed" | Set-Content -LiteralPath $buildLog -Encoding ASCII
Save-Provenance
Write-Host "Preselected B2 v2 calibration seed: $runSeed"
try {
    $provenance.collection_stage = 'source_and_git_provenance'
    foreach ($path in $sourceFiles) {
        if (-not (Test-Path $path)) { throw "Missing source: $path" }
        $relative = $path.Substring($root.Length + 1).Replace('\', '/')
        $provenance.source_sha256[$relative] = File-Hash $path
    }
    $gitHead = (& git.exe -C $root rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $gitHead -notmatch '^[0-9a-f]{40}$') {
        throw 'Could not record Git HEAD.'
    }
    $provenance.git_head = $gitHead
    $gitStatus = @(& git.exe -C $root status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Could not record Git working tree state.' }
    $provenance.git_status_porcelain = $gitStatus
    $provenance.git_clean = ($gitStatus.Count -eq 0)
    Save-Provenance
    if (-not $provenance.git_clean) {
        throw 'Commit or stash source changes before collecting calibration evidence; the tree is dirty.'
    }

    $provenance.collection_stage = 'toolchain_setup'
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
    foreach ($command in @('ml64.exe', 'cl.exe', 'link.exe', 'dumpbin.exe')) {
        $resolved = Get-Command $command -ErrorAction SilentlyContinue
        if (-not $resolved) { throw "Missing $command" }
        $toolPath = $resolved.Source
        $provenance.tools[$command] = [ordered]@{
            path = $toolPath
            file_version = (Get-Item $toolPath).VersionInfo.FileVersion
            product_version = (Get-Item $toolPath).VersionInfo.ProductVersion
        }
    }
    Save-Provenance

    $provenance.collection_stage = 'assembly'
    & ml64.exe /nologo /c "/Fo$object" $assembly 2>&1 |
        Tee-Object -FilePath $buildLog -Append
    if ($LASTEXITCODE -ne 0) { throw 'B2 v2 branch-site assembly failed.' }
    $provenance.collection_stage = 'compilation'
    Push-Location $out
    try {
        & cl.exe /nologo /std:c11 /O2 /W4 /WX "/Fe$binary" @sources $object 2>&1 |
            Tee-Object -FilePath $buildLog -Append
        if ($LASTEXITCODE -ne 0) { throw 'B2 v2 compilation failed.' }
    } finally { Pop-Location }

    $binaryHash = File-Hash $binary
    $provenance['binary_sha256'] = $binaryHash
    $provenance['text_section_sha256'] = Get-TextSha256 $binary
    $provenance.collection_stage = 'disassembly'
    & dumpbin.exe /disasm $binary | Set-Content -LiteralPath $disassembly -Encoding ASCII
    if ($LASTEXITCODE -ne 0) { throw 'Could not save executable disassembly.' }
    $provenance['disassembly_sha256'] = File-Hash $disassembly
    $provenance.build_runtime_status = 'built'
    Save-Provenance

    $runStartUtc = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $provenance['execution_start_utc'] = $runStartUtc
    $provenance.collection_stage = 'execution'
    & $binary ([string]$runSeed) 2>&1 | Set-Content -LiteralPath $trace -Encoding ASCII
    if ($LASTEXITCODE -ne 0) { throw 'B2 v2 executable returned a nonzero exit code.' }
    $provenance.collection_stage = 'host_metadata'
    $windowsBuild = (Get-CimInstance Win32_OperatingSystem -Property BuildNumber).BuildNumber
    if ([string]$windowsBuild -notmatch '^[0-9]+$') { throw 'Could not record Windows build number.' }
    Add-Content -LiteralPath $trace -Value "B2CAL_HOST,windows_build=$windowsBuild,run_utc=$runStartUtc" -Encoding ASCII
    Add-Content -LiteralPath $trace -Value "B2CAL_BINARY,sha256=$binaryHash" -Encoding ASCII
    $provenance.build_runtime_status = 'trace_recorded'
    Save-Provenance

    $provenance.collection_stage = 'raw_trace_analysis'
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $python = 'py.exe'
        $pythonPrefix = @('-3')
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $python = 'python.exe'
        $pythonPrefix = @()
    } else { throw 'Python 3 is required to analyze the raw trace.' }
    $jsonOutput = (& $python @pythonPrefix $analyzer $trace --json 2>&1 | Out-String)
    $jsonExit = $LASTEXITCODE
    $jsonOutput | Set-Content -LiteralPath $analysisFile -Encoding UTF8
    if ($jsonExit -ne 0) { throw 'Raw trace analyzer rejected this trace; inspect archived analysis output.' }
    try { $parsed = $jsonOutput | ConvertFrom-Json -ErrorAction Stop }
    catch { throw 'Raw trace analyzer did not return valid JSON.' }
    $gate = $parsed.PSObject.Properties['calibration_controls_pass']
    if ($null -eq $gate -or -not ($gate.Value -is [bool])) {
        throw 'Analyzer JSON lacks a Boolean calibration_controls_pass gate.'
    }
    $candidate = $parsed.PSObject.Properties['selected_candidate']
    if ($null -eq $candidate -or
        ($gate.Value -and @('dose4', 'dose8') -notcontains $candidate.Value) -or
        (-not $gate.Value -and $null -ne $candidate.Value)) {
        throw 'Analyzer JSON has an inconsistent selected_candidate.'
    }
    $provenance.selected_candidate = $parsed.selected_candidate
    $provenance.collection_stage = 'strict_analysis'
    $strictOutput = (& $python @pythonPrefix $analyzer $trace --strict 2>&1 | Out-String)
    $strictExit = $LASTEXITCODE
    $strictOutput | Set-Content -LiteralPath $strictLog -Encoding UTF8
    Write-Host $strictOutput
    $provenance['strict_analyzer_exit_code'] = $strictExit
    if ($gate.Value -and $strictExit -ne 0) {
        throw 'Analyzer gate passed, but strict analyzer returned nonzero.'
    }
    if (-not $gate.Value -and $strictExit -eq 0) {
        throw 'Analyzer gate failed, but strict analyzer returned success.'
    }
    $provenance.control_status = if ($gate.Value) { 'passed' } else { 'inconclusive' }
    $provenance.build_runtime_status = 'analyzed'
    $provenance.collection_stage = 'complete'
} catch {
    $failure = $_.Exception.Message
    if ($provenance.build_runtime_status -ne 'analyzed') {
        $provenance.build_runtime_status = 'failed_at_' + $provenance.collection_stage
    }
    $provenance['failure'] = $failure
    Add-Content -LiteralPath $buildLog -Value "Failure: $failure" -Encoding ASCII
    Write-Warning "B2 v2 calibration could not complete: $failure"
} finally {
    $provenance['execution_end_utc'] = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    Save-Provenance
    $artifactPaths = @($binary, $trace, $buildLog, $provenanceFile, $disassembly,
                       $analysisFile, $strictLog) | Where-Object { Test-Path $_ }
    $files = [ordered]@{}
    foreach ($path in $artifactPaths) {
        $files[(Split-Path $path -Leaf)] = File-Hash $path
    }
    $manifest = [ordered]@{
        schema = 1
        study = 'b2_v2_apparatus_calibration_only'
        created_utc = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
        git_head = $provenance.git_head
        git_clean = $provenance.git_clean
        build_runtime_status = $provenance.build_runtime_status
        control_status = $provenance.control_status
        files_sha256 = $files
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
    Compress-Archive -LiteralPath (@($artifactPaths) + @($manifestFile)) -DestinationPath $archive -CompressionLevel Optimal -ErrorAction Stop
    if ($provenance.build_runtime_status -eq 'analyzed') {
        Write-Host "READY TO SHARE: $archive"
    } else {
        Write-Host "Diagnostic evidence ZIP (partial): $archive"
    }
    Write-Host "Evidence ZIP SHA256: $(File-Hash $archive)"
    Write-Host "Build/runtime: $($provenance.build_runtime_status); controls: $($provenance.control_status)"
    Write-Host 'Instruction audit: PENDING manual review of this archived executable.'
}
if ($null -ne $failure) { throw "B2 v2 calibration failed: $failure. Evidence ZIP: $archive" }
if ($provenance.control_status -ne 'passed') {
    throw "B2 v2 calibration controls inconclusive; retain and share ZIP: $archive"
}
