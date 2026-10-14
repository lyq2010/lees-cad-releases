# Ephemeral CI runner only. User installations do not import trust certificates automatically.
$ErrorActionPreference = 'Stop'
if (-not $IsWindows -or $env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Certificate trust setup requires a Windows GitHub-hosted runner'
}
$folder = Join-Path $env:RUNNER_TEMP "lees-cad-certificate-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $folder | Out-Null
$pfxPath = Join-Path $folder 'signing.pfx'
[IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($env:LEESCAD_WINDOWS_PFX_BASE64))
$password = ConvertTo-SecureString -String $env:LEESCAD_WINDOWS_PFX_PASSWORD -AsPlainText -Force
$cert = Get-PfxCertificate -FilePath $pfxPath -Password $password -NoPromptForPassword
$config = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'public-config.json') | ConvertFrom-Json
$hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData)).ToLowerInvariant()
if ($hash -ne $config.windowsCertificateSha256) { throw 'Windows certificate identity differs' }
$cerPath = Join-Path $folder 'signing.cer'
[IO.File]::WriteAllBytes($cerPath, $cert.RawData)
# CurrentUser Root can display a native security dialog and hang unattended builds.
# GitHub-hosted Windows runners are disposable administrator VMs.
Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\LocalMachine\Root -Confirm:$false | Out-Null
Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\LocalMachine\TrustedPublisher -Confirm:$false | Out-Null
"WINDOWS_PFX_PATH=$pfxPath" >> $env:GITHUB_ENV
"WINDOWS_CERTIFICATE_PASSWORD=$env:LEESCAD_WINDOWS_PFX_PASSWORD" >> $env:GITHUB_ENV
$env:WINDOWS_PFX_PATH = $pfxPath
$env:WINDOWS_CERTIFICATE_PASSWORD = $env:LEESCAD_WINDOWS_PFX_PASSWORD
Write-Output "Ephemeral runner trusts the pinned self-signed certificate; clean user systems remain unverified."
