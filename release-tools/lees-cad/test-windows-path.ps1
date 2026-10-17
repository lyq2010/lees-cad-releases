# Inspect a compiled MSI without installing it or changing the host PATH.
param([Parameter(Mandatory)][string]$Msi)
$ErrorActionPreference = 'Stop'
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase((Resolve-Path -LiteralPath $Msi).Path, 0)
try {
    $view = $database.OpenView('SELECT `Name`, `Value`, `Component_` FROM `Environment` WHERE `Environment` = ''LeesCadCliPath''')
} catch {
    throw 'MSI has no readable Environment table for CLI PATH registration'
}
$view.Execute()
$row = $view.Fetch()
if (-not $row) { throw 'MSI does not register the CLI in PATH' }
if ($row.StringData(1) -notmatch '^[-=*]{3}PATH$' -or
    $row.StringData(1) -notlike '*=*' -or $row.StringData(1) -notlike '*-*' -or
    -not $row.StringData(1).Contains('*')) {
    throw 'CLI PATH must be per-machine, set on install and removed on uninstall'
}
if ($row.StringData(2) -cne '[~];[INSTALLFOLDER]' -or $row.StringData(3) -cne 'LeesCadCli') {
    throw 'CLI PATH must append only the installation directory and belong to the CLI component'
}
if ($view.Fetch()) { throw 'Duplicate CLI PATH registration' }
$view.Close()
foreach ($action in 'WriteEnvironmentStrings', 'RemoveEnvironmentStrings') {
    $view = $database.OpenView("SELECT ``Action`` FROM ``InstallExecuteSequence`` WHERE ``Action`` = '$action'")
    $view.Execute()
    if (-not $view.Fetch()) { throw "MSI is missing $action" }
    $view.Close()
}
Write-Output 'Compiled MSI PATH append, scope, uninstall ownership and standard actions passed'
