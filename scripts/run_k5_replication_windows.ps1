# One prospective K5 attempt per fresh Windows boot. Never reboot automatically.
param([ValidateSet('Next','Audit')][string]$Action = 'Next')
$ErrorActionPreference = 'Stop'

function Test-K5WindowsHost { return ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT -and [IntPtr]::Size -eq 8) }

function Get-K5CompilerMetadata {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { throw 'MSVC Build Tools with Desktop development with C++ is required.' }
    $installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'Cannot locate the MSVC x64 toolchain.' }
    $version = (Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
    $bin = Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
    $tools = [ordered]@{}
    foreach ($name in @('cl.exe','link.exe','dumpbin.exe')) {
        $path = Join-Path $bin $name
        $tools[$name] = [ordered]@{path=$path; file_version=(Get-Item -LiteralPath $path).VersionInfo.FileVersion;
            sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    return $tools
}

function Get-K5HostMetadata {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $processor = @(Get-CimInstance Win32_Processor -ErrorAction Stop)[0]
    $bios = Get-CimInstance Win32_BIOS -ErrorAction Stop
    $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    $identityMethod = 'smbios_uuid'
    $identity = ''
    try { $identity = ([string](Get-CimInstance Win32_ComputerSystemProduct -ErrorAction Stop).UUID).Trim().ToUpperInvariant() }
    catch { $identity = '' }
    if ($identity -notmatch '^[0-9A-F-]{36}$' -or $identity -match '^(0|-)+$' -or $identity -match '^(F|-)+$') {
        $identityMethod = 'windows_machine_guid'
        $identity = [string](Get-ItemPropertyValue -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid -ErrorAction Stop)
    }
    if ([string]::IsNullOrWhiteSpace($identity)) { throw 'Cannot record a stable host fingerprint.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    $microcode = [byte[]](Get-ItemPropertyValue -LiteralPath 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0' -Name 'Update Revision' -ErrorAction Stop)
    if ($microcode.Length -eq 0) { throw 'Microcode registry bytes are unavailable.' }
    $ubr = Get-ItemPropertyValue -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name UBR -ErrorAction Stop
    $guard = [ordered]@{query='unavailable'}
    try {
        $deviceGuard = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard -ErrorAction Stop
        $guard = [ordered]@{query='available'; vbs_status=[int]$deviceGuard.VirtualizationBasedSecurityStatus;
            configured=@($deviceGuard.SecurityServicesConfigured); running=@($deviceGuard.SecurityServicesRunning)}
    } catch { $guard['error'] = $_.Exception.Message }
    return [ordered]@{
        schema=1; captured_utc=(Get-Date).ToUniversalTime().ToString('o')
        boot_utc=([datetime]$os.LastBootUpTime).ToUniversalTime().ToString('o')
        machine_fingerprint_sha256=$fingerprint; fingerprint_method=$identityMethod
        environment=[ordered]@{
            cpu_name=([string]$processor.Name).Trim(); cpu_vendor=([string]$processor.Manufacturer).Trim()
            cores=[int]$processor.NumberOfCores; logical_processors=[int]$processor.NumberOfLogicalProcessors
            windows_build=[string]$os.BuildNumber; windows_version=[string]$os.Version; windows_ubr=[int]$ubr
            bios_version=([string]$bios.SMBIOSBIOSVersion).Trim()
            microcode_update_revision_hex=[BitConverter]::ToString($microcode).Replace('-','').ToLowerInvariant()
            hypervisor_present=[bool]$computer.HypervisorPresent
            vbs_query=[string]$guard.query
            vbs_status=$(if ($guard.query -eq 'available') { $guard.vbs_status } else { $null })
            vbs_services_running=@($(if ($guard.query -eq 'available') { $guard.running }))
            compiler_tools=Get-K5CompilerMetadata
            cl_environment=[string]$env:CL
            _cl_environment=[string]$env:_CL_
        }
        device_guard=$guard
        attestation='Local Windows inventory; not independent hardware or boot attestation.'
    }
}

function Save-K5Metadata([object]$Metadata, [string]$Path) {
    $Metadata | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Invoke-K5Python([string]$Python, [string[]]$Prefix, [string]$ScriptPath, [string[]]$ArgumentsForScript) {
    $text = (& $Python @Prefix $ScriptPath @ArgumentsForScript | Out-String)
    if ($LASTEXITCODE -ne 0) { throw "Replication validation command failed with exit $LASTEXITCODE. Keep the current evidence." }
    return ($text | ConvertFrom-Json -ErrorAction Stop)
}

function Invoke-K5Replication([string]$Repository, [ValidateSet('Next','Audit')][string]$Action = 'Next') {
    if (-not (Test-K5WindowsHost)) { throw 'This collector requires native Windows. No measurement started.' }
    $root = (Resolve-Path -LiteralPath $Repository).Path
    $out = Join-Path $root 'out'
    $folder = Join-Path $out 'k5-replication'
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $lockPath = Join-Path $out 'k5-replication.lock'
    try { $lock = [IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
    catch { throw 'Another K5 replication controller is running. No additional attempt was started.' }
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $metaPath = Join-Path $folder "host-$stamp.json"
    $archive = Join-Path $out "k5-replication-evidence-$stamp.zip"
    $failure = $null; $decision = $null; $python = $null; $pythonPrefix = @()
    $tool = Join-Path $root 'scripts\k5_replication.py'
    try {
        if (Get-Command py.exe -ErrorAction SilentlyContinue) { $python='py.exe'; $pythonPrefix=@('-3') }
        elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { $python='python.exe' }
        else { throw 'Python 3 is required. No measurement started.' }
        if ($Action -eq 'Next') {
            $meta = Get-K5HostMetadata
            Save-K5Metadata $meta $metaPath
            $decision = Invoke-K5Python $python $pythonPrefix $tool @('prepare','--repo',$root,'--folder',$folder,'--metadata',$metaPath)
            if ($decision.action -eq 'collect') {
                Write-Host "K5 replication attempt $($decision.ordinal)/3; preselected seed $($decision.seed)."
                $console = Join-Path $decision.attempt_directory 'collector-console.log'
                $collector = Join-Path $root 'scripts\check_dependency_receiver_windows.ps1'
                $oldPreference = $ErrorActionPreference; $collectorExit = 1
                try {
                    $ErrorActionPreference = 'Continue'
                    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $collector -Seed ([string]$decision.seed) 2>&1 |
                        ForEach-Object { [string]$_ } | Tee-Object -FilePath $console | ForEach-Object { Write-Host $_ }
                    $collectorExit = $LASTEXITCODE
                } catch { $failure = $_.Exception.Message }
                finally { $ErrorActionPreference = $oldPreference }
                $endMetaPath = Join-Path $folder "host-after-$stamp.json"
                Save-K5Metadata (Get-K5HostMetadata) $endMetaPath
                $null = Invoke-K5Python $python $pythonPrefix $tool @('finish','--repo',$root,'--folder',$folder,
                    '--metadata',$endMetaPath,'--ordinal',([string]$decision.ordinal),'--exit-code',([string]$collectorExit))
                if ($collectorExit -ne 0) { $failure = "Attempt $($decision.ordinal) ended with collector exit $collectorExit. Its slot and evidence are retained; do not retry that seed." }
            } elseif ($decision.action -eq 'restart_required') {
                Write-Host "Frozen prospective seeds: $($decision.seeds -join ', ')"
                Write-Host 'Restart Windows, then select Terminal > Run Task > K5 replication: collect next Windows session.'
                Write-Host 'This boot is not eligible for another collection. No measurement started.'
            } else { Write-Host 'All three attempt slots are recorded. Collection will not run again for this plan.' }
        }
    } catch {
        $failure = $_.Exception.Message
        [ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o'); action=$Action; error=$failure} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $folder "controller-error-$stamp.json") -Encoding UTF8
    } finally {
        try {
            if ($python) {
                Write-Host 'Validating every recorded evidence ZIP from its raw trace. This may take several minutes.'
                $result = Invoke-K5Python $python $pythonPrefix $tool @('package','--repo',$root,'--folder',$folder,'--archive',$archive)
                Write-Host "Replication outcome: $($result.outcome)"
                Write-Host "Recorded attempts: $($result.recorded_attempts)/3"
                if ($result.recorded_attempts -eq 3) { Write-Host "READY TO SHARE: $($result.archive)" }
                else { Write-Host "PLAN/PROGRESS ZIP ($($result.recorded_attempts)/3 attempts): $($result.archive)" }
                Write-Host "Evidence ZIP SHA256: $($result.sha256)"
                Write-Host 'This study does not establish user-to-kernel influence or reproduce the Fractal paper.'
                if ($Action -eq 'Next' -and $decision -and $decision.action -eq 'collect' -and $result.recorded_attempts -lt 3) {
                    Write-Host 'Next planned step: restart Windows, then run the same K5 replication task once.'
                }
            }
        } finally { $lock.Dispose() }
    }
    if ($failure) { throw $failure }
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-K5Replication -Repository (Join-Path $PSScriptRoot '..') -Action $Action
}
