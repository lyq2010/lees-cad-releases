# Ephemeral CI runner only. User installations do not import trust certificates automatically.
$ErrorActionPreference = 'Stop'
$folder = Join-Path $env:RUNNER_TEMP "lees-cad-certificate-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $folder | Out-Null
$pfxPath = Join-Path $folder 'signing.pfx'
[IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($env:LEESCAD_WINDOWS_PFX_BASE64))
$password = ConvertTo-SecureString -String $env:LEESCAD_WINDOWS_PFX_PASSWORD -AsPlainText -Force
$cert = Get-PfxCertificate -FilePath $pfxPath -Password $password
$config = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'public-config.json') | ConvertFrom-Json
$hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cert.RawData)).ToLowerInvariant()
if ($hash -ne $config.windowsCertificateSha256) { throw 'Windows certificate identity differs' }
$cerPath = Join-Path $folder 'signing.cer'
[IO.File]::WriteAllBytes($cerPath, $cert.RawData)
Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
Import-Certificate -FilePath $cerPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
"WINDOWS_PFX_PATH=$pfxPath" >> $env:GITHUB_ENV
"WINDOWS_CERTIFICATE_PASSWORD=$env:LEESCAD_WINDOWS_PFX_PASSWORD" >> $env:GITHUB_ENV
$env:WINDOWS_PFX_PATH = $pfxPath
$env:WINDOWS_CERTIFICATE_PASSWORD = $env:LEESCAD_WINDOWS_PFX_PASSWORD
Write-Output "Ephemeral runner trusts the pinned self-signed certificate; clean user systems remain unverified."
