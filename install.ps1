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

        & ([scriptblock]::Create((irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1))) -Version X.Y.Z

    Every download is checked before it is installed: IPMG's wheel and its
    hash-pinned dependency list against the SHA256SUMS of a GitHub release,
    and uv against a hash written in this script. A mismatch or a missing
    checksum stops the install. To read and check this script first, see
    "Verify before you run" in docs/INSTALL.md.

.PARAMETER Version
    Install this IPMG release (X.Y.Z, 4.2.1 or newer) instead of the latest.
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
$Repo = 'sameeralam3127/ipmg'
$MaxRetries = 3

# The uv this installer fetches when uv is missing, and the SHA256 of its
# Windows archives. To move to a newer uv, change all of them together, from
# https://github.com/astral-sh/uv/releases/download/<version>/sha256.sum
# CI fails when they no longer match what astral publishes.
$UvVersion = '0.13.7'
$UvArchiveSha256 = @{
    'x86_64-pc-windows-msvc'  = '0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021'
    'aarch64-pc-windows-msvc' = '505d9e65e7692bac3ddf98c66754aa26c5050c409c184af30a881a0a72cc85e3'
    'i686-pc-windows-msvc'    = 'fa2abbf16f7d12cb01c9b7f313d843218fbd91a9d3fab487cc06a1d6765b27bf'
}

# TEST ONLY: a directory or URL holding SHA256SUMS and the release files, in
# place of the GitHub release. CI points it at a deliberately corrupted copy.
$ReleaseBaseOverride = $env:IPMG_RELEASE_BASE_URL

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

# -------------------------------------------------------------- verified downloads
# Download-File Source Destination. Source is an https URL, or (for the test
# override) a local path.
function Download-File([string] $Source, [string] $Destination) {
    if ($Source -notmatch '^https?://') {
        Copy-Item -LiteralPath $Source -Destination $Destination -ErrorAction Stop
        return
    }
    # The progress bar makes Windows PowerShell 5.1 download many times slower.
    $previous = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try {
        for ($attempt = 1; ; $attempt++) {
            try {
                Invoke-WebRequest -UseBasicParsing -Uri $Source -OutFile $Destination
                return
            } catch {
                if ($attempt -ge $MaxRetries) { throw }
                Write-Warn "Download failed (attempt $attempt/$MaxRetries). Retrying in $($attempt * 2)s..."
                Start-Sleep -Seconds ($attempt * 2)
            }
        }
    } finally {
        $ProgressPreference = $previous
    }
}

function Get-Sha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

# Stops the install unless the file at Path hashes to Expected.
function Assert-Sha256([string] $Path, [string] $Label, [string] $Expected) {
    $actual = Get-Sha256 $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "Checksum mismatch for $Label; nothing was installed.`n  expected: $Expected`n  actual:   $actual`nThe download is corrupt or has been tampered with. Try again, and if it keeps`nfailing, report it at https://github.com/$Repo/issues"
    }
}

# Reads a SHA256SUMS file into @{ name = hash }.
function Read-Checksums([string] $Path) {
    $sums = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') {
            $sums[$Matches[2]] = $Matches[1].ToLowerInvariant()
        }
    }
    return $sums
}

# Downloads a release file and verifies it against SHA256SUMS. A file the
# checksums do not list is refused, not skipped.
function Get-CheckedFile([string] $Name) {
    if (-not $Sums.ContainsKey($Name)) {
        throw "SHA256SUMS in $ReleaseBase has no entry for $Name; nothing was installed.`nRefusing to install a file that has no published checksum."
    }
    $path = Join-Path $Work $Name
    try {
        Download-File "$ReleaseBase/$Name" $path
    } catch {
        throw "Could not download $ReleaseBase/${Name}: $($_.Exception.Message)"
    }
    Assert-Sha256 $path $Name $Sums[$Name]
    return $path
}

if ($Help) {
    Get-Help $PSCommandPath -Detailed -ErrorAction SilentlyContinue
    if (-not $PSCommandPath) {
        Write-Host 'Usage: irm https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.ps1 | iex'
        Write-Host '       & ([scriptblock]::Create((irm <that URL>))) -Version X.Y.Z'
    }
    return
}

# -------------------------------------------------------------- platform
if ($PSVersionTable.PSEdition -eq 'Core' -and -not $IsWindows) {
    throw "This installer is for Windows. On Linux and macOS run:`n  curl -sSL https://raw.githubusercontent.com/sameeralam3127/ipmg/main/install.sh | bash"
}

if ($Version) {
    $Version = $Version.TrimStart('v')
}

# Windows PowerShell 5.1 may still default to TLS 1.0, which astral.sh and
# PyPI refuse.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

Write-Step "Detected PowerShell $($PSVersionTable.PSVersion) on $([Environment]::OSVersion.VersionString)"

# uv's own installer puts uv.exe here and adds it to the user PATH, but only
# new sessions see that, so this one is told directly.
$uvHome = Join-Path $HOME '.local\bin'
Add-ToSessionPath $uvHome

$Work = Join-Path ([IO.Path]::GetTempPath()) ("ipmg-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null

try {

# -------------------------------------------------------------- release files
# Fetched and checked before anything is installed, uv included, so a bad
# download leaves nothing behind. SHA256SUMS comes from the release (over
# TLS), and every other file must match the hash it lists.
if ($ReleaseBaseOverride) {
    $ReleaseBase = $ReleaseBaseOverride.TrimEnd('/', '\')
} elseif ($Version) {
    $ReleaseBase = "https://github.com/$Repo/releases/download/v$Version"
} else {
    $ReleaseBase = "https://github.com/$Repo/releases/latest/download"
}

$shown = if ($Version) { $Version } else { '(latest release)' }
Write-Step "Fetching the checksums for IPMG $shown..."
$sumsPath = Join-Path $Work 'SHA256SUMS'
try {
    Download-File "$ReleaseBase/SHA256SUMS" $sumsPath
} catch {
    throw "Could not download $ReleaseBase/SHA256SUMS`nReleases before 4.2.1 have no checksums, so this installer will not install them.`nFor those, install by hand: uv tool install '$Package[web]==$(if ($Version) { $Version } else { 'X.Y.Z' })'"
}
$Sums = Read-Checksums $sumsPath

# The wheel is the one file named ipmg-<version>-py3-none-any.whl.
$wheels = @($Sums.Keys | Where-Object { $_ -like "$Package-*-py3-none-any.whl" })
if ($wheels.Count -ne 1) {
    throw "Expected one $Package wheel in SHA256SUMS, found $($wheels.Count); nothing was installed."
}
$wheelName = $wheels[0]

if ($Version -and $wheelName -ne "$Package-$Version-py3-none-any.whl") {
    throw "SHA256SUMS lists $wheelName, not IPMG $Version; nothing was installed.`n-Version takes a release number such as 4.2.1."
}

if (-not $Version) {
    # "Latest" was only used to find the version. Everything else comes from
    # that release's own tag, so a release cut in between cannot mix files.
    $Version = ($wheelName.Substring($Package.Length + 1) -split '-')[0]
    if (-not $ReleaseBaseOverride) {
        $ReleaseBase = "https://github.com/$Repo/releases/download/v$Version"
    }
}

$requirementsName = 'requirements-web.txt'
$wheelPath = Get-CheckedFile $wheelName
$requirementsPath = Get-CheckedFile $requirementsName
Write-Step "Verified $wheelName and $requirementsName against SHA256SUMS."

# -------------------------------------------------------------- uv
# Windows PowerShell 5.1 and PowerShell 7 expose the architecture the same way.
$uvTarget = switch ($env:PROCESSOR_ARCHITECTURE) {
    'ARM64' { 'aarch64-pc-windows-msvc' }
    'x86'   { 'i686-pc-windows-msvc' }
    default { 'x86_64-pc-windows-msvc' }
}

# uv's installer script does not check the archive it downloads, so this
# fetches the archive itself and checks it against the hash above.
if (Test-Command 'uv') {
    Write-Step 'uv is already installed.'
} else {
    Write-Step "Installing uv $UvVersion (it brings its own Python, so no system Python is needed)..."
    $uvZip = Join-Path $Work "uv-$uvTarget.zip"
    try {
        Download-File "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-$uvTarget.zip" $uvZip
    } catch {
        throw "Could not download uv $UvVersion. Check that this machine can reach https://github.com, or install uv by hand:`n  https://docs.astral.sh/uv/getting-started/installation/"
    }
    Assert-Sha256 $uvZip "uv-$uvTarget.zip (uv $UvVersion)" $UvArchiveSha256[$uvTarget]

    $uvOut = Join-Path $Work 'uv'
    Expand-Archive -LiteralPath $uvZip -DestinationPath $uvOut -Force
    New-Item -ItemType Directory -Path $uvHome -Force | Out-Null
    foreach ($exe in 'uv.exe', 'uvx.exe') {
        $found = Get-ChildItem -LiteralPath $uvOut -Recurse -Filter $exe | Select-Object -First 1
        if ($found) { Copy-Item -LiteralPath $found.FullName -Destination $uvHome -Force }
    }
    if (-not (Test-Command 'uv')) {
        throw "uv was unpacked into $uvHome but is not on PATH. Open a new terminal and re-run this installer."
    }
    Write-Step 'uv installed.'
}

# -------------------------------------------------------------- ipmg
# The web extra too: someone running the one-liner expects `ipmg web` to work.
$target = '{0}[web] @ {1}' -f $Package, ([Uri] $wheelPath).AbsoluteUri

# IPMG 4 needs Python 3.10 or newer: uv uses one that is installed, or
# downloads one, instead of resolving an older IPMG for an older Python.
$pythonRequest = '>=3.10'

# uv tool install does not check hashes (a wrong one in a constraints file is
# ignored), so it only places the verified wheel and the pinned versions;
# the dependencies are then reinstalled with --require-hashes below.
# --no-build: a source distribution would run code no hash has vouched for.
Write-Step "Installing $Package $Version from the verified wheel..."
$ok = Invoke-WithRetry { uv tool install --python $pythonRequest --no-build --constraints $requirementsPath --upgrade $target }
if (-not $ok) {
    Write-Warn "Upgrade failed; retrying with a clean reinstall (this recovers from an earlier install of '$Package' from a different source)."
    $ok = Invoke-WithRetry { uv tool install --python $pythonRequest --no-build --constraints $requirementsPath --force $target }
    if (-not $ok) {
        throw "Could not install '$Package' $Version from $wheelName. Try it by hand to see the full error:`n  uv tool install --python '$pythonRequest' --no-build --force '$target'"
    }
}

Write-Step 'Checking every dependency against its pinned hash...'
$toolPython = Join-Path (Join-Path (Join-Path ((uv tool dir | Out-String).Trim()) $Package) 'Scripts') 'python.exe'
uv pip install --python $toolPython --reinstall --require-hashes --no-build --requirement $requirementsPath
if ($LASTEXITCODE -ne 0) {
    try { uv tool uninstall $Package } catch { }
    throw "A dependency did not match its pinned hash in $requirementsName; IPMG was removed again.`nSee the uv error above for the package. Nothing unverified was left installed."
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

} finally {
    Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
}
