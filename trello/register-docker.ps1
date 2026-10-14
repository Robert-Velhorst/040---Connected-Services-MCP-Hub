<#
    Register the Docker-based Trello connector with the ChatGPT app / Codex.

    Used by install-docker.bat so the host needs no Python at all - PowerShell
    ships with Windows. Behaviour matches setup_codex.py --docker: it backs the
    file up, replaces only its own [mcp_servers.trello] block, and leaves every
    other server and setting untouched.
#>
[CmdletBinding()]
param(
    [string]$EnvFile,
    [string]$Image  = "trello-mcp:latest",
    [string]$Volume = "trello-mcp-data",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

$configDir  = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $configDir "config.toml"

if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

$original = ""
if (Test-Path $configPath) {
    $original = Get-Content -Path $configPath -Raw -Encoding UTF8
    if ($original.Trim()) {
        $stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
        $backup = "$configPath.bak-$stamp"
        Copy-Item -Path $configPath -Destination $backup -Force
        Write-Output "backed up   : $backup"
    }
}

# Drop any existing trello block, up to the next top-level table that is not
# one of its own sub-tables.
$pattern = '(?ms)^\[mcp_servers\.trello\].*?(?=^\[(?!mcp_servers\.trello\.)|\Z)'
$updated = [regex]::Replace($original, $pattern, '')
$updated = [regex]::Replace($updated, '(\r?\n){3,}', "`r`n`r`n").TrimEnd()

if (-not $Remove) {
    # TOML literal strings (single quotes) keep Windows backslashes as-is.
    $block = @"

[mcp_servers.trello]
command = "docker"
args = [
    "run", "--rm", "-i",
    "--env-file", '$EnvFile',
    "-v", "${Volume}:/data",
    "$Image",
]
# A cold container start needs more than the 10s default.
startup_timeout_sec = 90
tool_timeout_sec = 120
enabled = true
"@
    if ($updated.Trim()) { $updated = $updated + "`r`n" + $block } else { $updated = $block.TrimStart() }
}

$updated = $updated.TrimEnd() + "`r`n"

# UTF-8 without BOM: a BOM would break the TOML parser on the first key.
[System.IO.File]::WriteAllText($configPath, $updated, (New-Object System.Text.UTF8Encoding($false)))

if ($Remove) {
    Write-Output "trello removed from $configPath"
} else {
    Write-Output "trello registered in $configPath"
    Write-Output "mode        : Docker (image $Image, volume $Volume)"
    Write-Output "              Docker Desktop must be running when you use ChatGPT."
}
exit 0
