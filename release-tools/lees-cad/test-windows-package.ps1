# Exercise the real packaging selection with synthetic PE files and WiX/signing substitutes.
param([Parameter(Mandatory)][string]$Source, [string]$Fixtures)
$ErrorActionPreference = 'Stop'
if (-not $Fixtures) { $Fixtures = Join-Path $env:RUNNER_TEMP "cad-package-selection-$([guid]::NewGuid().ToString('N'))" }
if (Test-Path -LiteralPath $Fixtures) { throw 'Fixture directory already exists' }
$variables = @('DIST', 'CARGO_TARGET_DIR', 'LEES_CAD_VERSION', 'LEES_CAD_BUILD_SHA', 'LEES_CAD_BUILD_DATE',
    'LEESCAD_UPDATER_PRIVATE_KEY', 'WINDOWS_CERTIFICATE', 'WINDOWS_PFX_PATH', 'AZURE_CLIENT_SECRET')
$previous = @{}
foreach ($name in $variables) { $previous[$name] = [Environment]::GetEnvironmentVariable($name) }
$signArguments = [Collections.Generic.List[string]]::new()
function wix {
    $outputIndex = [Array]::IndexOf($args, '-o')
    if ($outputIndex -lt 0) { throw 'Missing MSI output argument' }
    [IO.File]::WriteAllText($args[$outputIndex + 1], 'synthetic MSI fixture')
    $global:LASTEXITCODE = 0
}
function node {
    $signArguments.Clear()
    foreach ($part in $args) { $signArguments.Add([string]$part) }
    $global:LASTEXITCODE = 0
}
try {
    $env:DIST = Join-Path $Fixtures 'dist'
    $env:CARGO_TARGET_DIR = Join-Path $Fixtures 'target'
    $env:LEES_CAD_VERSION = '0.1.1'
    $env:LEES_CAD_BUILD_SHA = '1111111111111111111111111111111111111111'
    $env:LEES_CAD_BUILD_DATE = '2026-10-15'
    $env:LEESCAD_UPDATER_PRIVATE_KEY = 'fixture; intercepted by signing substitute'
    $env:WINDOWS_CERTIFICATE = $null
    $env:WINDOWS_PFX_PATH = $null
    $env:AZURE_CLIENT_SECRET = $null
    # ARM64 headers select the existing cross-build branch without executing synthetic binaries.
    $bin = Join-Path $env:CARGO_TARGET_DIR 'aarch64-pc-windows-msvc/release'
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    foreach ($entry in @(@('lees-cad.exe', 2), @('lees-cad-cli.exe', 3))) {
        $bytes = [byte[]]::new(512)
        $bytes[0] = 0x4d; $bytes[1] = 0x5a
        [BitConverter]::GetBytes([int]0x80).CopyTo($bytes, 0x3c)
        $bytes[0x80] = 0x50; $bytes[0x81] = 0x45
        [BitConverter]::GetBytes([uint16]0xaa64).CopyTo($bytes, 0x84)
        [BitConverter]::GetBytes([uint16]$entry[1]).CopyTo($bytes, 0xdc)
        [IO.File]::WriteAllBytes((Join-Path $bin $entry[0]), $bytes)
    }
    & (Join-Path $Source 'packaging/windows/package.ps1') -Arch arm64 -SkipBuild | Out-Null
    $msi = 'lees-cad-0.1.1-windows-arm64.msi'
    $files = @(Get-ChildItem -LiteralPath $env:DIST -File)
    if ($files.Count -ne 1 -or $files[0].Name -ne $msi) { throw 'Windows packaging must produce only MSI' }
    if ($signArguments.Count -ne 6 -or $signArguments[5] -ne $msi) {
        throw 'Only the MSI may be passed to updater signing'
    }
    Write-Output 'Windows MSI-only package selection and signing arguments passed (synthetic fixtures)'
} finally {
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name, $previous[$name]) }
}
