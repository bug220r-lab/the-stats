[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DependencyRoot,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$LogoPath = (Join-Path $PSScriptRoot '..\assets\branding\couch-sticker-original.png')
)
$ErrorActionPreference = 'Stop'
$dependency = (Resolve-Path -LiteralPath $DependencyRoot).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
$logo = (Resolve-Path -LiteralPath $LogoPath).Path
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$version = '1.0.4314.35'
$archiveSha = '90778deb1b77e36292828b4b5833c9255c27533f40e0ddd55891ae718944edc4'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '.NET Framework 4.8 and its x64 C# compiler are required.' }
$archive = Join-Path (Split-Path -Parent $dependency) 'webview2.nupkg'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -cne $archiveSha) { throw 'The pinned official WebView2 SDK archive is missing or changed.' }
$spec = [xml](Get-Content -LiteralPath (Join-Path $dependency 'Microsoft.Web.WebView2.nuspec') -Raw)
if ($spec.package.metadata.version -cne $version) { throw 'Unexpected WebView2 SDK version.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
$members = [ordered]@{
    'lib/net462/Microsoft.Web.WebView2.Core.dll' = 'Microsoft.Web.WebView2.Core.dll'
    'lib/net462/Microsoft.Web.WebView2.WinForms.dll' = 'Microsoft.Web.WebView2.WinForms.dll'
    'runtimes/win-x64/native/WebView2Loader.dll' = 'WebView2Loader.dll'
    'LICENSE.txt' = 'WebView2-LICENSE.txt'
    'NOTICE.txt' = 'WebView2-NOTICE.txt'
}
try {
    foreach ($relative in $members.Keys) {
        $entry = $zip.GetEntry($relative)
        if ($null -eq $entry) { throw "Required SDK member is missing: $relative" }
        $stream = $entry.Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $expected = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
        if ((Get-FileHash -LiteralPath (Join-Path $dependency $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) { throw "Extracted SDK member changed: $relative" }
    }
} finally { $zip.Dispose() }
if (Test-Path -LiteralPath $output) {
    if (@(Get-ChildItem -LiteralPath $output -Force).Count -ne 0) { throw 'Use a new empty output directory; existing builds are preserved.' }
} else { New-Item -ItemType Directory -Path $output | Out-Null }

Add-Type -AssemblyName System.Drawing
$iconPath = Join-Path $output 'TheStats.ico'
$bitmap = [Drawing.Bitmap]::new(64,64)
$drawing = [Drawing.Graphics]::FromImage($bitmap)
$pen = [Drawing.Pen]::new([Drawing.Color]::White,3)
$font = [Drawing.Font]::new('Consolas',32,[Drawing.FontStyle]::Bold,[Drawing.GraphicsUnit]::Pixel)
try {
    $drawing.Clear([Drawing.Color]::Black)
    $drawing.DrawLine($pen,9,12,9,52); $drawing.DrawLine($pen,9,12,18,12); $drawing.DrawLine($pen,9,52,18,52)
    $drawing.DrawLine($pen,55,12,55,52); $drawing.DrawLine($pen,46,12,55,12); $drawing.DrawLine($pen,46,52,55,52)
    $drawing.DrawString('S',$font,[Drawing.Brushes]::White,20,11)
    $icon = [Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = [IO.File]::Create($iconPath)
    try { $icon.Save($stream) } finally { $stream.Dispose(); $icon.Dispose() }
} finally { $font.Dispose(); $pen.Dispose(); $drawing.Dispose(); $bitmap.Dispose() }

$core = Join-Path $dependency 'lib\net462\Microsoft.Web.WebView2.Core.dll'
$forms = Join-Path $dependency 'lib\net462\Microsoft.Web.WebView2.WinForms.dll'
$arguments = @('/nologo','/codepage:65001','/target:winexe','/platform:x64','/optimize+','/warn:4',('/win32icon:' + $iconPath),('/out:' + (Join-Path $output 'TheStats.exe')),('/reference:' + $core),('/reference:' + $forms),'/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Net.Http.dll','/reference:System.Web.Extensions.dll',(Join-Path $PSScriptRoot 'TheStats.cs'))
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'The Stats desktop compilation failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'TheStats.exe.config') -Destination $output
Copy-Item -LiteralPath $logo -Destination (Join-Path $output 'couch-sticker-original.png')
foreach ($relative in $members.Keys) { Copy-Item -LiteralPath (Join-Path $dependency $relative) -Destination (Join-Path $output $members[$relative]) }

$files = [ordered]@{}
foreach ($name in @('TheStats.exe','TheStats.exe.config','TheStats.ico','couch-sticker-original.png') + @($members.Values)) {
    $files[$name] = (Get-FileHash -LiteralPath (Join-Path $output $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$appRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $appRoot
$head = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Build provenance requires the existing Git checkout.' }
$gitState = @(& git -C $repoRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) { throw 'Could not record source working-tree state.' }
$sourceFiles = [ordered]@{}
foreach ($name in @('TheStats.cs','Build-Desktop.ps1','Test-Desktop.ps1','TheStats.exe.config','README.md')) {
    $sourceFiles['current-app/desktop/' + $name] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = [ordered]@{
    format = 'the-stats-desktop-package-v1'
    createdUtc = [DateTime]::UtcNow.ToString('o')
    sdkVersion = $version
    sdkArchiveSha256 = $archiveSha
    baseGitCommit = $head
    dirtySource = ($gitState.Count -ne 0)
    sourceWorkingTree = $gitState
    sourceFiles = $sourceFiles
    originalLogoSha256 = (Get-FileHash -LiteralPath $logo -Algorithm SHA256).Hash.ToLowerInvariant()
    compiler = $compiler
    files = $files
}
[IO.File]::WriteAllText((Join-Path $output 'DESKTOP-CHECKSUMS.json'),($manifest | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{ Status='THE_STATS_DESKTOP_BUILT'; OutputDirectory=$output; Files=$files.Count; SdkVersion=$version; BaseGitCommit=$head; DirtySource=$manifest.dirtySource } | ConvertTo-Json
