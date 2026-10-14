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
function Check-Failure([scriptblock]$Work, [string]$Code) {
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
    $summary = $output[1] | ConvertFrom-Json
    if ($summary.phase -ne 'synthetic failure') { throw 'Failure phase missing' }
    if ($Code -and $Code -notin $summary.compilerCodes) { throw 'Diagnostic code missing' }
}
Check-Failure { throw 'PRIVATE_SOURCE_MARKER' }
Check-Failure {
    Write-Output 'template.wxs(82) : error WIX0367: PRIVATE_SOURCE_MARKER'
    & pwsh -NoProfile -NonInteractive -Command 'exit 7'
} 'WIX0367'
$global:LASTEXITCODE = 0
Step 'synthetic success' { Write-Output 'PRIVATE_SOURCE_MARKER' } | Out-Null
Write-Output 'Build error regression passed: terminating errors, native exit codes, WiX diagnostics and success output stay isolated'
