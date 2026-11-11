[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PackageDirectory,
    [Parameter(Mandatory=$true)][string]$FixtureDirectory
)
$ErrorActionPreference = 'Stop'
$package = (Resolve-Path -LiteralPath $PackageDirectory).Path
$fixture = [IO.Path]::GetFullPath($FixtureDirectory)
if ($fixture.StartsWith('\\') -or -not [IO.Path]::IsPathRooted($fixture)) { throw 'Use an ordinary local fixture path.' }
$current = $fixture
while ($current) {
    if (Test-Path -LiteralPath $current) {
        if (([long](Get-Item -Force -LiteralPath $current).Attributes -band 0x441400) -ne 0) { throw 'Link, offline and cloud-placeholder fixture paths are refused.' }
    }
    $current = [IO.Path]::GetDirectoryName($current)
}
$outerCheckout = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
foreach ($protectedRoot in @($outerCheckout,'C:\Users\Jude\Documents\MSI-Project-Library','C:\Users\Jude\AppData\Local\ProjectLibrary')) {
    $prefix = [IO.Path]::GetFullPath($protectedRoot).TrimEnd('\') + '\'
    if (($fixture.TrimEnd('\') + '\').StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Fixtures must be outside the checkout, installed kit and managed cache.' }
}
if (Test-Path -LiteralPath $fixture) { throw 'Use a new fixture directory; existing test evidence is preserved.' }
New-Item -ItemType Directory -Path $fixture | Out-Null
$manifest = Get-Content -Raw -LiteralPath (Join-Path $package 'DESKTOP-CHECKSUMS.json') | ConvertFrom-Json
if ($manifest.format -cne 'the-stats-desktop-package-v1') { throw 'Unsupported desktop package manifest.' }
$expectedFiles = @('TheStats.exe','TheStats.exe.config','TheStats.ico','couch-sticker-original.png','Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll','WebView2-LICENSE.txt','WebView2-NOTICE.txt')
$actualFiles = @($manifest.files.PSObject.Properties.Name)
if ($actualFiles.Count -ne $expectedFiles.Count -or @(Compare-Object $expectedFiles $actualFiles).Count -ne 0) { throw 'Desktop package manifest membership differs.' }
foreach ($file in $manifest.files.PSObject.Properties) {
    if ($file.Name -match '[/\\:]' -or (Get-FileHash -LiteralPath (Join-Path $package $file.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value) { throw 'Desktop package checksum verification failed.' }
}
$exe = Join-Path $package 'TheStats.exe'
$self = Join-Path $fixture 'self-test'
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test',('"' + $self + '"')) -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(30000)) { throw 'Self-tests timed out; the fixture process was preserved for review.' }
if ($process.ExitCode -ne 0) { throw "Self-tests exited with $($process.ExitCode)." }
$selfReport = Get-Content -Raw -LiteralPath (Join-Path $self 'self-test.json') | ConvertFrom-Json
if (-not $selfReport.success -or -not $selfReport.syntheticOnly) { throw 'Desktop refusal checks failed.' }
$preview = Join-Path $fixture 'preview'
$process = Start-Process -FilePath $exe -ArgumentList @('--preview','--fixture-directory',('"' + $preview + '"'),'--smoke-test') -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(45000)) { throw 'Native WebView2 checks timed out; the preview process was preserved for review.' }
if ($process.ExitCode -ne 0) { throw "Native preview exited with $($process.ExitCode)." }
$previewReport = Get-Content -Raw -LiteralPath (Join-Path $preview 'smoke.json') | ConvertFrom-Json
if (-not $previewReport.success -or -not $previewReport.syntheticOnly) { throw 'Native desktop preview checks failed.' }
$result = [ordered]@{ format='the-stats-desktop-validation-v1'; createdUtc=[DateTime]::UtcNow.ToString('o'); success=$true; syntheticOnly=$true; fixtureDirectory=$fixture; packageFilesVerified=@($manifest.files.PSObject.Properties).Count; refusalChecks=@($selfReport.checks.PSObject.Properties).Count; nativeChecks=@($previewReport.checks.PSObject.Properties).Count; liveLibraryOpened=$false; existingBackendStartedOrStopped=$false }
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $fixture 'validation.json') -Encoding utf8
$result | ConvertTo-Json
