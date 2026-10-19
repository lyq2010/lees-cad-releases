# Validate actual PE resources and MSI tables without installing or changing associations.
param([Parameter(Mandatory)][string]$Msi, [Parameter(Mandatory)][string]$Exe)
$ErrorActionPreference = 'Stop'
$version = [Diagnostics.FileVersionInfo]::GetVersionInfo((Resolve-Path -LiteralPath $Exe).Path)
if ($version.ProductName -cne "Lee's CAD" -or $version.FileDescription -cne "Lee's CAD") {
    throw 'PE product and Open With display names must be exactly Lee''s CAD'
}
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase((Resolve-Path -LiteralPath $Msi).Path, 0)
$view = $database.OpenView('SELECT `Root`, `Key`, `Name`, `Value` FROM `Registry`')
$view.Execute()
$registry = @{}
while ($row = $view.Fetch()) {
    $key = $row.StringData(2)
    $name = $row.StringData(3)
    $root = $row.IntegerData(1)
    $registry["$root|$key|$name"] = $row.StringData(4)
    if ($key -match 'UserChoice' -or $key -match 'Software\\Classes\\\.(dwg|dxf)$') {
        throw 'The installer must offer Open With without taking over a default association'
    }
}
$view.Close()
$application = 'Software\Classes\Applications\lees-cad.exe'
if ($registry["2|$application|FriendlyAppName"] -cne "Lee's CAD") { throw 'Missing friendly application name' }
if ($registry["2|$application\shell\open\command|"] -cne '"[#LeesCadExe]" "%1"') {
    throw 'Missing or invalid application open command'
}
if ($registry['2|Software\Microsoft\Windows\CurrentVersion\App Paths\lees-cad.exe|'] -cne '[#LeesCadExe]') {
    throw 'Missing or invalid application path'
}
foreach ($type in 'DWG', 'DXF') {
    $extension = $type.ToLowerInvariant()
    $program = "Lee's CAD.$type"
    $key = "Software\Classes\$program"
    $iconId = if ($type -eq 'DWG') { 'DwgDocumentIcon' } else { 'DxfDocumentIcon' }
    $openWith = "2|Software\Classes\.$extension\OpenWithProgids|$program"
    if (-not $registry.ContainsKey($openWith) -or $registry[$openWith] -cne '' -or
        $registry["2|$key\shell\open|FriendlyAppName"] -cne "Lee's CAD" -or
        $registry["2|$key\DefaultIcon|"] -cne ('"[#' + $iconId + ']",0') -or
        $registry["2|$key\shell\open\command|"] -cne '"[#LeesCadExe]" "%1"') {
        throw "$type association, icon or quoted open command is invalid"
    }
    $view = $database.OpenView("SELECT ``FileName`` FROM ``File`` WHERE ``File`` = '$iconId'")
    $view.Execute()
    $row = $view.Fetch()
    if (-not $row -or $row.StringData(1).Split('|')[-1] -cne "lees-cad-$extension.ico") {
        throw "MSI does not include the $type document icon"
    }
    $view.Close()
}
Write-Output 'Actual PE display names and compiled MSI DWG/DXF icons, commands and default-app protection passed'
