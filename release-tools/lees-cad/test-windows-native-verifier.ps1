# Release desktop executables use the GUI subsystem. A pipeline is required to wait for
# termination and capture their actual exit status in PowerShell; no package is installed.
param([Parameter(Mandatory)][string]$Exe, [Parameter(Mandatory)][string]$Artifacts)
$ErrorActionPreference = 'Stop'
$Exe = (Resolve-Path -LiteralPath $Exe).Path
$Artifacts = (Resolve-Path -LiteralPath $Artifacts).Path
$missing = Join-Path $env:TEMP "cad-native-verifier-missing-$([guid]::NewGuid().ToString('N'))"
if (Test-Path -LiteralPath $missing) { throw 'Negative verifier input must not exist' }
& $Exe --verify-update-artifact $missing | Out-Null
if ($LASTEXITCODE -eq 0) { throw 'Native verifier accepted missing artifacts or did not return a failure exit code' }
& $Exe --verify-update-artifact $Artifacts | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Native package identity/signature verification failed' }
Write-Output 'Native GUI verifier waits for exit: missing input rejected and real artifacts accepted'
