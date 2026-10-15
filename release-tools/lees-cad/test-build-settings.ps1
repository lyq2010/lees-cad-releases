$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build-settings.ps1')
foreach ($case in @(@($true, 4, 4, 4), @($true, 2, 4, 2), @($true, 4, 2, 2),
                     @($false, 4, 3, 2), @($true, 4, 1, 1))) {
    if ((Get-BuildJobs -WindowsHost $case[0] -WindowsJobs $case[1] -LogicalCpus $case[2]) -ne $case[3]) {
        throw 'Compiler job budget differs'
    }
}
Write-Output 'Compiler budgets passed: Windows two/four, CPU cap, macOS unchanged'
