param(
    [string]$Repository = 'Instantlify/Instantlify-AI'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'Install GitHub CLI from https://cli.github.com and run gh auth login first.'
}

function Invoke-GitHubJson {
    param([string]$Endpoint, [string]$Method = 'GET', $Body = $null)
    if ($null -eq $Body) {
        $result = & gh api $Endpoint --method $Method
    } else {
        $result = $Body | ConvertTo-Json -Depth 20 | & gh api $Endpoint --method $Method --input -
    }
    if ($LASTEXITCODE -ne 0) { throw "GitHub request failed: $Method $Endpoint" }
    if ($result) { return ($result | ConvertFrom-Json) }
}

# Complete all read-only preflight checks before changing any settings.
$repo = Invoke-GitHubJson "repos/$Repository"
if (-not $repo.permissions.admin) { throw 'Repository admin access is required.' }
if ($repo.default_branch -ne 'main') { throw 'Expected main as the default branch. Review the repository setup first.' }
foreach ($branch in @('main', 'dev')) {
    $branchInfo = Invoke-GitHubJson "repos/$Repository/branches/$branch"
    if ($branchInfo.protected) {
        throw "$branch already has protection or a ruleset. Review and update its existing policy manually to preserve stronger rules."
    }
    $null = Invoke-GitHubJson "repos/$Repository/contents/.github/workflows/branch-policy.yml?ref=$branch"
    $null = Invoke-GitHubJson "repos/$Repository/contents/.github/workflows/ci.yml?ref=$branch"
}

$protection = @{
    required_status_checks = @{
        strict = $false
        checks = @('source-branch', 'backend', 'frontend', 'integration') | ForEach-Object {
            @{ context = $_; app_id = 15368 } # GitHub Actions
        }
    }
    enforce_admins = $true
    required_pull_request_reviews = @{
        required_approving_review_count = 0
        dismiss_stale_reviews = $true
        require_code_owner_reviews = $false
        require_last_push_approval = $false
        bypass_pull_request_allowances = @{ users = @(); teams = @(); apps = @() }
    }
    restrictions = $null
    required_linear_history = $false
    allow_force_pushes = $false
    allow_deletions = $false
    required_conversation_resolution = $true
}

# This sets the complete classic protection policy. Inspect existing protections
# and rulesets before running; preserve any stronger organization requirements.
foreach ($branch in @('dev', 'main')) {
    $null = Invoke-GitHubJson "repos/$Repository/branches/$branch/protection" 'PUT' $protection
    $actual = Invoke-GitHubJson "repos/$Repository/branches/$branch/protection"
    if (-not $actual.enforce_admins.enabled -or $actual.allow_force_pushes.enabled -or
        $actual.allow_deletions.enabled -or $null -eq $actual.required_pull_request_reviews) {
        throw "Protection verification failed for $branch. Inspect GitHub settings."
    }
    $contexts = @($actual.required_status_checks.checks | ForEach-Object { $_.context })
    foreach ($check in @('source-branch', 'backend', 'frontend', 'integration')) {
        if ($check -notin $contexts) { throw "Missing required check on ${branch}: $check" }
    }
    Write-Host "Verified PR-only protection and required checks for $branch."
}
