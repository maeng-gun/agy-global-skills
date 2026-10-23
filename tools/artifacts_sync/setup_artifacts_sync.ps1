<#
.SYNOPSIS
    One-Click Setup and Migration Launcher for Antigravity Conversation Artifacts.

.DESCRIPTION
    Configures Antigravity conversation artifact synchronization and migration:
    1. Deploys the global artifact mirroring rule to ~/.gemini/config/GEMINI.md (idempotent with markers).
    2. Deploys the custom artifacts-sync skill to ~/.gemini/config/skills/artifacts-sync/SKILL.md.
    3. Executes sync_artifacts.py to create Windows Directory Junctions (mklink /J), update .gitignore,
       and migrate historical conversation artifacts to Google Drive with SHA-256 conflict resolution.

.PARAMETER DryRun
    Simulate actions without making filesystem changes.

.PARAMETER ProjectsDir
    Custom root directory to scan for local Git projects (default: ~/Documents).

.PARAMETER GDriveRoot
    Custom path to Google Drive root directory (overrides automatic detection).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_artifacts_sync.ps1
    powershell -ExecutionPolicy Bypass -File .\setup_artifacts_sync.ps1 -DryRun
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$DeployOnly,
    [string]$ProjectsDir = "",
    [string]$GDriveRoot = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host " Antigravity Artifact Synchronization & Migration Launcher" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# Resolve Base Paths Dynamically
$scriptDir = $PSScriptRoot
if (-not $scriptDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$repoRoot = Split-Path (Split-Path $scriptDir -Parent) -Parent
$userHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }

$ruleTemplatePath = Join-Path $repoRoot "rules\artifact_mirror_rule.md"
$skillSourceDir   = Join-Path $repoRoot "skills\artifacts-sync"
$syncEnginePath   = Join-Path $scriptDir "sync_artifacts.py"

$geminiConfigDir  = Join-Path $userHome ".gemini\config"
$geminiMdPath     = Join-Path $geminiConfigDir "GEMINI.md"
$skillTargetDir   = Join-Path $geminiConfigDir "skills\artifacts-sync"

Write-Host "Script Root : $scriptDir"
Write-Host "Repo Root   : $repoRoot"
Write-Host "User Home   : $userHome"
if ($DryRun) {
    Write-Host "Mode        : DRY-RUN (Simulating changes)" -ForegroundColor Yellow
}
Write-Host "--------------------------------------------------------------------------------"

# ============================================================================
# Step 1: Deploy Global Artifact Mirroring Rule to GEMINI.md
# ============================================================================
Write-Host "[Step 1/3] Deploying Global Artifact Mirroring Rule..." -ForegroundColor Yellow

$markerStart = "<!-- AGY_ARTIFACT_MIRROR_RULE_START -->"
$markerEnd   = "<!-- AGY_ARTIFACT_MIRROR_RULE_END -->"

if (-not (Test-Path $ruleTemplatePath)) {
    Write-Error "Rule template not found at: $ruleTemplatePath"
    exit 1
}

$rawRuleContent = [System.IO.File]::ReadAllText($ruleTemplatePath, [System.Text.Encoding]::UTF8)

# Normalize rule content so it is cleanly wrapped with delimiters exactly once
$ruleBody = $rawRuleContent
if ($ruleBody.Contains($markerStart) -and $ruleBody.Contains($markerEnd)) {
    $startIndex = $ruleBody.IndexOf($markerStart)
    $endIndex = $ruleBody.IndexOf($markerEnd) + $markerEnd.Length
    $markedBlock = $ruleBody.Substring($startIndex, $endIndex - $startIndex).Trim()
} else {
    $markedBlock = "$markerStart`r`n$($ruleBody.Trim())`r`n$markerEnd"
}

if ($DryRun) {
    Write-Host "  [DRY-RUN] Would update: $geminiMdPath" -ForegroundColor DarkCyan
    if (Test-Path $geminiMdPath) {
        $existing = [System.IO.File]::ReadAllText($geminiMdPath, [System.Text.Encoding]::UTF8)
        if ($existing.Contains($markerStart) -and $existing.Contains($markerEnd)) {
            Write-Host "  [DRY-RUN] Existing marker section found -> Would replace marked section." -ForegroundColor DarkCyan
        } else {
            Write-Host "  [DRY-RUN] No existing marker found -> Would append marked section to preserve user rules." -ForegroundColor DarkCyan
        }
    } else {
        Write-Host "  [DRY-RUN] GEMINI.md does not exist -> Would create file with marked rule block." -ForegroundColor DarkCyan
    }
} else {
    if (-not (Test-Path $geminiConfigDir)) {
        New-Item -ItemType Directory -Path $geminiConfigDir -Force | Out-Null
    }

    if (Test-Path $geminiMdPath) {
        $existingText = [System.IO.File]::ReadAllText($geminiMdPath, [System.Text.Encoding]::UTF8)
        if ($existingText.Contains($markerStart) -and $existingText.Contains($markerEnd)) {
            $pattern = "(?s)" + [regex]::Escape($markerStart) + ".*?" + [regex]::Escape($markerEnd)
            $updatedText = [regex]::Replace($existingText, $pattern, $markedBlock)
            [System.IO.File]::WriteAllText($geminiMdPath, $updatedText, [System.Text.Encoding]::UTF8)
            Write-Host "  [SUCCESS] Updated existing rule block in $geminiMdPath" -ForegroundColor Green
        } else {
            $prefix = if ([string]::IsNullOrWhiteSpace($existingText)) { "" } else { $existingText.TrimEnd() + "`r`n`r`n" }
            $updatedText = $prefix + $markedBlock + "`r`n"
            [System.IO.File]::WriteAllText($geminiMdPath, $updatedText, [System.Text.Encoding]::UTF8)
            Write-Host "  [SUCCESS] Appended rule block to existing $geminiMdPath (preserved existing rules)" -ForegroundColor Green
        }
    } else {
        $initialText = $markedBlock + "`r`n"
        [System.IO.File]::WriteAllText($geminiMdPath, $initialText, [System.Text.Encoding]::UTF8)
        Write-Host "  [SUCCESS] Created $geminiMdPath with rule block" -ForegroundColor Green
    }
}

# ============================================================================
# Step 2: Deploy Custom Skill to ~/.gemini/config/skills/artifacts-sync/
# ============================================================================
Write-Host "[Step 2/3] Deploying artifacts-sync Custom Skill..." -ForegroundColor Yellow

$skillSourceFile = Join-Path $skillSourceDir "SKILL.md"
if (-not (Test-Path $skillSourceFile)) {
    Write-Error "Skill definition not found at: $skillSourceFile"
    exit 1
}

if ($DryRun) {
    Write-Host "  [DRY-RUN] Would deploy skill from $skillSourceDir to $skillTargetDir" -ForegroundColor DarkCyan
} else {
    if (-not (Test-Path $skillTargetDir)) {
        New-Item -ItemType Directory -Path $skillTargetDir -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $skillSourceDir "*") -Destination $skillTargetDir -Recurse -Force
    Write-Host "  [SUCCESS] Deployed skill to: $skillTargetDir" -ForegroundColor Green
}

if ($DeployOnly) {
    Write-Host "[Step 3/3] Skipping migration engine execution (-DeployOnly specified)." -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------------------------------"
    Write-Host " Configuration and Skill Deployment Completed Successfully!" -ForegroundColor Green
    Write-Host "================================================================================" -ForegroundColor Cyan
    exit 0
}

# ============================================================================
# Step 3: Run sync_artifacts.py Engine (--setup-junctions --migrate)
# ============================================================================
Write-Host "[Step 3/3] Executing Artifact Migration & Junction Engine..." -ForegroundColor Yellow

if (-not (Test-Path $syncEnginePath)) {
    Write-Error "Engine script not found at: $syncEnginePath"
    exit 1
}

# Resolve Python Executable
$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonExe = "python3"
} else {
    Write-Error "Python executable ('python', 'py', or 'python3') not found in PATH."
    exit 1
}

$engineArgs = @($syncEnginePath, "--setup-junctions", "--migrate")

if ($DryRun) {
    $engineArgs += "--dry-run"
}
if ($ProjectsDir) {
    $engineArgs += @("--projects-dir", $ProjectsDir)
}
if ($GDriveRoot) {
    $engineArgs += @("--gdrive-root", $GDriveRoot)
}

Write-Host "Running: $pythonExe $($engineArgs -join ' ')" -ForegroundColor DarkGray
Write-Host "--------------------------------------------------------------------------------"

& $pythonExe $engineArgs
$exitCode = $LASTEXITCODE

Write-Host "--------------------------------------------------------------------------------"
if ($exitCode -eq 0) {
    Write-Host " Antigravity Artifact Setup & Migration Completed Successfully!" -ForegroundColor Green
} else {
    Write-Host " Engine completed with exit code: $exitCode (Check warnings/errors above)." -ForegroundColor Red
}
Write-Host "================================================================================" -ForegroundColor Cyan

exit $exitCode
