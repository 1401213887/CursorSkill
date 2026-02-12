#pragma region Engine ZXB

param(
    [switch]$SkipPip
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ("[upload2feishu] " + $Message)
}

function Assert-File {
    param([string]$Path, [string]$Hint)
    if (-not (Test-Path $Path)) {
        throw "Missing file: $Path`n$Hint"
    }
}

$SkillRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Join-Path $SkillRoot "scripts"
$ConfigDir = Join-Path $SkillRoot "config"
$UploadScript = Join-Path $ScriptsDir "feishu_upload.py"
$RequirementsFile = Join-Path $ScriptsDir "requirements.txt"
$AuthTemplate = Join-Path $ConfigDir "feishu_auth.template.json"
$AuthConfig = Join-Path $ConfigDir "feishu_auth.json"
$LegacyConfig = Join-Path $env:USERPROFILE ".feishu-docx\config.json"

Write-Step "Skill root: $SkillRoot"
Assert-File -Path $UploadScript -Hint "Please keep scripts/feishu_upload.py in this skill."
Assert-File -Path $RequirementsFile -Hint "Please keep scripts/requirements.txt in this skill."
Assert-File -Path $AuthTemplate -Hint "Please keep config/feishu_auth.template.json in this skill."

Write-Step "Checking Python 3.11..."
& py -3.11 --version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 is required. Install Python 3.11 and make sure 'py -3.11' works."
}

if (-not $SkipPip) {
    Write-Step "Installing dependencies..."
    & py -3.11 -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency install failed. Check network or pip settings."
    }
} else {
    Write-Step "Skipped dependency install (-SkipPip)."
}

Write-Step "Validating upload script..."
& py -3.11 $UploadScript --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Upload script failed to run. Check script and Python environment."
}

if (-not (Test-Path $AuthConfig)) {
    if (Test-Path $LegacyConfig) {
        Write-Step "Found legacy credentials. Copying to skill-local config..."
        Copy-Item -Path $LegacyConfig -Destination $AuthConfig -Force
    } else {
        Write-Step "No local credentials found. Creating template config..."
        Copy-Item -Path $AuthTemplate -Destination $AuthConfig -Force
        Write-Host ""
        Write-Host "Edit the file below and fill app_id/app_secret before using upload:"
        Write-Host "  $AuthConfig"
        Write-Host ""
    }
} else {
    Write-Step "Detected local credentials: $AuthConfig"
}

Write-Host ""
Write-Host "[OK] upload2feishu install/self-check completed."
Write-Host "Example command:"
Write-Host "  py -3.11 `"$UploadScript`" --help"
Write-Host ""

#pragma endregion
