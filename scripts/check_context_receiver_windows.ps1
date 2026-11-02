# K4 context-prefix engineering pilot. Retain nulls and every failed attempt.
param([uint32]$Seed = 0, [switch]$RequireValidControls)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
if ($PSBoundParameters.ContainsKey('Seed')) {
    if ($Seed -eq 0) { throw 'Specify a nonzero uint32 seed.' }
    $runSeed = $Seed
} else {
    $bytes = New-Object byte[] 4
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do { $rng.GetBytes($bytes); $runSeed = [BitConverter]::ToUInt32($bytes, 0) }
        while ($runSeed -eq 0)
    } finally { $rng.Dispose() }
}
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$name = "context-receiver-windows-$stamp"
$prefix = Join-Path $out $name
$binary = "$prefix.exe"
$trace = "$prefix.log"
$nopCode = "$prefix.nop.bin"
$cpuidCode = "$prefix.cpuid.bin"
$buildLog = "$prefix.build.log"
$provenanceFile = "$prefix.build.json"
$hostFile = "$prefix.host.json"
$disassembly = "$prefix.disasm.txt"
$analysisFile = "$prefix.analysis.json"
$strictLog = "$prefix.strict.log"
$manifestFile = "$prefix.manifest.json"
$sourceArchive = "$prefix.sources.zip"
$archive = "$prefix.zip"
if (@(Get-ChildItem -LiteralPath $out -Filter "$name*" -ErrorAction Stop).Count) {
    throw "Timestamp collision: $name"
}
$sources = @((Join-Path $root 'programs\context_receiver.c'),
             (Join-Path $root 'programs\cpu_features.c'))
$analyzer = Join-Path $root 'scripts\analyze_context_receiver.py'
$sourceFiles = $sources + @(
    (Join-Path $root 'programs\cpu_features.h'),
    (Join-Path $root 'programs\context_receiver_code.h'),
    (Join-Path $root 'programs\context_receiver_layout.S'),
    (Join-Path $root 'scripts\context_receiver_contract.py'),
    (Join-Path $root 'scripts\analyze_cache_probe.py'),
    (Join-Path $root 'scripts\verify_context_receiver_layout.py'),
    (Join-Path $root 'scripts\fresh_receiver_contract.py'),
    (Join-Path $root 'protocols\CONTEXT_RECEIVER_K4.md'), $analyzer,
    $MyInvocation.MyCommand.Path, (Join-Path $root '.vscode\tasks.json'))
$provenance = [ordered]@{
    schema = 1; study = 'context_marker_k4_v1'; seed = [uint64]$runSeed
    build_start_utc = $stamp; git_head = $null; git_clean = $null
    git_status_porcelain = @(); source_sha256 = [ordered]@{}; tools = [ordered]@{}
    build_runtime_status = 'preselected'; collection_stage = 'provenance'
    control_status = 'not_evaluated'; primary_endpoint = 'p0_adjusted_training_contrast_nop_minus_cpuid'
    instruction_audit = 'runtime bytes checked automatically; linked C harness review pending'
    compilation_command = @('cl.exe', '/nologo', '/std:c11', '/O2', '/W4', '/WX', "/Fe$binary") + $sources
}
function Save-Provenance {
    $provenance | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $provenanceFile -Encoding UTF8
}
function File-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Invoke-Logged([string]$Command, [object[]]$Arguments) {
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $Command @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    $lines | Add-Content -LiteralPath $buildLog -Encoding UTF8
    $lines | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) { throw "$Command exited with $code" }
}
$failure = $null
"Preselected K4 seed: $runSeed" | Set-Content -LiteralPath $buildLog -Encoding UTF8
Save-Provenance
Write-Host "Preselected K4 context-prefix pilot seed: $runSeed"
try {
    foreach ($path in $sourceFiles) {
        $relative = $path.Substring($root.Length + 1).Replace('\', '/')
        $provenance.source_sha256[$relative] = File-Hash $path
    }
    $provenance.git_head = (& git.exe -C $root rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $provenance.git_head -notmatch '^[0-9a-f]{40}$') {
        throw 'Cannot record source revision.'
    }
    $status = @(& git.exe -C $root status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record Git status.' }
    $provenance.git_status_porcelain = $status
    $provenance.git_clean = ($status.Count -eq 0)
    Save-Provenance
    if (-not $provenance.git_clean) { throw 'Commit or stash changes before collecting K4 evidence.' }
    $sourceDir = "$prefix.sources"
    foreach ($path in $sourceFiles) {
        $relative = $path.Substring($root.Length + 1)
        $destination = Join-Path $sourceDir $relative
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $path -Destination $destination -ErrorAction Stop
    }
    Compress-Archive -Path (Join-Path $sourceDir '*') -DestinationPath $sourceArchive -ErrorAction Stop
    $provenance.collection_stage = 'toolchain_setup'
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) { throw 'Install MSVC Build Tools with Desktop development with C++.' }
    $installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'MSVC x64 tools not found.' }
    $developerCommand = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
    $setup = 'call "' + $developerCommand + '" -arch=x64 >nul && set'
    $environmentLines = & cmd.exe /d /c $setup
    if ($LASTEXITCODE -ne 0) { throw 'MSVC setup failed.' }
    foreach ($line in $environmentLines) {
        if ($line -match '^([^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
    foreach ($command in @('cl.exe', 'link.exe', 'dumpbin.exe')) {
        $resolved = Get-Command $command -ErrorAction Stop
        $provenance.tools[$command] = [ordered]@{
            path = $resolved.Source; file_version = (Get-Item $resolved.Source).VersionInfo.FileVersion
        }
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { $python = 'py.exe'; $pythonPrefix = @('-3') }
    elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { $python = 'python.exe'; $pythonPrefix = @() }
    else { throw 'Python 3 is required.' }
    $provenance.collection_stage = 'compilation'
    Save-Provenance
    Push-Location $out
    try { Invoke-Logged 'cl.exe' (@('/nologo', '/std:c11', '/O2', '/W4', '/WX', "/Fe$binary") + $sources) }
    finally { Pop-Location }
    $binaryHash = File-Hash $binary
    $provenance['binary_sha256'] = $binaryHash
    $provenance.collection_stage = 'disassembly'
    & dumpbin.exe /disasm $binary | Set-Content -LiteralPath $disassembly -Encoding ASCII
    if ($LASTEXITCODE -ne 0) { throw 'Disassembly failed.' }
    $provenance.collection_stage = 'host_metadata'
    $processor = @(Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, Revision)
    $os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
    $bios = Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion, ReleaseDate
    $system = Get-CimInstance Win32_ComputerSystem | Select-Object HypervisorPresent
    $microcode = Get-ItemPropertyValue -LiteralPath 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0' -Name 'Update Revision' -ErrorAction SilentlyContinue
    [ordered]@{
        cpu = $processor; os = $os; bios = $bios; virtualization = $system
        microcode_registry_update_revision = $microcode
        environment_assertion = 'Host inventory, not independent attestation of a bare-metal machine.'
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $hostFile -Encoding UTF8
    if ([string]$os.BuildNumber -notmatch '^[0-9]+$') { throw 'Windows build missing.' }
    $runStart = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $provenance.collection_stage = 'execution'
    Save-Provenance
    Write-Host 'Collecting 262144 episodes. This can take several minutes; the raw trace is written after collection.'
    & $binary ([string]$runSeed) $prefix 2>&1 | Set-Content -LiteralPath $trace -Encoding ASCII
    $executionExit = $LASTEXITCODE
    Add-Content -LiteralPath $trace -Value "K4_HOST,windows_build=$($os.BuildNumber),run_utc=$runStart" -Encoding ASCII
    Add-Content -LiteralPath $trace -Value "K4_BINARY,sha256=$binaryHash" -Encoding ASCII
    $provenance['execution_exit_code'] = $executionExit
    if ($executionExit -ne 0) { throw "Collector exited with $executionExit. Keep this trace." }
    $provenance.collection_stage = 'analysis'
    $analysisArgs = @($trace, '--binary', $binary, '--nop-code', $nopCode, '--cpuid-code', $cpuidCode)
    $jsonOutput = (& $python @pythonPrefix $analyzer @analysisArgs --json 2>&1 | Out-String)
    $jsonExit = $LASTEXITCODE
    $jsonOutput | Set-Content -LiteralPath $analysisFile -Encoding UTF8
    if ($jsonExit -ne 0) { throw 'Analyzer rejected the evidence. Keep the partial ZIP.' }
    $parsed = $jsonOutput | ConvertFrom-Json -ErrorAction Stop
    if (-not ($parsed.apparatus_controls_pass -is [bool]) -or
        $parsed.primary_endpoint -cne $provenance.primary_endpoint -or
        $parsed.binary_sha256 -cne $binaryHash -or
        -not $parsed.windows_collection -or
        -not $parsed.artifact_audit.runtime_snapshots_verified) { throw 'Analysis provenance mismatch.' }
    $strictOutput = (& $python @pythonPrefix $analyzer @analysisArgs --strict 2>&1 | Out-String)
    $strictExit = $LASTEXITCODE
    $strictOutput | Set-Content -LiteralPath $strictLog -Encoding UTF8
    Write-Host $strictOutput
    if (($parsed.apparatus_controls_pass -and $strictExit -ne 0) -or
        (-not $parsed.apparatus_controls_pass -and $strictExit -ne 1)) { throw 'Strict analysis mismatch.' }
    $provenance.control_status = if ($parsed.apparatus_controls_pass) { 'passed' } else { 'inconclusive' }
    $provenance['numerical_signature_detected'] = $parsed.numerical_signature_detected
    $provenance['run_outcome'] = if ($parsed.apparatus_controls_pass) {
        if ($parsed.numerical_signature_detected) { 'completed_numerical_signature_review_pending' }
        else { 'completed_eligible_null' }
    } else { 'completed_inconclusive' }
    $provenance.build_runtime_status = 'analyzed'
    $provenance.collection_stage = 'complete'
} catch {
    $failure = $_.Exception.Message
    $provenance.build_runtime_status = 'failed_at_' + $provenance.collection_stage
    $provenance['failure'] = $failure
    Write-Warning "K4 run could not complete: $failure"
} finally {
    $provenance['execution_end_utc'] = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    Save-Provenance
    $artifactPaths = @($binary, $trace, $nopCode, $cpuidCode, $buildLog, $provenanceFile,
                       $hostFile, $disassembly, $analysisFile, $strictLog, $sourceArchive) |
                       Where-Object { Test-Path -LiteralPath $_ }
    $hashes = [ordered]@{}
    foreach ($path in $artifactPaths) { $hashes[(Split-Path $path -Leaf)] = File-Hash $path }
    [ordered]@{
        schema = 1; study = 'context_marker_k4_v1'; git_head = $provenance.git_head
        build_runtime_status = $provenance.build_runtime_status; control_status = $provenance.control_status
        files_sha256 = $hashes
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
    Compress-Archive -LiteralPath (@($artifactPaths) + @($manifestFile)) -DestinationPath $archive -ErrorAction Stop
    Write-Host "READY TO SHARE (including nulls or failures): $archive"
    Write-Host "Evidence ZIP SHA256: $(File-Hash $archive)"
    Write-Host 'Mechanism review remains pending. One run does not establish a replicated physical result.'
}
if ($null -ne $failure) { throw "K4 failed: $failure. Retain ZIP: $archive" }
if ($provenance.control_status -ne 'passed') {
    if ($RequireValidControls) { throw "K4 controls inconclusive. Retain ZIP: $archive" }
    Write-Warning "COLLECTION COMPLETE; SCIENTIFIC RESULT INCONCLUSIVE. Failed gates remain failed. Retain ZIP: $archive"
    Write-Host 'Use -RequireValidControls for an automation gate that exits nonzero on inconclusive controls.'
}
exit 0
