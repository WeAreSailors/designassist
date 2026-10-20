# designassist setup for Windows (PowerShell). Safe to re-run.
#   powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}

if (-not (Have uv)) {
  Write-Host "installing uv ..."
  powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
# node is optional: only the Adobe-script tests run .jsx against mocks with it
if (-not (Have node) -and (Have winget)) {
  Write-Host "installing Node.js LTS (optional) ..."
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  Refresh-Path
}

uv sync

uv run da memory --init | Out-Null  # memory-os global tier if installed, else gitignored memory/
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# design apps: nothing to install, exports are files (+ live open through COM)
Get-ChildItem "$env:ProgramFiles\Adobe" -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "Adobe Illustrator*" -or $_.Name -like "Adobe Photoshop*" } |
  ForEach-Object { Write-Host "found: $($_.Name) - designassist can open its exports there" }

uv run da doctor
Write-Host ""
Write-Host "Done. Open this folder in Claude Code (claude) or Codex and describe the piece you want."
