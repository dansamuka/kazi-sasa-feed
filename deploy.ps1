[CmdletBinding()]
param(
    [string]$CommitMessage = "Deploy Africa and eligibility certification hardening"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/dansamuka/kazi-sasa-feed.git"
$RepoName = "dansamuka/kazi-sasa-feed"
$SourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TempRoot = Join-Path $env:TEMP ("kazi-sasa-feed-deploy-" + [guid]::NewGuid().ToString("N"))
$CloneRoot = Join-Path $TempRoot "repo"
$BackupRoot = Join-Path $TempRoot "generated-backup"

$GeneratedPaths = @(
    "feed.json",
    "certified_feed.json",
    "currency_rates.json",
    "docs/index.html",
    "reports/coverage_report.json",
    "reports/source_health.json",
    "reports/collector_manifest.json",
    "reports/collector_errors.json",
    "reports/deduplication_report.json",
    "reports/coverage_gate_report.json",
    "reports/africa_eligibility_certification_report.json",
    "reports/rejected_records.json",
    "reports/investment_coverage_report.json",
    "reports/dfi_coverage_report.json",
    "reports/ngo_coverage_report.json",
    "reports/government_coverage_report.json",
    "reports/kenya_public_institutions_report.json",
    "reports/multinational_coverage_report.json",
    "reports/registry_report.json"
)

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Copy-PreservedFile([string]$RelativePath, [string]$FromRoot, [string]$ToRoot) {
    $source = Join-Path $FromRoot $RelativePath
    if (-not (Test-Path -LiteralPath $source)) { return }
    $target = Join-Path $ToRoot $RelativePath
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

try {
    Assert-Command "git"
    New-Item -ItemType Directory -Force -Path $TempRoot, $BackupRoot | Out-Null

    Write-Host "[1/6] Cloning the current repository so live generated artifacts are preserved..."
    git clone --depth 1 $RepoUrl $CloneRoot
    if ($LASTEXITCODE -ne 0) { throw "git clone failed." }

    Write-Host "[2/6] Backing up the current live feed, site, and runtime reports..."
    foreach ($path in $GeneratedPaths) {
        Copy-PreservedFile $path $CloneRoot $BackupRoot
    }

    Write-Host "[3/6] Overlaying the new source package without force-pushing an offline snapshot..."
    $null = & robocopy $SourceRoot $CloneRoot /MIR /R:2 /W:1 /XD ".git" "__pycache__" ".pytest_cache" ".http-cache" ".runtime" /XF "deploy.log"
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE." }

    foreach ($path in $GeneratedPaths) {
        Copy-PreservedFile $path $BackupRoot $CloneRoot
    }

    Write-Host "[4/6] Committing source and workflow changes..."
    Push-Location $CloneRoot
    git config user.name "D Samuka"
    git config user.email "actions@users.noreply.github.com"
    git add -A
    git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        git commit -m $CommitMessage
        if ($LASTEXITCODE -ne 0) { throw "git commit failed." }
    } else {
        Write-Host "No source changes required a new commit."
    }

    Write-Host "[5/6] Pushing normally to main (no force push)..."
    git push origin main
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }

    Write-Host "[6/6] Triggering the refresh workflow when GitHub CLI is available..."
    $gh = Get-Command "gh" -ErrorAction SilentlyContinue
    if ($gh) {
        gh auth status 2>$null
        if ($LASTEXITCODE -eq 0) {
            gh workflow run refresh-feed.yml --repo $RepoName
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Refresh workflow triggered."
            } else {
                Write-Warning "The source push succeeded, but the workflow could not be triggered automatically."
                Start-Process "https://github.com/$RepoName/actions/workflows/refresh-feed.yml"
            }
        } else {
            Start-Process "https://github.com/$RepoName/actions/workflows/refresh-feed.yml"
        }
    } else {
        Start-Process "https://github.com/$RepoName/actions/workflows/refresh-feed.yml"
    }

    Write-Host ""
    Write-Host "SUCCESS: Source code was deployed without overwriting the current live feed."
    Write-Host "The workflow first applies Africa/access certification to the existing live feed, commits it,"
    Write-Host "then attempts a full live refresh. If a collector fails, the certified"
    Write-Host "last-known-good feed remains published."
}
finally {
    Pop-Location -ErrorAction SilentlyContinue
    if (Test-Path $TempRoot) {
        Remove-Item -Recurse -Force $TempRoot -ErrorAction SilentlyContinue
    }
}
