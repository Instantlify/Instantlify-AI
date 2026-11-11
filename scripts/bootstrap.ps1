$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envTarget = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envTarget) {
    Write-Host '.env already exists; preserving your configuration.'
    exit 0
}
function New-RandomValue([int]$Size) {
    $randomBytes = New-Object byte[] $Size
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($randomBytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($randomBytes).Replace('+', '-').Replace('/', '_')
}
$djangoKey = (New-RandomValue 64).TrimEnd('=')
$fieldKey = New-RandomValue 32
$databasePassword = (New-RandomValue 32).TrimEnd('=')
$flowerPassword = (New-RandomValue 24).TrimEnd('=')
$template = Get-Content -LiteralPath (Join-Path $projectRoot '.env.example') -Raw
$template = $template.Replace('DJANGO_SECRET_KEY=GENERATE_WITH_BOOTSTRAP', "DJANGO_SECRET_KEY=$djangoKey")
$template = $template.Replace('FIELD_ENCRYPTION_KEYS=GENERATE_WITH_BOOTSTRAP', "FIELD_ENCRYPTION_KEYS=$fieldKey")
$template = $template.Replace('POSTGRES_PASSWORD=GENERATE_WITH_BOOTSTRAP', "POSTGRES_PASSWORD=$databasePassword")
$template = $template.Replace('instantlify:GENERATE_WITH_BOOTSTRAP@postgres', "instantlify:${databasePassword}@postgres")
$template = $template.Replace('local:GENERATE_WITH_BOOTSTRAP', "local:$flowerPassword")
[System.IO.File]::WriteAllText($envTarget, $template, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Created .env with random local secrets. Run docker compose up --build -d.'
