# Read the actual compiled MSI; never install it or change the host PATH.
param([Parameter(Mandatory)][string]$Msi, [Parameter(Mandatory)][string]$Source)
$ErrorActionPreference = 'Stop'
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase((Resolve-Path -LiteralPath $Msi).Path, 0)
$view = $database.OpenView('SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`')
$view.Execute()
$directories = @{}
while ($row = $view.Fetch()) { $directories[$row.StringData(1)] = @($row.StringData(2), $row.StringData(3)) }
$view.Close()
if ($directories['CadFonts'][0] -cne 'INSTALLFOLDER' -or $directories['CadFonts'][1] -cne 'fonts' -or
    $directories['CadShxFonts'][0] -cne 'CadFonts' -or $directories['CadShxFonts'][1] -cne 'shx') {
    throw 'MSI must install exactly one shared product font directory'
}
$expected = @{}
$fontRoot = Join-Path $Source 'assets/fonts'
Get-ChildItem -LiteralPath $fontRoot -Recurse -File | Where-Object Extension -In '.ttf', '.gz', '.shx' | ForEach-Object {
    $name = [IO.Path]::GetRelativePath($fontRoot, $_.FullName).Replace('\', '/')
    $expected[$name] = $_.Length
}
$view = $database.OpenView('SELECT `File`.`FileName`, `File`.`FileSize`, `Component`.`Directory_` FROM `File`, `Component` WHERE `File`.`Component_` = `Component`.`Component`')
$view.Execute()
$found = @{}
while ($row = $view.Fetch()) {
    $directory = $row.StringData(3)
    if ($directory -in 'CadFonts', 'CadShxFonts') {
        $name = ($row.StringData(1) -split '\|')[-1]
        if ($directory -eq 'CadShxFonts') { $name = 'shx/' + $name }
        if (-not $expected.ContainsKey($name) -or $expected[$name] -ne $row.IntegerData(2) -or $found.ContainsKey($name)) {
            throw "Invalid or duplicate shared font entry: $name"
        }
        $found[$name] = $true
    }
}
$view.Close()
if ($expected.Count -ne 80 -or $found.Count -ne 80) { throw 'MSI must include all 80 fonts exactly once' }
Write-Output 'Compiled MSI includes one complete shared set of all 80 CAD fonts'
