# Exercise the actual public Step wrapper without running private builds.
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'build.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Build script syntax failed' }
$step = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Step' }, $false)
if (-not $step) { throw 'Step wrapper missing' }
. ([scriptblock]::Create($step.Extent.Text))
$root = Join-Path ([IO.Path]::GetTempPath()) "lees-cad-error-test-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $root | Out-Null
$log = Join-Path $root 'private-build.log'
function Check-Failure([scriptblock]$Work, [string]$Code, [string]$Location, [int]$NativeCode = 0) {
    $output = [Collections.Generic.List[string]]::new()
    $global:LASTEXITCODE = 0
    try {
        Step 'synthetic failure' $Work | ForEach-Object { $output.Add($_.ToString()) }
        throw 'Expected failure missing'
    } catch {
        if ($_.Exception.Message -ne 'synthetic failure failed; code and private build log remain only on this runner') { throw }
    }
    $text = $output -join "`n"
    if ($text.Contains('PRIVATE_SOURCE_MARKER')) { throw 'Private failure details escaped' }
    $records = @($output | Where-Object { $_.StartsWith('{') } | ConvertFrom-Json)
    $summary = $records | Where-Object { $_.PSObject.Properties.Name -contains 'compilerCodes' }
    if ($summary.phase -ne 'synthetic failure') { throw 'Failure phase missing' }
    if ($Code -and $Code -notin $summary.compilerCodes) { throw 'Diagnostic code missing' }
    if ($Location -and $Location -notin $summary.locations) { throw 'Diagnostic location missing' }
    if ($NativeCode -and $summary.nativeExitCode -ne $NativeCode) { throw 'Actual native exit code missing' }
    $timing = $records | Where-Object { $_.PSObject.Properties.Name -contains 'elapsedSeconds' }
    if ($timing.result -ne 'failed' -or $timing.elapsedSeconds -lt 0) { throw 'Failure timing missing' }
}
Check-Failure { throw 'PRIVATE_SOURCE_MARKER' }
Check-Failure {
    Write-Output 'template.wxs(82) : error WIX0367: PRIVATE_SOURCE_MARKER'
    & pwsh -NoProfile -NonInteractive -Command 'exit 7'
} 'WIX0367'
Check-Failure {
    Write-Output "$([char]27)[31mDiff in D:\a\release\private-source\crates\doc\src\entity.rs:91:$([char]27)[0m"
    Write-Output 'PRIVATE_SOURCE_MARKER'
    & pwsh -NoProfile -NonInteractive -Command 'exit 1'
} '' 'crates/doc/src/entity.rs:91:1'
$global:LASTEXITCODE = 0
& {
    $LASTEXITCODE = 1
    $global:LASTEXITCODE = 9
    $passed = @(Step 'native success with stale caller exit' { & pwsh -NoProfile -NonInteractive -Command 'exit 0' })
    if (($passed | Where-Object { $_.StartsWith('{') } | ConvertFrom-Json).result -ne 'passed') { throw 'Successful native command was rejected' }
    $global:LASTEXITCODE = 9
    $passed = @(Step 'PowerShell success with stale prior native exit' { Write-Output 'PRIVATE_SOURCE_MARKER' })
    if (($passed | Where-Object { $_.StartsWith('{') } | ConvertFrom-Json).result -ne 'passed') { throw 'Successful PowerShell step was rejected' }
    Check-Failure { & pwsh -NoProfile -NonInteractive -Command 'exit 7' } '' '' 7
    $scriptExit = Join-Path $root 'exit7.ps1'
    [IO.File]::WriteAllText($scriptExit, 'exit 7')
    Check-Failure { & $scriptExit } '' '' 7
}
$global:LASTEXITCODE = 0
$success = @(Step 'synthetic success' { Write-Output 'PRIVATE_SOURCE_MARKER' })
if (($success -join '').Contains('PRIVATE_SOURCE_MARKER')) { throw 'Success details escaped' }
$timing = $success | Where-Object { $_.StartsWith('{') } | ConvertFrom-Json
if ($timing.result -ne 'passed' -or $timing.elapsedSeconds -lt 0) { throw 'Success timing missing' }
Write-Output 'Build error regression passed: terminating errors, native exit codes, WiX diagnostics and success output stay isolated'
