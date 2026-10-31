# Package one recorded suite session and its original artifacts for review.
param([string]$SessionDirectory = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
if (-not (Test-Path $out)) { throw 'No out directory exists yet. Run the suite pilot first.' }
if ($SessionDirectory) {
    $sessionDir = (Resolve-Path $SessionDirectory).Path
} else {
    $latest = Get-ChildItem -Path $out -Directory -Filter 'suite-*' |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $latest) { throw 'No suite session directory exists yet.' }
    $sessionDir = $latest.FullName
}
$sessionPath = Join-Path $sessionDir 'session.json'
if (-not (Test-Path $sessionPath)) { throw "Missing $sessionPath" }
$session = Get-Content -Path $sessionPath -Raw | ConvertFrom-Json
if ($session.schema -ne 1 -or -not $session.runs) { throw 'Unknown suite session schema.' }

$seen = @{}
$files = New-Object System.Collections.ArrayList
$outPrefix = [IO.Path]::GetFullPath($out).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
function Add-RecordedFile([string]$Candidate, [string]$ExpectedSha256 = '') {
    if (-not $Candidate) { return }
    $full = [IO.Path]::GetFullPath($Candidate)
    if (-not $full.StartsWith($outPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Suite record refers outside out/: $full"
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "Recorded artifact missing: $full"
    }
    if ($ExpectedSha256) {
        $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
            throw "Recorded artifact changed: $full"
        }
    }
    if (-not $seen.ContainsKey($full)) {
        $seen[$full] = $true
        [void]$files.Add($full)
    }
}

Add-RecordedFile $sessionPath
if ($session.host_snapshot) {
    Add-RecordedFile $session.host_snapshot.path $session.host_snapshot.sha256
}
foreach ($run in $session.runs) {
    if ($run.transcript_path) {
        Add-RecordedFile $run.transcript_path $run.transcript_sha256
    }
    foreach ($item in @($run.new_artifacts) + @($run.traces) + @($run.exes) + @($run.sidecars)) {
        if ($item -and $item.path) { Add-RecordedFile $item.path $item.sha256 }
    }
    if ($run.disassembly) {
        Add-RecordedFile $run.disassembly.path $run.disassembly.sha256
    }
}
$archive = Join-Path $out ('suite-evidence-{0}.zip' -f (Split-Path $sessionDir -Leaf))
if (Test-Path $archive) { throw "Archive already exists: $archive" }
Compress-Archive -LiteralPath $files.ToArray() -DestinationPath $archive -CompressionLevel Optimal
Write-Host "Suite evidence ZIP: $archive"
Write-Host "Included $($files.Count) checked files. Review the host snapshot for system details before sharing."
