# Run one complete exploratory pilot, or three rotated follow-up rounds, on the native Windows host.
# Every study script independently builds, archives its EXE/trace and runs strict trace analysis.
param(
    [ValidateSet('Pilot', 'Followup')][string]$Phase = 'Pilot',
    [ValidateRange(1, 3)][int]$Rounds = 1
)
$ErrorActionPreference = 'Stop'
if ($Rounds -ne 1 -and $Rounds -ne 3) { throw 'Rounds must be 1 or 3.' }
if ($Phase -eq 'Pilot' -and $Rounds -ne 1) {
    throw 'Run one physical pilot of each study, then inspect the controls and Windows binaries before follow-up rounds.'
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$studies = @(
    [pscustomobject]@{ name = 'history_b2'; script = 'check_history_b2_windows.ps1'; prefix = 'history-b2-windows-' },
    [pscustomobject]@{ name = 'pattern_complexity'; script = 'check_pattern_complexity_windows.ps1'; prefix = 'pattern-complexity-windows-' },
    [pscustomobject]@{ name = 'history_decay'; script = 'check_history_decay_windows.ps1'; prefix = 'history-decay-windows-' }
)
$sourceFiles = @(
    'programs/history_b2_windows.c', 'programs/history_b2_windows.asm',
    'programs/pattern_complexity_windows.c', 'programs/pattern_complexity_windows.asm',
    'programs/history_decay_windows.c', 'programs/history_decay_windows.asm',
    'programs/cpu_features.c', 'programs/cpu_features.h',
    'scripts/check_history_b2_windows.ps1', 'scripts/analyze_history_b2.py',
    'scripts/check_pattern_complexity_windows.ps1', 'scripts/analyze_pattern_complexity.py',
    'scripts/check_history_decay_windows.ps1', 'scripts/analyze_history_decay.py',
    'scripts/analyze_branch_batch.py', 'scripts/analyze_cache_probe.py',
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
    $baseOrder = @(0, 1, 2)
    if (($suiteSeed -band 1) -ne 0) { $baseOrder = @(2, 1, 0) }
    $rotation = [int]($suiteSeed % 3)
    $baseOrder = @($baseOrder[$rotation], $baseOrder[($rotation + 1) % 3], $baseOrder[($rotation + 2) % 3])
    $runs = New-Object System.Collections.ArrayList
    for ($round = 0; $round -lt $Rounds; $round++) {
        for ($position = 0; $position -lt 3; $position++) {
            $study = $studies[$baseOrder[($position + $round) % 3]]
            do { $seed = New-NonzeroSeed } while ($used.ContainsKey([string]$seed))
            $used[[string]$seed] = $true
            [void]$runs.Add([ordered]@{
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
$plan = [ordered]@{
    schema = 1
    phase = $Phase
    started_utc = $stamp
    suite_seed = [uint64]$suiteSeed
    git_head = $gitHead
    git_status_porcelain = $gitStatus
    source_sha256 = $fileHashes
    host_snapshot = $null
    toolchain = $null
    windows_binary_audit = 'required before interpreting physical outcomes'
    runs = $runs
}
function Save-Session {
    $plan | ConvertTo-Json -Depth 12 | Set-Content -Path $planPath -Encoding UTF8
}
Save-Session
Write-Host "Preselected suite plan: $planPath"
Write-Host "Phase: $Phase; study rounds: $Rounds; Git HEAD: $gitHead"
foreach ($entry in $runs) {
    Write-Host ("Round {0}, position {1}: {2}, seed {3}" -f $entry.round, $entry.position, $entry.study, $entry.seed)
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
        Write-Host ("Running {0} (round {1}, position {2})" -f $entry.study, $entry.round, $entry.position)
        $transcriptStarted = $false
        try {
            Start-Transcript -Path $entry.transcript_path -ErrorAction Stop | Out-Null
            $transcriptStarted = $true
            & (Join-Path $PSScriptRoot $entry.script) -Seed ([uint32]$entry.seed)
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
} finally {
    $plan.ended_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-Session
}
Write-Host "Suite completed. Session record: $planPath"
Write-Host 'Inspect each physical Windows EXE and its controls before interpreting the pilot or scheduling follow-up rounds.'
$failed = @($runs | Where-Object { $_.status -ne 'validated_trace_pending_binary_audit' })
if ($failed.Count -gt 0) {
    throw ("{0} of {1} study runs did not pass build/run/strict analysis. All attempted runs remain in the session record." -f $failed.Count, $runs.Count)
}
