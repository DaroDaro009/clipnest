$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$binaryDir = Join-Path $projectRoot 'src-tauri\binaries'
$nodeCommand = Get-Command node.exe -ErrorAction Stop
$nodeSource = $nodeCommand.Source
$licenseSource = Join-Path (Split-Path $nodeSource) 'LICENSE'
if (-not (Test-Path -LiteralPath $licenseSource)) {
    throw "The Node.js license was not found beside $nodeSource."
}

New-Item -ItemType Directory -Force -Path $binaryDir | Out-Null
$nodeTarget = Join-Path $binaryDir 'node.exe'
Copy-Item -LiteralPath $nodeSource -Destination $nodeTarget -Force
Copy-Item -LiteralPath $licenseSource -Destination (Join-Path $binaryDir 'node-LICENSE') -Force

$version = & $nodeTarget --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v(2[2-9]|[3-9][0-9])\.') {
    throw "Bundled Node.js did not start or is too old: $version"
}
Write-Output "Bundled Node.js $version"
