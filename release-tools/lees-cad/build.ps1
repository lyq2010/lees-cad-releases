# Kept in the public release repository; build logs and private checkout stay on the runner.
param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Revision,
      [ValidateSet(2, 4)][int]$WindowsJobs = 4)
$ErrorActionPreference = 'Stop'
if ($Revision -notmatch '^[a-f0-9]{40}$') { throw 'A fixed source SHA is required' }
$Source = (Resolve-Path -LiteralPath $Source).Path
if ((git -C $Source rev-parse HEAD) -ne $Revision) { throw 'Private checkout SHA differs' }
$env:LEES_CAD_BUILD_SHA = $Revision
$env:RUSTUP_TOOLCHAIN = '1.96.0'
. (Join-Path $PSScriptRoot 'build-settings.ps1')
$env:CARGO_BUILD_JOBS = [string](Get-BuildJobs -WindowsHost $IsWindows -WindowsJobs $WindowsJobs)
@{phase='build configuration'; logicalCpus=[Environment]::ProcessorCount; compilerJobs=[int]$env:CARGO_BUILD_JOBS} | ConvertTo-Json -Compress | Write-Output
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
  $timer = [Diagnostics.Stopwatch]::StartNew()
  $failed = $false
  try {
    & $Work >> $log 2>&1
    $failed = $LASTEXITCODE -ne 0
  } catch {
    # Terminating PowerShell errors must not escape with private source excerpts.
    $_ | Out-String | Add-Content -LiteralPath $log
    $failed = $true
  }
  $timer.Stop()
  @{phase=$Name; elapsedSeconds=[math]::Round($timer.Elapsed.TotalSeconds, 3);
    result=$(if ($failed) { 'failed' } else { 'passed' })} | ConvertTo-Json -Compress | Write-Output
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
  Step 'compiler budget regression' { & (Join-Path $PSScriptRoot 'test-build-settings.ps1') }
  Step 'MPL source archive regression' { python scripts/test-package-mpl-source.py }
  Step 'shared CAD font packaging regression' { python scripts/test-package-fonts.py }
  if ($IsWindows) {
    Step 'Windows package selection regression' { & (Join-Path $PSScriptRoot 'test-windows-package.ps1') -Source $Source }
    Step 'certificate setup regression' { & (Join-Path $PSScriptRoot 'test-windows-certificate.ps1') }
    Step 'self-signed runner certificate' { & (Join-Path $PSScriptRoot 'windows-certificate.ps1') }
  }
  Step 'install Rust 1.96.0' { rustup toolchain install 1.96.0 --profile minimal --component rustfmt --component clippy }
  # Same gates as xtask ci, separately timed without exposing their output.
  Step 'quality format' { cargo +1.96.0 fmt --all -- --check }
  Step 'clippy' { cargo +1.96.0 clippy --workspace --locked --all-targets -- -D warnings }
  Step 'workspace tests' { cargo +1.96.0 test --workspace --locked --all-targets }
  Step 'asset attribution' { cargo +1.96.0 xtask assets }
  Step 'dependency layers' { cargo +1.96.0 xtask layers }
  Step 'product identity' { python scripts/check-identity.py }
  Step 'Chinese message coverage' { python scripts/check-translations.py }
  Step 'identity scanner regression' { python scripts/test-check-identity.py }
  Step 'icon validator dependency' { python -m pip install pillow==12.3.0 }
  Step 'approved application icon frames' { python scripts/test-app-icons.py }
  # The private source remote is intentionally absent in an Actions checkout.
  if ($IsWindows) {
    Step 'install WiX' { dotnet tool install --global wix --version 5.0.2 }
    Step 'WiX UI extension' { wix extension add -g WixToolset.UI.wixext/5.0.2 }
    # GITHUB_ENV is read by later steps; this call also sets current process values.
    $env:WINDOWS_CERTIFICATE_PASSWORD = $env:LEESCAD_WINDOWS_PFX_PASSWORD
    Step 'Windows release compile' { & packaging/windows/package.ps1 -Arch x64 -BuildOnly }
    Step 'Windows package and signing' { & packaging/windows/package.ps1 -Arch x64 -SkipBuild }
    Step 'Windows document associations' {
      $packages = @(Get-ChildItem -LiteralPath $env:DIST -Filter '*-windows-x64.msi' -File)
      if ($packages.Count -ne 1) { throw 'Expected exactly one Windows MSI for association validation' }
      $exe = Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc/release/lees-cad.exe'
      & (Join-Path $PSScriptRoot 'test-windows-association-guards.ps1') -Msi $packages[0].FullName -Exe $exe `
        -Fixtures (Join-Path $env:RUNNER_TEMP "association-guards-$([guid]::NewGuid().ToString('N'))")
    }
    Step 'Windows shared font MSI contract' {
      $packages = @(Get-ChildItem -LiteralPath $env:DIST -Filter '*-windows-x64.msi' -File)
      if ($packages.Count -ne 1) { throw 'Expected exactly one Windows MSI for font validation' }
      & (Join-Path $PSScriptRoot 'test-windows-fonts.ps1') -Msi $packages[0].FullName -Source $Source
    }
    Step 'Windows native artifact identity' { & (Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc/release/lees-cad.exe') --verify-update-artifact $env:DIST }
  } else {
    $env:MACOS_SIGN_IDENTITY = '-'
    # The runner's python and python3 may refer to different installations.
    $installerPython = Join-Path $env:RUNNER_TEMP 'cad-installer-python'
    Step 'macOS installer Python environment' { python -m venv $installerPython }
    $env:PATH = (Join-Path $installerPython 'bin') + [IO.Path]::PathSeparator + $env:PATH
    Step 'macOS installer layout dependencies' { python3 -m pip install --require-hashes --only-binary=:all: -r packaging/macos/dmg/requirements.txt }
    Step 'macOS release compile' { bash packaging/macos/package.sh --arch aarch64 --build-only }
    Step 'macOS package and signing' { bash packaging/macos/package.sh --arch aarch64 --skip-build }
    Step 'macOS native artifact identity' { & (Join-Path $env:CARGO_TARGET_DIR 'aarch64-apple-darwin/release/lees-cad') --verify-update-artifact $env:DIST }
  }
} finally { Pop-Location }
