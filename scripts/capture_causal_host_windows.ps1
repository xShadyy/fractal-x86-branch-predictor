# Read-only Windows inventory for the K7/K8 user-mode study. This performs no measurement.
param([string]$OutputFile)
$ErrorActionPreference = 'Stop'

function Get-CausalHostMetadata {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
    $bios = @(Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop)[0]
    $board = @(Get-CimInstance -ClassName Win32_BaseBoard -ErrorAction Stop)[0]
    $system = @(Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop)[0]
    $processors = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | ForEach-Object {
        [ordered]@{
            Name = ([string]$_.Name).Trim()
            Manufacturer = ([string]$_.Manufacturer).Trim()
            NumberOfCores = [int]$_.NumberOfCores
            NumberOfLogicalProcessors = [int]$_.NumberOfLogicalProcessors
            Revision = $_.Revision
        }
    })
    if ($processors.Count -eq 0) { throw 'Windows returned no CPU inventory.' }

    $ubr = $null
    $ubrStatus = 'unavailable'
    try {
        $ubr = [int](Get-ItemPropertyValue -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name UBR -ErrorAction Stop)
        $ubrStatus = 'available'
    } catch { }

    $microcode = $null
    $microcodeStatus = 'unavailable'
    try {
        $bytes = [byte[]](Get-ItemPropertyValue -LiteralPath 'HKLM:\HARDWARE\DESCRIPTION\System\CentralProcessor\0' -Name 'Update Revision' -ErrorAction Stop)
        if ($bytes.Length -gt 0) {
            $microcode = [BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()
            $microcodeStatus = 'available'
        }
    } catch { }

    $vbs = [ordered]@{query_status='unavailable'; status=$null; services_configured=$null; services_running=$null}
    try {
        $guard = Get-CimInstance -Namespace 'root\Microsoft\Windows\DeviceGuard' -ClassName Win32_DeviceGuard -ErrorAction Stop
        $vbs = [ordered]@{
            query_status='available'
            status=[int]$guard.VirtualizationBasedSecurityStatus
            services_configured=@($guard.SecurityServicesConfigured)
            services_running=@($guard.SecurityServicesRunning)
        }
    } catch { }

    $power = [ordered]@{query_status='unavailable'; raw=$null; exit_code=$null}
    if (Get-Command powercfg.exe -ErrorAction SilentlyContinue) {
        $oldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $lines = @(& powercfg.exe /getactivescheme 2>&1 | ForEach-Object { [string]$_ })
            $powerExit = $LASTEXITCODE
            $power = [ordered]@{
                query_status=$(if ($powerExit -eq 0) { 'available' } else { 'unavailable' })
                raw=$(if ($powerExit -eq 0) { ($lines -join "`n").Trim() } else { $null })
                exit_code=$powerExit
            }
        } catch { }
        finally { $ErrorActionPreference = $oldPreference }
    }

    $releaseDate = $null
    if ($null -ne $bios.ReleaseDate) {
        if ($bios.ReleaseDate -is [datetime]) { $releaseDate = $bios.ReleaseDate.ToUniversalTime().ToString('o') }
        else { $releaseDate = [string]$bios.ReleaseDate }
    }
    $hypervisor = $null
    if ($null -ne $system.HypervisorPresent) { $hypervisor = [bool]$system.HypervisorPresent }

    return [ordered]@{
        schema=1
        captured_utc=(Get-Date).ToUniversalTime().ToString('o')
        boot_utc=([datetime]$os.LastBootUpTime).ToUniversalTime().ToString('o')
        cpu=$processors
        os=[ordered]@{Caption=[string]$os.Caption; Version=[string]$os.Version; BuildNumber=[string]$os.BuildNumber; UBR=$ubr; ubr_query_status=$ubrStatus}
        bios=[ordered]@{SMBIOSBIOSVersion=([string]$bios.SMBIOSBIOSVersion).Trim(); ReleaseDate=$releaseDate}
        baseboard=[ordered]@{Product=([string]$board.Product).Trim(); Manufacturer=([string]$board.Manufacturer).Trim()}
        hypervisor_present=$hypervisor
        vbs=$vbs
        microcode_update_revision_hex=$microcode
        microcode_query_status=$microcodeStatus
        power_plan=$power
        inventory_scope='Read-only local Windows inventory; not independent hardware attestation.'
    }
}

function Save-CausalHostMetadata([string]$Path) {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Host capture requires native Windows.' }
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Specify -OutputFile for the host inventory JSON.' }
    $target = [IO.Path]::GetFullPath($Path)
    $metadata = Get-CausalHostMetadata
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    $stream = [IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $writer = $null
    try {
        $writer = [IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
        $writer.WriteLine(($metadata | ConvertTo-Json -Depth 15))
    } finally {
        if ($writer) { $writer.Dispose() } else { $stream.Dispose() }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    Save-CausalHostMetadata -Path $OutputFile
}
