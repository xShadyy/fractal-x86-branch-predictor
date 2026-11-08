# Build once, freeze the prospective K7/K8 study, and retain all six attempts.
# This runner uses ordinary user mode and makes no driver or system-setting changes.
param([string]$Folder)
$ErrorActionPreference = 'Stop'

function Get-CausalPython {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { return [pscustomobject]@{command='py.exe'; prefix=@('-3')} }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) { return [pscustomobject]@{command='python.exe'; prefix=@()} }
    throw 'Python 3 is required. No measurement started.'
}

function Get-CausalFileHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Write-CausalBuildRecord([object]$Record,[string]$Path) {
    $Record | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Invoke-CausalLogged([string]$Command,[object[]]$CommandArguments,[string]$LogPath) {
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Command @CommandArguments 2>&1 | ForEach-Object { [string]$_ } |
            Tee-Object -FilePath $LogPath -Append | ForEach-Object { Write-Host $_ }
        $commandExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $oldPreference }
    if ($commandExit -ne 0) { throw "$Command failed with exit $commandExit." }
}

function Build-CausalReceiver([string]$Repository,[string]$StudyFolder) {
    $head = (& git.exe -C $Repository rev-parse HEAD | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-f]{40}$') { throw 'Cannot record the Git source revision.' }
    $status = @(& git.exe -C $Repository status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the Git working tree.' }
    if ($status.Count -ne 0) { throw 'Commit or stash source edits before starting this study.' }
    if ($env:CL -or $env:_CL_) { throw 'CL/_CL_ compiler overrides are set. No study build started.' }

    $policy = Get-Content -LiteralPath (Join-Path $Repository 'protocols\WINDOWS_CAUSAL_POLICY.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $sourceNames = @($policy.source_files)
    if ($sourceNames.Count -eq 0) { throw 'The study policy has no frozen source inventory.' }
    $build = Join-Path $StudyFolder 'build'
    if ((Test-Path -LiteralPath $build) -and @(Get-ChildItem -LiteralPath $build -Force).Count -ne 0) {
        throw 'A previous unplanned build is retained in this folder. It will not be overwritten; keep its evidence for review.'
    }
    New-Item -ItemType Directory -Path $build -Force | Out-Null
    $binary = Join-Path $build 'collector.exe'
    $buildJson = Join-Path $build 'build.json'
    $buildLog = Join-Path $build 'build.log'
    $inputs = @((Join-Path $Repository 'programs\causal_receiver.c'),(Join-Path $Repository 'programs\cpu_features.c'))
    $commandArguments = @('/nologo','/std:c11','/O2','/W4','/WX',"/Fe$binary") + $inputs
    $record = [ordered]@{
        schema=1; study='windows_causal_followup'; git_head=$head; git_clean=$true
        build_start_utc=(Get-Date).ToUniversalTime().ToString('o'); build_end_utc=$null
        compilation_command=@('cl.exe') + $commandArguments
        binary_sha256=$null; tools=[ordered]@{}; source_sha256=[ordered]@{}; source_sha256_lf=[ordered]@{}
        build_runtime_status='preparing'; collection_stage='source_inventory'; error=$null
    }
    Write-CausalBuildRecord $record $buildJson
    try {
        foreach ($name in $sourceNames) {
            $relative = ([string]$name).Replace('\','/')
            if ([IO.Path]::IsPathRooted($relative) -or ($relative -split '/') -contains '..' -or $relative.Contains(':')) {
                throw 'Invalid path in the frozen source inventory.'
            }
            if ($record.source_sha256.Contains($relative)) { throw 'Duplicate path in the frozen source inventory.' }
            $path = Join-Path $Repository $relative
            $record.source_sha256[$relative] = Get-CausalFileHash $path
            $bytes = [IO.File]::ReadAllBytes($path)
            $sourceText = [Text.Encoding]::UTF8.GetString($bytes).Replace("`r`n","`n")
            $hash = [Security.Cryptography.SHA256]::Create()
            try { $record.source_sha256_lf[$relative] = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($sourceText))).Replace('-','').ToLowerInvariant() }
            finally { $hash.Dispose() }
        }

        $record.collection_stage = 'toolchain_setup'
        Write-CausalBuildRecord $record $buildJson
        $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
        if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Install MSVC Build Tools with Desktop development with C++ and a Windows SDK.' }
        $installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'Cannot locate the MSVC x64 toolchain.' }
        $developerCommand = Join-Path $installation 'Common7\Tools\VsDevCmd.bat'
        $setup = 'call "' + $developerCommand + '" -arch=x64 >nul && set'
        $environmentLines = @(& cmd.exe /d /c $setup)
        if ($LASTEXITCODE -ne 0) { throw 'MSVC environment setup failed.' }
        foreach ($line in $environmentLines) {
            if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process') }
        }
        if ($env:CL -or $env:_CL_) { throw 'MSVC setup introduced CL/_CL_ compiler overrides.' }
        foreach ($tool in @('cl.exe','link.exe','dumpbin.exe')) {
            $path = (Get-Command $tool -ErrorAction Stop).Source
            $record.tools[$tool] = [ordered]@{path=$path; file_version=(Get-Item -LiteralPath $path).VersionInfo.FileVersion; sha256=(Get-CausalFileHash $path)}
        }
        $record.collection_stage = 'compilation'
        Write-CausalBuildRecord $record $buildJson
        Push-Location -LiteralPath $build
        try { Invoke-CausalLogged 'cl.exe' $commandArguments $buildLog }
        finally { Pop-Location }
        $record.binary_sha256 = Get-CausalFileHash $binary
        $record.collection_stage = 'disassembly'
        Write-CausalBuildRecord $record $buildJson
        $oldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & dumpbin.exe /disasm $binary | Set-Content -LiteralPath (Join-Path $build 'collector.disasm.txt') -Encoding ASCII
            $disassemblyExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $oldPreference }
        if ($disassemblyExit -ne 0) { throw 'MSVC disassembly failed.' }

        $record.collection_stage = 'host_inventory'
        Write-CausalBuildRecord $record $buildJson
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repository 'scripts\capture_causal_host_windows.ps1') -OutputFile (Join-Path $build 'initial-host.json')
        if ($LASTEXITCODE -ne 0) { throw 'Initial Windows host inventory failed.' }
        $headAfter = (& git.exe -C $Repository rev-parse HEAD | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $headAfter -cne $head) { throw 'Git revision changed during the study build.' }
        $statusAfter = @(& git.exe -C $Repository status --porcelain --untracked-files=normal)
        if ($LASTEXITCODE -ne 0 -or $statusAfter.Count -ne 0) { throw 'Source changed during the study build.' }
        foreach ($name in $record.source_sha256.Keys) {
            if ((Get-CausalFileHash (Join-Path $Repository $name)) -cne $record.source_sha256[$name]) { throw "Source bytes changed during the study build: $name" }
        }
        $record.build_runtime_status = 'built'
        $record.collection_stage = 'ready_for_plan'
    } catch {
        $record.build_runtime_status = 'failed'
        $record.error = $_.Exception.Message
        throw
    } finally {
        $record.build_end_utc = (Get-Date).ToUniversalTime().ToString('o')
        Write-CausalBuildRecord $record $buildJson
    }
}

function Invoke-CausalWindowsStudy([string]$StudyFolder) {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or [IntPtr]::Size -ne 8) { throw 'This runner requires native 64-bit Windows.' }
    $root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    if ([string]::IsNullOrWhiteSpace($StudyFolder)) { $StudyFolder = Join-Path $root 'out\causal-windows-study' }
    elseif (-not [IO.Path]::IsPathRooted($StudyFolder)) { $StudyFolder = Join-Path $root $StudyFolder }
    $folderPath = [IO.Path]::GetFullPath($StudyFolder)
    New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
    try { $lock = [IO.File]::Open(($folderPath+'.runner.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
    catch { throw 'Another Windows causal runner is using this study folder.' }
    $python = $null
    $failure = $null
    $controller = Join-Path $root 'scripts\causal_receiver_study.py'
    try {
        $python = Get-CausalPython
        if (-not (Test-Path -LiteralPath (Join-Path $folderPath 'plan.json'))) {
            Build-CausalReceiver -Repository $root -StudyFolder $folderPath
        } else { Write-Host 'Using the existing frozen plan and build. No rebuild or replacement attempt will be made.' }
        $command = $python.command; $prefix = @($python.prefix)
        $oldPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $command @prefix $controller collect --repo $root --folder $folderPath
            $collectExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $oldPreference }
        if ($collectExit -ne 0) { throw "Causal study controller exited with $collectExit. Existing evidence is retained." }
    } catch {
        $failure = $_.Exception.Message
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
        try {
            Write-CausalBuildRecord ([ordered]@{schema=1; captured_utc=(Get-Date).ToUniversalTime().ToString('o'); stage='windows_runner'; error=$failure}) (Join-Path $folderPath ("runner-error-"+$stamp+'.json'))
        } catch { Write-Host 'The runner error could not be saved; retain this console output.' }
    }
    finally {
        try {
            if (-not $python) { $python = Get-CausalPython }
            $command = $python.command; $prefix = @($python.prefix)
            Write-Host 'Validating and packaging all available study records.'
            $oldPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                $json = (& $command @prefix $controller package --repo $root --folder $folderPath | Out-String)
                $packageExit = $LASTEXITCODE
            } finally { $ErrorActionPreference = $oldPreference }
            if ($packageExit -ne 0) { throw "Causal study packaging exited with $packageExit." }
            $result = $json | ConvertFrom-Json -ErrorAction Stop
            if (-not $result.archive -or -not $result.sha256) { throw 'Packaging did not report an evidence archive and hash.' }
            Write-Host "Study outcome: $($result.outcome)"
            Write-Host "Recorded attempts: $($result.recorded_attempts)/$($result.planned_attempts)"
            Write-Host "READY TO SHARE: $($result.archive)"
            Write-Host "Evidence ZIP SHA256: $($result.sha256)"
            Write-Host 'These are Windows user-mode experiments. Mechanism attribution and user-to-kernel influence require separate evidence.'
        } catch {
            Write-Host "Evidence packaging error: $($_.Exception.Message)"
            Write-Host "Keep the study folder and console output: $folderPath"
            if (-not $failure) { $failure = $_.Exception.Message }
        } finally { $lock.Dispose() }
    }
    if ($failure) { throw $failure }
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-CausalWindowsStudy -StudyFolder $Folder
}
