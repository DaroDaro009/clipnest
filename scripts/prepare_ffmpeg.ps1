$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$binaryDir = Join-Path $projectRoot 'src-tauri\binaries'
$cacheDir = Join-Path $projectRoot '.build-tools\ffmpeg'
$archivePath = Join-Path $cacheDir 'ffmpeg-n8.1.3-win64-lgpl-8.1.zip'
$sourceUrl = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-09-23-14-55/ffmpeg-n8.1.3-win64-lgpl-8.1.zip'
$expectedHash = '3aacb540e6c0aaef82a063fc6ddb5b55aa4425e5d95780c0c04b5a528667020a'

New-Item -ItemType Directory -Force -Path $cacheDir, $binaryDir | Out-Null
if (-not (Test-Path -LiteralPath $archivePath)) {
    Invoke-WebRequest -Uri $sourceUrl -OutFile $archivePath
}
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "FFmpeg archive checksum mismatch: $actualHash"
}

Add-Type -AssemblyName System.IO.Compression
$archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($fileName in @('ffmpeg.exe', 'ffprobe.exe')) {
        $entry = $archive.Entries | Where-Object { $_.FullName -match "/bin/$fileName$" } | Select-Object -First 1
        if (-not $entry) { throw "The FFmpeg archive is missing $fileName." }
        $target = Join-Path $binaryDir $fileName
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        $versionOutput = & $target -version
        if ($LASTEXITCODE -ne 0) { throw "Bundled $fileName did not start." }
        Write-Output $versionOutput[0]
    }
    $license = $archive.Entries | Where-Object { $_.FullName -match '/LICENSE.txt$' } | Select-Object -First 1
    if (-not $license) { throw 'The FFmpeg archive is missing its license.' }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($license, (Join-Path $binaryDir 'ffmpeg-LICENSE.txt'), $true)
}
finally {
    $archive.Dispose()
}
