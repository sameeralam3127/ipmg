<#
.SYNOPSIS
    IPMG installer for Windows.

.DESCRIPTION
    Installs uv (which brings its own Python, so no system Python is needed),
    then installs IPMG as an isolated tool, puts it on your PATH, and checks
    that it runs. Needs no administrator rights, and works in Windows
    PowerShell 5.1 and PowerShell 7.

        irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex

    To pass options, run it as a script block instead:

        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1))) -Version 2.3.0

.PARAMETER Version
    Install this IPMG release (for example 2.3.0) instead of the latest.
    The IPMG_VERSION environment variable does the same.

.PARAMETER Help
    Show this help.
#>
param(
    [string] $Version = $env:IPMG_VERSION,
    [switch] $Help
)

$ErrorActionPreference = 'Stop'
$Package = 'ipmg'
$MaxRetries = 3

# -------------------------------------------------------------- output
# Everything below runs inside the caller's session (that is what `iex`
# does), so failures throw rather than exit: `exit` would close their window.
function Write-Step([string] $Message) {
    Write-Host ''
    Write-Host '[IPMG] ' -ForegroundColor Blue -NoNewline
    Write-Host $Message
}

function Write-Warn([string] $Message) {
    Write-Host ''
    Write-Host '[WARN] ' -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Test-Command([string] $Name) {
    return [bool] (Get-Command $Name -ErrorAction SilentlyContinue)
}

# Retries a script block with backoff: the installer usually runs once,
# unattended, over a network that may blip.
function Invoke-WithRetry([scriptblock] $Action) {
    for ($attempt = 1; ; $attempt++) {
        & $Action
        if ($LASTEXITCODE -eq 0) { return $true }
        if ($attempt -ge $MaxRetries) { return $false }
        Write-Warn "Command failed (attempt $attempt/$MaxRetries). Retrying in $($attempt * 2)s..."
        Start-Sleep -Seconds ($attempt * 2)
    }
}

function Add-ToSessionPath([string] $Directory) {
    $entries = $env:Path -split ';'
    if ($entries -notcontains $Directory) {
        $env:Path = "$Directory;$env:Path"
    }
}

if ($Help) {
    Get-Help $PSCommandPath -Detailed -ErrorAction SilentlyContinue
    if (-not $PSCommandPath) {
        Write-Host 'Usage: irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex'
        Write-Host '       & ([scriptblock]::Create((irm <that URL>))) -Version 2.3.0'
    }
    return
}

# -------------------------------------------------------------- platform
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) {
    throw "This installer is for Windows. On Linux and macOS run:`n  curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash"
}

# Windows PowerShell 5.1 may still default to TLS 1.0, which astral.sh and
# PyPI refuse.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

Write-Step "Detected PowerShell $($PSVersionTable.PSVersion) on $([Environment]::OSVersion.VersionString)"

# -------------------------------------------------------------- uv
# uv's own installer puts uv.exe here and adds it to the user PATH, but only
# new sessions see that, so this one is told directly.
$uvHome = Join-Path $HOME '.local\bin'
Add-ToSessionPath $uvHome

if (Test-Command 'uv') {
    Write-Step 'uv is already installed.'
} else {
    Write-Step 'Installing uv (it brings its own Python, so no system Python is needed)...'
    # A child process, so anything uv's installer does to its session (an
    # exit, a changed preference) cannot end this one.
    $shell = (Get-Process -Id $PID).Path
    $installed = Invoke-WithRetry {
        & $shell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    }
    if (-not $installed -or -not (Test-Command 'uv')) {
        throw "Could not install uv. Check that this machine can reach https://astral.sh, or install uv by hand:`n  https://docs.astral.sh/uv/getting-started/installation/"
    }
    Write-Step 'uv installed.'
}

# -------------------------------------------------------------- ipmg
# The web extra too: someone running the one-liner expects `ipmg web` to work.
$target = '{0}[web]' -f $Package
if ($Version) {
    $target = '{0}[web]=={1}' -f $Package, $Version
}

Write-Step "Installing $target from PyPI..."
$ok = Invoke-WithRetry { uv tool install --upgrade $target }
if (-not $ok) {
    Write-Warn "Upgrade failed; retrying with a clean reinstall (this recovers from an earlier install of '$Package' from a different source)."
    $ok = Invoke-WithRetry { uv tool install --force $target }
    if (-not $ok) {
        throw "Could not install '$target'. Try it by hand to see the full error:`n  uv tool install --force $target"
    }
}

# -------------------------------------------------------------- PATH
# "Installed fine, command not found" is the most common install report, so
# the tool directory goes on the user PATH (no administrator rights needed)
# and on this session's PATH.
$binDir = (uv tool dir --bin | Out-String).Trim()
if (-not $binDir) {
    $binDir = $uvHome
}
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) {
    $userPath = ''
}
$onUserPath = ($userPath -split ';') -contains $binDir
if (-not $onUserPath) {
    $newPath = ($binDir, $userPath | Where-Object { $_ }) -join ';'
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Step "Added $binDir to your user PATH."
}
Add-ToSessionPath $binDir

# -------------------------------------------------------------- verify
$exe = Join-Path $binDir "$Package.exe"
if (-not (Test-Path $exe)) {
    throw "Installation finished but $exe was not found. Try: uv tool install --force $Package"
}

$installedVersion = (& $exe --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $installedVersion) {
    throw "$Package was installed but '$Package --version' failed. Try: uv tool install --force $Package"
}
if ($Version -and $installedVersion -notmatch [regex]::Escape($Version)) {
    throw "Asked for $Package $Version but '$Package --version' reports: $installedVersion"
}

Write-Step "Installed: $installedVersion"
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  ipmg --help          # every option'
Write-Host '  ipmg --discover      # scan the network this machine is on'
Write-Host ''
if (-not $onUserPath) {
    Write-Host 'Other open terminals need restarting to see ipmg; this one already can.'
    Write-Host ''
}
