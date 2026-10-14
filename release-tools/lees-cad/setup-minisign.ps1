$ErrorActionPreference = 'Stop'
if ($IsWindows) {
  $asset = 'minisign-0.12-win64.zip'
  $hash = '37b600344e20c19314b2e82813db2bfdcc408b77b876f7727889dbd46d539479'
  $name = 'minisign.exe'
} else {
  $asset = 'minisign-0.12-macos.zip'
  $hash = '89000b19535765f9cffc65a65d64a820f433ef6db8020667f7570e06bf6aac63'
  $name = 'minisign'
}
$root = Join-Path $env:RUNNER_TEMP "minisign-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $root | Out-Null
$zip = Join-Path $root $asset
Invoke-WebRequest -Uri "https://github.com/jedisct1/minisign/releases/download/0.12/$asset" -OutFile $zip
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) { throw 'Minisign tool digest mismatch' }
Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $root 'tool')
$tool = Get-ChildItem -Path (Join-Path $root 'tool') -Recurse -File | Where-Object Name -eq $name | Select-Object -First 1
if (!$tool) { throw 'Minisign tool missing' }
if (!$IsWindows) { chmod +x $tool.FullName }
$env:PATH = $tool.DirectoryName + [IO.Path]::PathSeparator + $env:PATH
$tool.DirectoryName >> $env:GITHUB_PATH
& $tool.FullName -v
if ($LASTEXITCODE -ne 0) { throw 'Minisign tool cannot execute' }
