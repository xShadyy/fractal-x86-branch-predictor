# Validate a physical UART capture. Emulation traces are rejected by this entry point.
param([Parameter(Mandatory=$true)][string]$Trace,
      [Parameter(Mandatory=$true)][string]$Assets,
      [Parameter(Mandatory=$true)][string]$MachineDescription)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$inputTrace = (Resolve-Path -LiteralPath $Trace).Path
$assetsRoot = (Resolve-Path -LiteralPath $Assets).Path
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$out = Join-Path $root "out\fractal-k6-physical-$stamp"
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null
$failure = $null
try {
    Copy-Item -LiteralPath $inputTrace -Destination (Join-Path $out 'serial.log')
    Copy-Item -LiteralPath (Join-Path $assetsRoot 'manifest.json') -Destination (Join-Path $out 'boot-manifest.json')
    $manifest = Get-Content -LiteralPath (Join-Path $assetsRoot 'manifest.json') -Raw | ConvertFrom-Json
    foreach ($entry in $manifest.files_sha256.PSObject.Properties) {
        if ((Get-FileHash -LiteralPath (Join-Path $assetsRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value) {
            throw "Boot-kit SHA256 mismatch: $($entry.Name)"
        }
    }
    foreach ($entry in $manifest.source_sha256.PSObject.Properties) {
        $text = Get-Content -LiteralPath (Join-Path $root $entry.Name) -Raw -Encoding UTF8
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text.Replace("`r`n","`n"))))).Replace('-','').ToLowerInvariant() }
        finally { $sha.Dispose() }
        if ($actual -cne $entry.Value) {
            throw "Frozen K6 source mismatch: $($entry.Name)"
        }
        $destination = Join-Path (Join-Path $out 'sources') $entry.Name
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $root $entry.Name) -Destination $destination
    }
    $bootEvidence = Join-Path $out 'boot-evidence'
    New-Item -ItemType Directory -Path $bootEvidence | Out-Null
    foreach ($name in @('fractal-k6.multiboot','k6-physical.elf','k6-physical.ext2','fractal-upstream-source.tar.gz',
                        'fractal-host-init-array.patch','fractal-multiboot2-k6.patch','FRACTAL-LICENSE.txt')) {
        Copy-Item -LiteralPath (Join-Path $assetsRoot $name) -Destination $bootEvidence
    }
    [ordered]@{measured_machine_notes=$MachineDescription; capture_utc=$stamp; attestation='User notes and trace metadata; not independent hardware attestation.'} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'machine-notes.json') -Encoding UTF8
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { $python='py.exe'; $pythonPrefix=@('-3') }
    elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { $python='python.exe'; $pythonPrefix=@() }
    else { throw 'Python 3 is required.' }
    $analyzer = Join-Path $root 'scripts\analyze_fractal_privilege.py'
    $analysis = (& $python @pythonPrefix $analyzer (Join-Path $out 'serial.log') --json 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $analysis | Set-Content -LiteralPath (Join-Path $out 'analysis.json') -Encoding UTF8
    if ($code -ne 0) { throw 'Physical evidence validation failed. Retain this archive, including the raw trace.' }
    $parsed = $analysis | ConvertFrom-Json
    Write-Host "K6 physical collection validated: $($parsed.samples) samples"
    Write-Host "Eligible with same-domain positives: $($parsed.hardware_eligible)"
    Write-Host "User-to-kernel numerical signature: $($parsed.user_to_kernel_numerical_signature_detected)"
    Write-Host 'One physical pilot does not establish a replicated mechanism. Retain nulls and failed gates.'
} catch { $failure = $_.Exception.Message }
finally {
    [ordered]@{failure=$failure; completed_validation=($null -eq $failure)} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $out 'status.json') -Encoding UTF8
    $hashes=[ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $out -File -Recurse) {
        $relative = $file.FullName.Substring($out.Length+1).Replace('\','/')
        $hashes[$relative]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $hashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'files-sha256.json') -Encoding UTF8
    Compress-Archive -Path (Join-Path $out '*') -DestinationPath "$out.zip" -ErrorAction Stop
    Write-Host "READY TO SHARE (including nulls or failures): $out.zip"
}
if ($null -ne $failure) { throw $failure }
exit 0
