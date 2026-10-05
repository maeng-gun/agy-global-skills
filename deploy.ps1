$skillsDir = "$PSScriptRoot\skills"
$targetBase = "$HOME\.gemini\config\skills"

# 1. Clean up obsolete legacy skills in targetBase
$obsoleteSkills = @("notion-uploader")
foreach ($obsolete in $obsoleteSkills) {
    $obsoletePath = Join-Path $targetBase $obsolete
    if (Test-Path $obsoletePath) {
        Remove-Item -Path $obsoletePath -Recurse -Force
        Write-Host "Cleaned up obsolete skill: $obsolete at $obsoletePath" -ForegroundColor Cyan
    }
}

# 2. Deploy active skills
if (Test-Path $skillsDir) {
    $skills = Get-ChildItem -Path $skillsDir -Directory
    foreach ($skill in $skills) {
        $dest = Join-Path $targetBase $skill.Name
        
        if (!(Test-Path $dest)) {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
        }
        
        Copy-Item -Path "$($skill.FullName)\*" -Destination $dest -Recurse -Force
        Write-Host "Deployed $($skill.Name) to $dest" -ForegroundColor Green
    }
} else {
    Write-Host "Skills directory not found at $skillsDir" -ForegroundColor Yellow
}
