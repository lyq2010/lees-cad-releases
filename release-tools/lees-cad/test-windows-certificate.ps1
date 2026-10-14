# Synthetic certificate regression; Import-Certificate is mocked, never changes host trust.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'This regression requires Windows' }
$root = Join-Path ([IO.Path]::GetTempPath()) "lees-cad-certificate-test-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $root | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows-certificate.ps1') -Destination $root
$rsa = [Security.Cryptography.RSA]::Create(2048)
$request = [Security.Cryptography.X509Certificates.CertificateRequest]::new(
    'CN=Lee CAD synthetic test', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256,
    [Security.Cryptography.RSASignaturePadding]::Pkcs1)
$cert = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(1))
$hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData)).ToLowerInvariant()
$names = 'GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'RUNNER_TEMP', 'GITHUB_ENV',
    'LEESCAD_WINDOWS_PFX_BASE64', 'LEESCAD_WINDOWS_PFX_PASSWORD', 'WINDOWS_PFX_PATH', 'WINDOWS_CERTIFICATE_PASSWORD'
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name) }
$imports = [Collections.Generic.List[string]]::new()
function Import-Certificate {
    param($FilePath, $CertStoreLocation, [switch]$Confirm)
    if ($CertStoreLocation -eq 'Cert:\CurrentUser\Root') { throw 'Interactive root trust prompt' }
    if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($FilePath)) -ne [Convert]::ToBase64String($cert.RawData)) {
        throw 'Imported certificate differs'
    }
    $imports.Add($CertStoreLocation)
}
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Expect-Failure([scriptblock]$Work, [string]$Message, [string]$ErrorPattern) {
    $failed = $false
    try { & $Work | Out-Null } catch {
        if ($ErrorPattern) { Assert ($_.Exception.Message -match $ErrorPattern) "Unexpected rejection: $Message" }
        Assert ($_.Exception.Message -notmatch 'NonInteractive|prompt') 'Failure must not depend on an interactive prompt'
        $failed = $true
    }
    Assert $failed $Message
    Assert ($imports.Count -eq 0) 'Rejected input must not change trust'
}
try {
    $env:GITHUB_ACTIONS = 'true'
    $env:RUNNER_ENVIRONMENT = 'github-hosted'
    $env:RUNNER_TEMP = $root
    $env:GITHUB_ENV = Join-Path $root 'github-env'
    $env:LEESCAD_WINDOWS_PFX_PASSWORD = 'synthetic-test-password'
    $env:LEESCAD_WINDOWS_PFX_BASE64 = [Convert]::ToBase64String($cert.Export(
        [Security.Cryptography.X509Certificates.X509ContentType]::Pkcs12, $env:LEESCAD_WINDOWS_PFX_PASSWORD))
    $scriptPath = Join-Path $root 'windows-certificate.ps1'
    $configPath = Join-Path $root 'public-config.json'
    @{windowsCertificateSha256 = '0' * 64} | ConvertTo-Json | Set-Content -LiteralPath $configPath
    Expect-Failure { & $scriptPath } 'Wrong publisher must fail' 'certificate identity differs'
    @{windowsCertificateSha256 = $hash} | ConvertTo-Json | Set-Content -LiteralPath $configPath
    $env:RUNNER_ENVIRONMENT = 'self-hosted'
    Expect-Failure { & $scriptPath } 'Self-hosted execution must fail before trust changes' 'GitHub-hosted runner'
    $env:RUNNER_ENVIRONMENT = 'github-hosted'
    $env:GITHUB_ACTIONS = $null
    Expect-Failure { & $scriptPath } 'Local execution must fail before trust changes' 'GitHub-hosted runner'
    $env:GITHUB_ACTIONS = 'true'
    $env:LEESCAD_WINDOWS_PFX_PASSWORD = 'wrong-password'
    Expect-Failure { & $scriptPath } 'Wrong PFX password must fail without prompting'
    $env:LEESCAD_WINDOWS_PFX_PASSWORD = 'synthetic-test-password'
    & $scriptPath | Out-Null
    Assert (($imports -join ',') -eq 'Cert:\LocalMachine\Root,Cert:\LocalMachine\TrustedPublisher') 'Hosted trust must finish without a user root prompt'
    Assert (Test-Path -LiteralPath $env:WINDOWS_PFX_PATH) 'Signing PFX must be available to the current build'
    Assert ((Get-Content -Raw -LiteralPath $env:GITHUB_ENV).Contains("WINDOWS_PFX_PATH=$env:WINDOWS_PFX_PATH")) 'Later workflow steps must receive the signing path'
    Write-Output 'Certificate regression passed: publisher, runner scope, password, unattended trust and signing handoff'
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name]) }
    $cert.Dispose()
    $rsa.Dispose()
    # Synthetic files are retained for authorized cleanup, never contain production keys.
}
