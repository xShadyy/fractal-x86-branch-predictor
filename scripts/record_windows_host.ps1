# Record reproducibility metadata for a Windows measurement session.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out = Join-Path $root 'out'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$path = Join-Path $out ('host-windows-{0}.json' -f $stamp)
if (Test-Path $path) { throw "Host snapshot timestamp collision: $stamp" }

$os = Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption, Version, BuildNumber, OSArchitecture
$cpu = Get-CimInstance Win32_Processor |
    Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
$board = Get-CimInstance Win32_BaseBoard |
    Select-Object Manufacturer, Product, Version
$bios = Get-CimInstance Win32_BIOS |
    Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
$computer = Get-CimInstance Win32_ComputerSystem |
    Select-Object HypervisorPresent
$powerPlan = (& powercfg.exe /getactivescheme | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not read the active power plan.' }

$record = [ordered]@{
    captured_utc = $stamp
    os = $os
    processor = $cpu
    baseboard = $board
    bios = $bios
    hypervisor = $computer
    active_power_plan = $powerPlan
    note = 'Windows host inventory; microcode and mitigation configuration are not established by this record.'
}
$record | ConvertTo-Json -Depth 5 | Out-File -FilePath $path -Encoding utf8
Write-Host "Windows host snapshot: $path"
Write-Host 'Review before sharing: this file describes your system configuration.'
