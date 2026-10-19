# Corrupt isolated MSI copies, never install them or change the host registry.
param([Parameter(Mandatory)][string]$Msi, [Parameter(Mandatory)][string]$Exe,
      [Parameter(Mandatory)][string]$Fixtures)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $Fixtures) { throw 'Fixture directory already exists' }
New-Item -ItemType Directory -Path $Fixtures | Out-Null
$validator = Join-Path $PSScriptRoot 'test-windows-associations.ps1'
& $validator -Msi $Msi -Exe $Exe
$installer = New-Object -ComObject WindowsInstaller.Installer
$cases = @(
    @{ Name='application-command'; Expected='Missing or invalid application open command'; Sql="DELETE FROM ``Registry`` WHERE ``Key`` = 'Software\Classes\Applications\lees-cad.exe\shell\open\command'" },
    @{ Name='app-path'; Expected='Missing or invalid application path'; Sql="DELETE FROM ``Registry`` WHERE ``Key`` = 'Software\Microsoft\Windows\CurrentVersion\App Paths\lees-cad.exe'" },
    @{ Name='wrong-root'; Expected='DWG association, icon or quoted open command is invalid'; Sql="UPDATE ``Registry`` SET ``Root`` = 1 WHERE ``Key`` = 'Software\Classes\.dwg\OpenWithProgids'" },
    @{ Name='wrong-openwith-value'; Expected='DXF association, icon or quoted open command is invalid'; Sql="UPDATE ``Registry`` SET ``Value`` = 'invalid' WHERE ``Key`` = 'Software\Classes\.dxf\OpenWithProgids'" }
)
foreach ($case in $cases) {
    $copy = Join-Path $Fixtures ($case.Name + '.msi')
    Copy-Item -LiteralPath $Msi -Destination $copy
    $database = $installer.OpenDatabase($copy, 1)
    $view = $database.OpenView($case.Sql)
    $view.Execute()
    $view.Close()
    $database.Commit()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($view)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($database)
    $rejected = $false
    try { & $validator -Msi $copy -Exe $Exe | Out-Null } catch {
        if ($_.Exception.Message -cne $case.Expected) { throw }
        $rejected = $true
        Write-Output $_.Exception.Message
    }
    if (-not $rejected) { throw "Association guard accepted corrupted MSI: $($case.Name)" }
    Write-Output "Rejected corrupted MSI: $($case.Name)"
}
