# Kept in the public release repository; build logs and private checkout stay on the runner.
param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Revision)
$ErrorActionPreference = 'Stop'
if ($Revision -notmatch '^[a-f0-9]{40}$') { throw 'A fixed source SHA is required' }
$Source = (Resolve-Path -LiteralPath $Source).Path
if ((git -C $Source rev-parse HEAD) -ne $Revision) { throw 'Private checkout SHA differs' }
$env:LEES_CAD_BUILD_SHA = $Revision
$env:RUSTUP_TOOLCHAIN = '1.96.0'
$env:CARGO_BUILD_JOBS = '2'
$env:CARGO_PROFILE_DEV_DEBUG = '0'
$env:LEES_CAD_BUILD_DATE = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd')
$env:CARGO_TARGET_DIR = Join-Path $env:RUNNER_TEMP 'cad-build'
$env:CARGO_HOME = Join-Path $env:RUNNER_TEMP 'cad-cargo'
# Quality tests do not measure optimized rendering performance. This is runner-local only;
# release optimization stays unchanged, and no private cache is uploaded.
New-Item -ItemType Directory -Force -Path $env:CARGO_HOME | Out-Null
@'
[profile.dev.package."*"]
opt-level = 0
'@ | Set-Content -LiteralPath (Join-Path $env:CARGO_HOME 'config.toml') -Encoding utf8
$env:DIST = Join-Path $env:GITHUB_WORKSPACE 'public-assets'
$env:LEES_CAD_CONFIG_DIR = Join-Path $env:RUNNER_TEMP 'cad-profile'
New-Item -ItemType Directory -Force -Path $env:DIST, $env:LEES_CAD_CONFIG_DIR | Out-Null
$log = Join-Path $env:RUNNER_TEMP 'private-build.log'
function Step([string]$Name, [scriptblock]$Work) {
  Write-Output "==> $Name"
  $failed = $false
  try {
    & $Work >> $log 2>&1
    $failed = $LASTEXITCODE -ne 0
  } catch {
    # Terminating PowerShell errors must not escape with private source excerpts.
    $_ | Out-String | Add-Content -LiteralPath $log
    $failed = $true
  }
  if ($failed) {
    # Only identifiers/locations leave the runner. Never print code, assertions or raw logs.
    $lines = Get-Content -LiteralPath $log
    $tests = @($lines | ForEach-Object { if ($_ -match '^test (.+) \.\.\. FAILED$') { $Matches[1] } })
    $locations = @($lines | ForEach-Object {
      if ($_ -match 'panicked at (.*\.rs):([0-9]+):([0-9]+)' -or $_ -match '^\s*-->\s*(.*\.rs):([0-9]+):([0-9]+)') {
        $path = $Matches[1] -replace '\\', '/'
        $path = $path -replace '^.*private-source/', ''
        "$path`:$($Matches[2])`:$($Matches[3])"
      }
    })
    $codes = @($lines | ForEach-Object {
      if ($_ -match '^error\[([A-Z0-9]+)\]' -or $_ -match '\berror (WIX[0-9]{4})\b') { $Matches[1] }
    } | Select-Object -Unique)
    @{phase=$Name; failedTests=$tests; locations=$locations; compilerCodes=$codes} | ConvertTo-Json -Compress | Write-Output
    throw "$Name failed; code and private build log remain only on this runner"
  }
}
Push-Location $Source
try {
  Step 'build error regression' { & (Join-Path $PSScriptRoot 'test-build-errors.ps1') }
  if ($IsWindows) {
    Step 'certificate setup regression' { & (Join-Path $PSScriptRoot 'test-windows-certificate.ps1') }
    Step 'self-signed runner certificate' { & (Join-Path $PSScriptRoot 'windows-certificate.ps1') }
  }
  Step 'install Rust 1.96.0' { rustup toolchain install 1.96.0 --profile minimal --component rustfmt --component clippy }
  Step 'format' { cargo +1.96.0 fmt --all -- --check }
  Step 'quality and regression' { cargo +1.96.0 xtask ci }
  Step 'product identity' { python scripts/check-identity.py }
  Step 'identity scanner regression' { python scripts/test-check-identity.py }
  Step 'icon validator dependency' { python -m pip install pillow==12.3.0 }
  Step 'approved application icon frames' { python scripts/test-app-icons.py }
  # The private source remote is intentionally absent in an Actions checkout.
  if ($IsWindows) {
    Step 'install WiX' { dotnet tool install --global wix --version 5.0.2 }
    Step 'WiX UI extension' { wix extension add -g WixToolset.UI.wixext/5.0.2 }
    # GITHUB_ENV is read by later steps; this call also sets current process values.
    $env:WINDOWS_CERTIFICATE_PASSWORD = $env:LEESCAD_WINDOWS_PFX_PASSWORD
    Step 'Windows package' { & packaging/windows/package.ps1 -Arch x64 }
    Step 'Windows native artifact identity' { & (Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc/release/lees-cad.exe') --verify-update-artifact $env:DIST }
  } else {
    $env:MACOS_SIGN_IDENTITY = '-'
    Step 'macOS package' { bash packaging/macos/package.sh --arch aarch64 }
    Step 'macOS native artifact identity' { & (Join-Path $env:CARGO_TARGET_DIR 'aarch64-apple-darwin/release/lees-cad') --verify-update-artifact $env:DIST }
  }
} finally { Pop-Location }
