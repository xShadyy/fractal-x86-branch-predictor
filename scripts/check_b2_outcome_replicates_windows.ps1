# Three independent B2 v4 runs in one session; preserve all attempts in one ZIP.
# Same-day replication does not measure variation between UTC dates.
param([uint32[]]$Seeds)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$runner = Join-Path $PSScriptRoot 'check_b2_outcome_windows.ps1'
$analyzer = Join-Path $PSScriptRoot 'summarize_b2_outcome_replicates.py'
$protocol = Join-Path $root 'B2_REPLICATION_V1.md'
$powershell = Join-Path $PSHOME 'powershell.exe'
foreach ($path in @($runner, $analyzer, $protocol, $powershell)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing replication dependency: $path" }
}

if ($PSBoundParameters.ContainsKey('Seeds')) {
    if ($Seeds.Count -ne 3 -or ($Seeds | Where-Object { $_ -eq 0 }).Count -ne 0 -or
        (@($Seeds | Select-Object -Unique)).Count -ne 3) {
        throw 'Specify exactly three distinct nonzero uint32 seeds.'
    }
    $chosen = @($Seeds)
} else {
    $chosen = @()
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $bytes = New-Object byte[] 4
        while ($chosen.Count -lt 3) {
            $random.GetBytes($bytes)
            $candidate = [BitConverter]::ToUInt32($bytes, 0)
            if ($candidate -ne 0 -and $candidate -notin $chosen) { $chosen += $candidate }
        }
    } finally { $random.Dispose() }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$name = "b2-replication-windows-$stamp"
$sessionFile = Join-Path $out "$name.session.json"
$summaryFile = Join-Path $out "$name.summary.json"
$manifestFile = Join-Path $out "$name.manifest.json"
$archive = Join-Path $out "$name.zip"
foreach ($path in @($sessionFile, $summaryFile, $manifestFile, $archive)) {
    if (Test-Path -LiteralPath $path) { throw "Session timestamp collision: $name" }
}

function File-Hash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Save-Session {
    $session | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $sessionFile -Encoding UTF8
}

# All choices and the source revision are recorded before the first host run.
$head = (& git.exe -C $root rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') {
    throw 'Could not record Git HEAD.'
}
$gitStatus = @(& git.exe -C $root status --porcelain --untracked-files=normal)
if ($LASTEXITCODE -ne 0 -or $gitStatus.Count -ne 0) {
    throw 'Commit or stash source changes before the replication session.'
}
$sourceFiles = @($runner, $analyzer, $protocol, $MyInvocation.MyCommand.Path,
                 (Join-Path $root 'B2_OUTCOME_V4.md'),
                 (Join-Path $root '.vscode\tasks.json'))
$sourceHashes = [ordered]@{}
foreach ($path in $sourceFiles) {
    $relative = $path.Substring($root.Length + 1).Replace('\', '/')
    $sourceHashes[$relative] = File-Hash $path
}
$session = [ordered]@{
    schema = 1
    study = 'b2_v4_same_site_replication'
    preselected_utc = $stamp
    preselected_seeds = @($chosen | ForEach-Object { [uint64]$_ })
    git_head = $head
    git_clean = $true
    source_sha256 = $sourceHashes
    attempts = @()
    status = 'preselected'
}
Save-Session
Write-Host "Preselected three B2 v4 seeds: $($chosen -join ', ')"
Write-Host "Frozen session ledger: $sessionFile"

$sessionFailure = $null
$attemptFiles = @()
try {
    for ($i = 1; $i -le 3; ++$i) {
        $seed = [uint32]$chosen[$i - 1]
        $transcript = Join-Path $out "$name.attempt-$i.transcript.log"
        $before = @{}
        Get-ChildItem -LiteralPath $out -Filter 'b2-outcome-windows-*.zip' -File |
            ForEach-Object { $before[$_.Name] = $true }
        Write-Host "B2 v4 attempt $i/3, seed $seed"
        $previousPreference = $ErrorActionPreference
        $lines = @()
        $exitCode = 1
        try {
            $ErrorActionPreference = 'Continue'
            $lines = @(& $powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Seed $seed 2>&1 |
                       ForEach-Object { [string]$_ })
            $exitCode = $LASTEXITCODE
        } catch {
            $lines = @($lines) + @("Runner launch failed: $($_.Exception.Message)")
            $exitCode = 1
        } finally { $ErrorActionPreference = $previousPreference }
        ($lines -join [Environment]::NewLine) | Set-Content -LiteralPath $transcript -Encoding UTF8
        $lines | ForEach-Object { Write-Host $_ }
        $attemptFiles += $transcript
        $newArchives = @(Get-ChildItem -LiteralPath $out -Filter 'b2-outcome-windows-*.zip' -File |
                         Where-Object { -not $before.ContainsKey($_.Name) })
        $runArchive = $null
        if ($newArchives.Count -eq 1) {
            $runArchive = $newArchives[0]
            $attemptFiles += $runArchive.FullName
        } elseif ($newArchives.Count -gt 1) {
            $attemptFiles += @($newArchives | ForEach-Object { $_.FullName })
            Write-Warning "Attempt $i produced multiple new B2 ZIPs; all retained for manual triage."
        }
        $entryArchiveName = $null
        $entryArchiveHash = $null
        if ($null -ne $runArchive) {
            $entryArchiveName = $runArchive.Name
            $entryArchiveHash = File-Hash $runArchive.FullName
        }
        $entry = [ordered]@{
            ordinal = $i
            seed = [uint64]$seed
            exit_code = [int]$exitCode
            transcript = (Split-Path $transcript -Leaf)
            transcript_sha256 = File-Hash $transcript
            archive = $entryArchiveName
            archive_sha256 = $entryArchiveHash
        }
        $session.attempts += $entry
        $session.status = 'attempts_in_progress'
        Save-Session
    }
    $session.status = 'all_attempts_recorded'
    Save-Session
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $python = 'py.exe'
        $pythonPrefix = @('-3')
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $python = 'python.exe'
        $pythonPrefix = @()
    } else { throw 'Python 3 is needed for replication summary.' }
    $output = (& $python @pythonPrefix $analyzer $sessionFile --json 2>&1 | Out-String)
    $analyzerExit = $LASTEXITCODE
    $output | Set-Content -LiteralPath $summaryFile -Encoding UTF8
    $attemptFiles += $summaryFile
    if ($analyzerExit -ne 0) { throw "Replication analyzer rejected session: $output" }
    $parsed = $output | ConvertFrom-Json -ErrorAction Stop
    if ($parsed.attempt_count -ne 3) { throw 'Replication summary did not retain three attempts.' }
    $session.status = 'analyzed'
    Save-Session
    Write-Host "Three attempts: $($parsed.analyzed_run_count) analyzed; $($parsed.control_passed_run_count) controls passed."
    foreach ($row in $parsed.runs) {
        if ($null -ne $row.outcome_F_ticks_per_episode) {
            $primary = $row.outcome_F_ticks_per_episode.p0_n1
            Write-Host "seed $($row.seed): F_p0_n1=$($primary.point) ticks/episode; controls=$($row.control_status)"
        } else {
            Write-Host "seed $($row.seed): $($row.diagnostic)"
        }
    }
    if ($parsed.analyzed_run_count -ne 3) {
        throw 'At least one attempt ended before complete B2 outcome analysis.'
    }
} catch {
    $sessionFailure = $_.Exception.Message
    $session.status = 'diagnostic'
    $session['failure'] = $sessionFailure
    Save-Session
    Write-Warning "B2 replication session issue: $sessionFailure"
} finally {
    $session['completed_utc'] = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    Save-Session
    $files = @($sessionFile) + @($attemptFiles | Where-Object { Test-Path -LiteralPath $_ })
    $hashes = [ordered]@{}
    foreach ($path in $files) { $hashes[(Split-Path $path -Leaf)] = File-Hash $path }
    $manifest = [ordered]@{
        schema = 1
        study = 'b2_v4_same_site_replication'
        git_head = $head
        files_sha256 = $hashes
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestFile -Encoding UTF8
    Compress-Archive -LiteralPath ($files + @($manifestFile)) -DestinationPath $archive -CompressionLevel Optimal -ErrorAction Stop
    if ($null -eq $sessionFailure) {
        Write-Host "READY TO SHARE: $archive"
    } else {
        Write-Host "Diagnostic evidence ZIP (partial): $archive"
    }
    Write-Host "Evidence ZIP SHA256: $(File-Hash $archive)"
}
if ($null -ne $sessionFailure) { throw "B2 replication incomplete: $sessionFailure. Evidence ZIP: $archive" }
if ($parsed.control_passed_run_count -ne 3) {
    throw "Some B2 v4 controls failed; preserve and share the complete ZIP: $archive"
}
