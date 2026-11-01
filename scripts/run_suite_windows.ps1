# Run the full Windows pilot or a recorded full/focused follow-up session.
# Every study script independently builds, archives its EXE/trace and runs strict trace analysis.
param(
    [ValidateSet('Pilot', 'Followup')][string]$Phase = 'Pilot',
    [ValidateSet('Full', 'Focus')][string]$StudySet = 'Full',
    [ValidateRange(1, 8)][int]$Rounds = 1,
    [ValidateRange(-1, 62)][int]$LogicalCpu = -1
)
$ErrorActionPreference = 'Stop'
if ($Phase -eq 'Pilot' -and $Rounds -ne 1) {
    throw 'Run one physical pilot of each study, then inspect the controls and Windows binaries before follow-up rounds.'
}
if ($Phase -eq 'Pilot' -and $StudySet -ne 'Full') {
    throw 'The first physical pilot must include the full study set.'
}
if ($StudySet -eq 'Focus' -and $Rounds -ne 1) {
    throw 'Run one focused follow-up per session so each session remains a separate replication unit.'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
# Each check script imports VsDevCmd.bat variables into this PowerShell process.
# Without restoring the environment, later checks repeatedly expand PATH and
# cmd.exe eventually rejects the developer-command invocation as too long.
$initialEnvironment = [Environment]::GetEnvironmentVariables('Process')
function Restore-InitialEnvironment {
    $currentEnvironment = [Environment]::GetEnvironmentVariables('Process')
    foreach ($name in @($currentEnvironment.Keys)) {
        if ([string]$name -notmatch '^=' -and -not $initialEnvironment.Contains($name)) {
            [Environment]::SetEnvironmentVariable([string]$name, $null, 'Process')
        }
    }
    foreach ($name in @($initialEnvironment.Keys)) {
        if ([string]$name -notmatch '^=') {
            [Environment]::SetEnvironmentVariable([string]$name, [string]$initialEnvironment[$name], 'Process')
        }
    }
}
if ($LogicalCpu -ge 0) {
    if ([IntPtr]::Size -ne 8) { throw 'Use 64-bit Windows PowerShell for a requested logical CPU.' }
    $requestedMask = [int64](([uint64]1) -shl $LogicalCpu)
    $currentProcess = [Diagnostics.Process]::GetCurrentProcess()
    $currentProcess.ProcessorAffinity = [IntPtr]$requestedMask
    if ($currentProcess.ProcessorAffinity.ToInt64() -ne $requestedMask) {
        throw "Could not restrict this session to logical CPU $LogicalCpu."
    }
}
$baselineStudies = @(
    [pscustomobject]@{ name = 'cache_controls'; script = 'check_windows.ps1'; prefix = 'cache-probe-windows-'; seeded = $false },
    [pscustomobject]@{ name = 'spec_cache_receiver'; script = 'check_spec_windows.ps1'; prefix = 'spec-probe-windows-'; seeded = $false },
    [pscustomobject]@{ name = 'branch_batch'; script = 'check_branch_batch_windows.ps1'; prefix = 'branch-batch-windows-'; seeded = $true },
    [pscustomobject]@{ name = 'single_branch_latency'; script = 'check_branch_latency_windows.ps1'; prefix = 'branch-latency-windows-'; seeded = $false },
    [pscustomobject]@{ name = 'decision_source_a'; script = 'check_decision_source_windows.ps1'; prefix = 'decision-source-windows-'; seeded = $true },
    [pscustomobject]@{ name = 'history_probe_b1'; script = 'check_history_probe_windows.ps1'; prefix = 'history-probe-windows-'; seeded = $true }
)
$studies = @(
    [pscustomobject]@{ name = 'history_b2'; script = 'check_history_b2_windows.ps1'; prefix = 'history-b2-windows-' },
    [pscustomobject]@{ name = 'pattern_complexity'; script = 'check_pattern_complexity_windows.ps1'; prefix = 'pattern-complexity-windows-' },
    [pscustomobject]@{ name = 'history_decay'; script = 'check_history_decay_windows.ps1'; prefix = 'history-decay-windows-' },
    [pscustomobject]@{ name = 'training_dose'; script = 'check_training_dose_windows.ps1'; prefix = 'training-dose-windows-' },
    [pscustomobject]@{ name = 'address_sensitivity'; script = 'check_address_sensitivity_windows.ps1'; prefix = 'address-sensitivity-windows-' },
    [pscustomobject]@{ name = 'indirect_target'; script = 'check_indirect_target_windows.ps1'; prefix = 'indirect-target-windows-' },
    [pscustomobject]@{ name = 'indirect_cache'; script = 'check_indirect_cache_windows.ps1'; prefix = 'indirect-cache-windows-' },
    [pscustomobject]@{ name = 'prelude_sweep'; script = 'check_prelude_sweep_windows.ps1'; prefix = 'prelude-sweep-windows-' }
)
if ($StudySet -eq 'Focus') {
    $focusBaselines = @('cache_controls', 'branch_batch', 'decision_source_a', 'history_probe_b1')
    $focusStudies = @('pattern_complexity', 'history_b2', 'history_decay',
                      'address_sensitivity', 'indirect_cache')
    $baselineStudies = @($baselineStudies | Where-Object { $_.name -in $focusBaselines })
    $studies = @($studies | Where-Object { $_.name -in $focusStudies })
    if ($baselineStudies.Count -ne $focusBaselines.Count -or
        $studies.Count -ne $focusStudies.Count) {
        throw 'Focused follow-up study selection is incomplete.'
    }
}
$sourceFiles = @(
    '.vscode/tasks.json', 'README.md', 'EXPLORATORY_HISTORY_B2.md',
    'WINDOWS_MULTI_EXPERIMENT_SUITE.md', 'WINDOWS_RESEARCH_PROGRAM.md',
    'FOLLOWUP_2026_10_31.md', 'FOLLOWUP_AMENDMENT_2026_11_01.md',
    'PAPER_CLAIM_MATRIX.md', 'PHANTOM_FEASIBILITY.md',
    'INDIRECT_TARGET_STUDY.md', 'INDIRECT_CACHE_STUDY.md', 'PRELUDE_SWEEP_STUDY.md',
    'programs/utest.c', 'programs/cache_probe_windows.c',
    'programs/branch_batch_windows.c', 'programs/branch_latency_windows.c',
    'programs/spec_probe_windows.c', 'programs/spec_branch_windows.asm',
    'programs/decision_source_windows.c', 'programs/decision_source_windows.asm',
    'programs/history_probe_windows.c', 'programs/history_probe_windows.asm',
    'programs/history_b2_windows.c', 'programs/history_b2_windows.asm',
    'programs/pattern_complexity_windows.c', 'programs/pattern_complexity_windows.asm',
    'programs/history_decay_windows.c', 'programs/history_decay_windows.asm',
    'programs/training_dose_windows.c', 'programs/training_dose_windows.asm',
    'programs/address_sensitivity_windows.c', 'programs/address_sensitivity_windows.asm',
    'programs/indirect_target_windows.c', 'programs/indirect_target_windows.asm',
    'programs/indirect_cache_windows.c', 'programs/indirect_cache_windows.asm',
    'programs/prelude_sweep_windows.c', 'programs/prelude_sweep_windows.asm',
    'programs/cache_probe.h', 'programs/cpu_features.c', 'programs/cpu_features.h',
    'scripts/check_windows.ps1', 'scripts/analyze_cache_probe.py',
    'scripts/check_spec_windows.ps1', 'scripts/analyze_spec_probe.py',
    'scripts/check_branch_batch_windows.ps1', 'scripts/analyze_branch_batch.py',
    'scripts/check_branch_latency_windows.ps1', 'scripts/analyze_branch_latency.py',
    'scripts/check_decision_source_windows.ps1', 'scripts/analyze_decision_source.py',
    'scripts/check_history_probe_windows.ps1', 'scripts/analyze_history_probe.py',
    'scripts/check_history_b2_windows.ps1', 'scripts/analyze_history_b2.py',
    'scripts/check_pattern_complexity_windows.ps1', 'scripts/analyze_pattern_complexity.py',
    'scripts/check_history_decay_windows.ps1', 'scripts/analyze_history_decay.py',
    'scripts/check_training_dose_windows.ps1', 'scripts/analyze_training_dose.py',
    'scripts/check_address_sensitivity_windows.ps1', 'scripts/analyze_address_sensitivity.py',
    'scripts/check_indirect_target_windows.ps1', 'scripts/analyze_indirect_target.py',
    'scripts/check_indirect_cache_windows.ps1', 'scripts/analyze_indirect_cache.py',
    'scripts/check_prelude_sweep_windows.ps1', 'scripts/analyze_prelude_sweep.py',
    'scripts/audit_suite_evidence.py',
    'scripts/summarize_suite_followup.py',
    'scripts/record_windows_host.ps1', 'scripts/run_suite_windows.ps1',
    'scripts/package_suite_windows.ps1'
)
$fileHashes = [ordered]@{}
foreach ($relative in $sourceFiles) {
    $path = Join-Path $root $relative
    if (-not (Test-Path $path)) { throw "Suite source missing: $relative" }
    $fileHashes[$relative] = (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$gitHead = (& git.exe -C $root rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $gitHead -notmatch '^[0-9a-f]{40}$') { throw 'Git HEAD could not be recorded.' }
$gitStatus = @(& git.exe -C $root status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0) { throw 'Git working-tree status could not be recorded.' }

$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    function New-NonzeroSeed {
        $bytes = New-Object byte[] 4
        do {
            $rng.GetBytes($bytes)
            $value = [BitConverter]::ToUInt32($bytes, 0)
        } while ($value -eq 0)
        return $value
    }
    $suiteSeed = New-NonzeroSeed
    $used = @{}
    $runs = New-Object System.Collections.ArrayList
    $baselinePosition = 0
    foreach ($study in $baselineStudies) {
        $baselinePosition++
        $seed = $null
        if ($study.seeded) {
            do { $seed = New-NonzeroSeed } while ($used.ContainsKey([string]$seed))
            $used[[string]$seed] = $true
        }
        [void]$runs.Add([ordered]@{
            stage = 'session_baseline'
            round = 0
            position = $baselinePosition
            study = $study.name
            script = $study.script
            prefix = $study.prefix
            seed = $seed
            status = 'planned'
        })
    }
    $baseOrder = @(0..($studies.Count - 1))
    for ($i = $baseOrder.Count - 1; $i -gt 0; --$i) {
        $bytes = New-Object byte[] 4
        $rng.GetBytes($bytes)
        $j = [int]([BitConverter]::ToUInt32($bytes, 0) % ($i + 1))
        $temp = $baseOrder[$i]
        $baseOrder[$i] = $baseOrder[$j]
        $baseOrder[$j] = $temp
    }
    for ($round = 0; $round -lt $Rounds; $round++) {
        for ($position = 0; $position -lt $studies.Count; $position++) {
            $study = $studies[$baseOrder[($position + $round) % $studies.Count]]
            do { $seed = New-NonzeroSeed } while ($used.ContainsKey([string]$seed))
            $used[[string]$seed] = $true
            [void]$runs.Add([ordered]@{
                stage = 'exploratory'
                round = $round + 1
                position = $position + 1
                study = $study.name
                script = $study.script
                prefix = $study.prefix
                seed = [uint64]$seed
                status = 'planned'
            })
        }
    }
} finally {
    $rng.Dispose()
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$sessionDir = Join-Path $out ('suite-{0}-{1:x8}' -f $stamp, $suiteSeed)
New-Item -ItemType Directory -Path $sessionDir -ErrorAction Stop | Out-Null
$planPath = Join-Path $sessionDir 'session.json'
$evidenceArchive = Join-Path $out ('suite-evidence-{0}.zip' -f (Split-Path $sessionDir -Leaf))
$archiveError = $null
$plan = [ordered]@{
    schema = 1
    phase = $Phase
    study_set = $StudySet
    started_utc = $stamp
    suite_seed = [uint64]$suiteSeed
    git_head = $gitHead
    git_status_porcelain = $gitStatus
    requested_logical_cpu = $LogicalCpu
    source_sha256 = $fileHashes
    host_snapshot = $null
    toolchain = $null
    windows_binary_audit = 'required before interpreting physical outcomes'
    runs = $runs
}
function Save-Session {
    $pending = Join-Path $sessionDir ('session-{0}.pending' -f [guid]::NewGuid().ToString('N'))
    $plan | ConvertTo-Json -Depth 12 | Set-Content -Path $pending -Encoding UTF8
    if ([IO.File]::Exists($planPath)) {
        [IO.File]::Replace($pending, $planPath,
                           (Join-Path $sessionDir 'session.previous.json'))
    } else {
        [IO.File]::Move($pending, $planPath)
    }
}
Save-Session
Write-Host "Preselected suite plan: $planPath"
Write-Host "Phase: $Phase; study set: $StudySet; exploratory study rounds: $Rounds; Git HEAD: $gitHead"
foreach ($entry in $runs) {
    Write-Host ("Stage {0}, round {1}, position {2}: {3}, seed {4}" -f $entry.stage, $entry.round, $entry.position, $entry.study, $entry.seed)
}

try {
    $hostBefore = @(Get-ChildItem -Path $out -Filter 'host-windows-*.json' -File |
        ForEach-Object { $_.FullName })
    & (Join-Path $PSScriptRoot 'record_windows_host.ps1')
    $newHosts = @(Get-ChildItem -Path $out -Filter 'host-windows-*.json' -File |
        Where-Object { $hostBefore -notcontains $_.FullName })
    if ($newHosts.Count -ne 1) { throw 'Expected exactly one new host snapshot.' }
    $hostFile = $newHosts[0]
    $plan.host_snapshot = [ordered]@{
        path = $hostFile.FullName
        sha256 = (Get-FileHash -Path $hostFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Save-Session
    foreach ($entry in $runs) {
        Restore-InitialEnvironment
        $tracePattern = '^' + [regex]::Escape($entry.prefix) + '\d{8}T\d{6}Z\.log$'
        $artifactPattern = '^' + [regex]::Escape($entry.prefix) + '\d{8}T\d{6}Z\.(log|exe|build\.json|build\.log|disasm\.txt)$'
        $beforeArtifacts = @(Get-ChildItem -Path $out -Filter ($entry.prefix + '*') -File |
            Where-Object { $_.Name -match $artifactPattern } |
            ForEach-Object { $_.FullName })
        $before = @(Get-ChildItem -Path $out -Filter ($entry.prefix + '*.log') -File |
            Where-Object { $_.Name -match $tracePattern } |
            ForEach-Object { $_.FullName })
        $entry.status = 'running'
        $entry.started_utc = (Get-Date).ToUniversalTime().ToString('o')
        $entry.transcript_path = Join-Path $sessionDir ('round-{0}-{1}.txt' -f $entry.round, $entry.study)
        Save-Session
        Write-Host ("Running {0} (stage {1}, round {2}, position {3})" -f $entry.study, $entry.stage, $entry.round, $entry.position)
        $transcriptStarted = $false
        try {
            Start-Transcript -Path $entry.transcript_path -ErrorAction Stop | Out-Null
            $transcriptStarted = $true
            if ($null -eq $entry.seed) {
                & (Join-Path $PSScriptRoot $entry.script)
            } else {
                & (Join-Path $PSScriptRoot $entry.script) -Seed ([uint32]$entry.seed)
            }
            if ($LASTEXITCODE -ne 0) { throw "Study process returned exit code $LASTEXITCODE" }
            $entry.status = 'validated_trace_pending_binary_audit'
        } catch {
            $entry.status = 'failed_preserved'
            $entry.error = $_.Exception.Message
            Write-Warning ("Study {0} did not pass its build/run/strict-analysis step: {1}" -f $entry.study, $entry.error)
        } finally {
            if ($transcriptStarted) {
                try { Stop-Transcript -ErrorAction Stop | Out-Null }
                catch { $entry.transcript_error = $_.Exception.Message }
            }
            if (Test-Path $entry.transcript_path) {
                $entry.transcript_sha256 = (Get-FileHash -Path $entry.transcript_path -Algorithm SHA256).Hash.ToLowerInvariant()
            }
            $entry.new_artifacts = @(Get-ChildItem -Path $out -Filter ($entry.prefix + '*') -File |
                Where-Object { $_.Name -match $artifactPattern -and $beforeArtifacts -notcontains $_.FullName } |
                ForEach-Object {
                    [ordered]@{
                        path = $_.FullName
                        sha256 = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                    }
                })
            $newTraces = @(Get-ChildItem -Path $out -Filter ($entry.prefix + '*.log') -File |
                Where-Object { $_.Name -match $tracePattern -and $before -notcontains $_.FullName })
            $entry.traces = @($newTraces | ForEach-Object {
                [ordered]@{
                    path = $_.FullName
                    sha256 = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                }
            })
            $entry.exes = @($newTraces | ForEach-Object {
                $exe = [IO.Path]::ChangeExtension($_.FullName, '.exe')
                if (Test-Path $exe) {
                    [ordered]@{
                        path = $exe
                        sha256 = (Get-FileHash -Path $exe -Algorithm SHA256).Hash.ToLowerInvariant()
                    }
                }
            })
            $entry.sidecars = @($newTraces | ForEach-Object {
                $base = $_.FullName.Substring(0, $_.FullName.Length - 4)
                foreach ($extension in @('.build.json', '.build.log', '.disasm.txt')) {
                    $sidecar = $base + $extension
                    if (Test-Path $sidecar) {
                        [ordered]@{
                            path = $sidecar
                            sha256 = (Get-FileHash -Path $sidecar -Algorithm SHA256).Hash.ToLowerInvariant()
                        }
                    }
                }
            })
            $dumpbin = Get-Command dumpbin.exe -ErrorAction SilentlyContinue
            if ($dumpbin -and $entry.exes.Count -eq 1) {
                $disassembly = Join-Path $sessionDir ('round-{0}-{1}-disasm.txt' -f $entry.round, $entry.study)
                try {
                    & $dumpbin.Source /DISASM $entry.exes[0].path |
                        Out-File -FilePath $disassembly -Encoding ascii
                    if ($LASTEXITCODE -eq 0) {
                        $entry.disassembly = [ordered]@{
                            path = $disassembly
                            sha256 = (Get-FileHash -Path $disassembly -Algorithm SHA256).Hash.ToLowerInvariant()
                        }
                    } else {
                        $entry.disassembly_error = 'dumpbin /DISASM failed; physical instruction audit remains pending.'
                    }
                } catch {
                    $entry.disassembly_error = $_.Exception.Message
                }
            } else {
                $entry.disassembly_error = 'dumpbin was unavailable or no single paired EXE was found.'
            }
            if ($entry.status -eq 'validated_trace_pending_binary_audit' -and
                ($entry.traces.Count -ne 1 -or $entry.exes.Count -ne 1)) {
                $entry.status = 'failed_preserved'
                $entry.error = 'Expected exactly one timestamped trace and matching executable.'
            }
            if ($LogicalCpu -ge 0 -and $entry.stage -eq 'exploratory' -and
                $entry.traces.Count -eq 1) {
                $affinityLine = @(Get-Content -Path $entry.traces[0].path -TotalCount 8 |
                    Where-Object { $_ -match '^HOST_AFFINITY_CPU=([0-9]+)$' })
                if ($affinityLine.Count -ne 1 -or
                    [int]($affinityLine[0].Split('=')[1]) -ne $LogicalCpu) {
                    $entry.status = 'failed_preserved'
                    $entry.error = "Trace affinity did not confirm requested logical CPU $LogicalCpu."
                }
            }
            $toolchain = [ordered]@{}
            foreach ($tool in @('cl.exe', 'ml64.exe', 'link.exe', 'dumpbin.exe')) {
                $command = Get-Command $tool -ErrorAction SilentlyContinue
                if ($command) {
                    $toolchain[$tool] = [ordered]@{
                        path = $command.Source
                        file_version = (Get-Item $command.Source).VersionInfo.FileVersion
                    }
                }
            }
            $plan.toolchain = $toolchain
            $entry.ended_utc = (Get-Date).ToUniversalTime().ToString('o')
            Save-Session
        }
        if ($entry.status -ne 'validated_trace_pending_binary_audit') {
            Write-Host ("Retained study record for {0}; continuing the complete suite." -f $entry.study)
        }
    }
} catch {
    $plan.failure = $_.Exception.Message
    Save-Session
    Write-Warning "Suite interrupted; preserved session plan and failure at $planPath"
    throw
} finally {
    try {
        $plan.ended_utc = (Get-Date).ToUniversalTime().ToString('o')
        Save-Session
        try {
            # Package the exact session, including failed-control attempts, after its final record is saved.
            & (Join-Path $PSScriptRoot 'package_suite_windows.ps1') -SessionDirectory $sessionDir
            if (-not (Test-Path -LiteralPath $evidenceArchive -PathType Leaf)) {
                throw "Evidence packager did not create $evidenceArchive"
            }
            Write-Host "READY TO SHARE: $evidenceArchive"
        } catch {
            $archiveError = $_.Exception.Message
            Write-Warning ("Automatic evidence packaging failed: {0}" -f $archiveError)
        }
    } finally {
        Restore-InitialEnvironment
    }
}
Write-Host "Suite completed. Session record: $planPath"
if ($archiveError) { throw "Session evidence ZIP unavailable: $archiveError" }
Write-Host 'Inspect each physical Windows EXE and its controls before interpreting the pilot or scheduling follow-up rounds.'
$failed = @($runs | Where-Object { $_.status -ne 'validated_trace_pending_binary_audit' })
if ($failed.Count -gt 0) {
    throw ("{0} of {1} study runs did not pass build/run/strict analysis. All attempted runs remain in the session record." -f $failed.Count, $runs.Count)
}
