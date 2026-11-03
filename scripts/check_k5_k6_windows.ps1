# Run the ordinary Windows control and any available QEMU functional check once.
param([Parameter(Mandatory=$true)][string]$Assets, [switch]$SkipWindows)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$assetsRoot = (Resolve-Path -LiteralPath $Assets).Path
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$out = Join-Path $root 'out'
$session = Join-Path $out "k5-k6-session-$stamp"
New-Item -ItemType Directory -Path $session -ErrorAction Stop | Out-Null
$status = [ordered]@{schema=1; study='k5_k6_session'; windows_k5='not_run'; k6_smoke='not_run'; k6_physical='not_collected'; failures=@()}
$archive = "$session.zip"
try {
    $manifestPath = Join-Path $assetsRoot 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($entry in $manifest.files_sha256.PSObject.Properties) {
        $file = Join-Path $assetsRoot $entry.Name
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
            throw "Boot-kit SHA256 mismatch: $($entry.Name)"
        }
    }
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $session 'boot-manifest.json')
    if (-not $SkipWindows) {
        $before = @((Get-ChildItem -LiteralPath $out -Filter 'dependency-receiver-windows-*.zip').FullName)
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\check_dependency_receiver_windows.ps1')
            if ($LASTEXITCODE -ne 0) { throw "K5 runner exited with $LASTEXITCODE" }
            $status.windows_k5 = 'collected_see_its_analysis_for_validity'
        } catch { $status.windows_k5='software_error'; $status.failures += $_.Exception.Message }
        $new = @(Get-ChildItem -LiteralPath $out -Filter 'dependency-receiver-windows-*.zip' | Where-Object { $before -notcontains $_.FullName })
        foreach ($file in $new) { Copy-Item -LiteralPath $file.FullName -Destination $session }
        if ($new.Count -ne 1) { $status.failures += 'Expected exactly one new K5 archive; inspect out/.' }
    }
    $qemuCommand = Get-Command 'qemu-system-x86_64.exe' -ErrorAction SilentlyContinue
    $qemu = if ($qemuCommand) { $qemuCommand.Source } else { Join-Path $env:ProgramFiles 'qemu\qemu-system-x86_64.exe' }
    if (Test-Path -LiteralPath $qemu) {
        try {
            if (Get-Command py.exe -ErrorAction SilentlyContinue) { $python='py.exe'; $pythonPrefix=@('-3') }
            elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { $python='python.exe'; $pythonPrefix=@() }
            else { throw 'Python 3 is required.' }
            & $python @pythonPrefix (Join-Path $root 'scripts\run_fractal_privilege_smoke.py') $assetsRoot --qemu $qemu --output (Join-Path $session 'k6-smoke')
            if ($LASTEXITCODE -ne 0) { throw "K6 functional smoke failed with $LASTEXITCODE" }
            $status.k6_smoke='locally_verified_functional_only'
        } catch { $status.k6_smoke='failed'; $status.failures += $_.Exception.Message }
    } else {
        $status.k6_smoke='qemu_not_installed_reference_trace_in_package'
        Write-Host 'QEMU is unavailable here. The supplied verified smoke trace is reference evidence; no local K6 run is claimed.'
    }
    Copy-Item -LiteralPath (Join-Path $root 'protocols\FRACTAL_PRIVILEGE_K6.md') -Destination $session
    Write-Host "Physical boot files: $assetsRoot"
    Write-Host 'K6 PHYSICAL RESULT PENDING: boot the physical Fractal entry and capture its complete UART trace.'
} catch { $status.failures += $_.Exception.Message }
finally {
    $status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $session 'status.json') -Encoding UTF8
    $hashes = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $session -Recurse -File) {
        $relative = $file.FullName.Substring($session.Length+1).Replace('\','/')
        $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $hashes | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $session 'files-sha256.json') -Encoding UTF8
    Compress-Archive -Path (Join-Path $session '*') -DestinationPath $archive -ErrorAction Stop
    Write-Host "READY TO SHARE: $archive"
}
if ($status.failures.Count) { throw ($status.failures -join '; ') }
exit 0
