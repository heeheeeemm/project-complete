$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-ProjectGit {
    param([string[]]$GitArguments)
    & git @GitArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed. No force push was attempted: git $($GitArguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath '.git')) {
    Invoke-ProjectGit -GitArguments @('init', '-b', 'master')
}

$files = @(
    '.gitignore', '.env.example', 'README.md', 'requirements.txt', 'manage.py',
    'accounts', 'books', 'mypjt', 'templates', 'screenshots', 'media', 'upload.ps1'
)
Invoke-ProjectGit -GitArguments (@('add', '--') + $files)
& git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    Invoke-ProjectGit -GitArguments @('commit', '-m', 'Implement book community with AI author profiles and requirement screenshots')
} elseif ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect staged changes.'
}

$remoteUrl = 'https://lab.ssafy.com/s16/e02/04_pjt_moonheehyeon.git'
$remotes = @(& git remote)
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect Git remotes.'
}
if ($remotes -contains 'origin') {
    Invoke-ProjectGit -GitArguments @('remote', 'set-url', 'origin', $remoteUrl)
} else {
    Invoke-ProjectGit -GitArguments @('remote', 'add', 'origin', $remoteUrl)
}

# A normal push preserves any existing remote history by rejecting conflicting updates.
Invoke-ProjectGit -GitArguments @('push', '-u', 'origin', 'HEAD:master')

# Remove main only after the complete submission was successfully pushed to master.
& git ls-remote --exit-code --heads origin refs/heads/main | Out-Null
if ($LASTEXITCODE -eq 0) {
    Invoke-ProjectGit -GitArguments @('push', 'origin', '--delete', 'main')
} elseif ($LASTEXITCODE -ne 2) {
    throw 'Unable to verify remote main. No branch deletion was attempted.'
}
Write-Host 'Upload to master completed. Remote main is absent.'
