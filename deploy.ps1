$source = "$PSScriptRoot\notion-uploader"
$dest = "$HOME\.gemini\config\skills\notion-uploader"

# Create destination if not exists
if (!(Test-Path $dest)) {
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
}

# Copy files, overwriting existing
Copy-Item -Path "$source\*" -Destination $dest -Recurse -Force

Write-Host "Deployed notion-uploader to $dest" -ForegroundColor Green
