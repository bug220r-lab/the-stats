param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$projectPath = [System.IO.Path]::GetFullPath($ProjectRoot)
$venvPath = Join-Path $projectPath '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$lockPath = Join-Path $projectPath 'requirements.lock.txt'

function Get-CompatiblePython {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        $result = & $Executable @PrefixArguments -c 'import json, struct, sys; print(json.dumps(dict(major=sys.version_info.major, minor=sys.version_info.minor, bits=struct.calcsize(chr(80)) * 8, executable=sys.executable, version=sys.version.split()[0])))' 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $info = ($result -join "`n") | ConvertFrom-Json
        if ($info.major -eq 3 -and $info.minor -eq 12 -and $info.bits -eq 64) {
            return $info
        }
    }
    catch { return $null }
    return $null
}

try {
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        throw 'requirements.lock.txt is missing. Restore the complete application before setup.'
    }

    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $pythonInfo = Get-CompatiblePython -Executable $venvPython
        if ($null -eq $pythonInfo) {
            throw 'The existing .venv does not run 64-bit Python 3.12. Keep a copy if needed, rename .venv, and rerun setup with Python 3.12 installed.'
        }
        Write-Host ('Using existing project environment: Python ' + $pythonInfo.version)
    }
    else {
        if (Test-Path -LiteralPath $venvPath) {
            throw 'An incomplete .venv folder already exists. Rename it and rerun setup. Setup will not delete an existing environment.'
        }
        $pythonInfo = $null
        if ($env:STATS_PYTHON) {
            if (-not (Test-Path -LiteralPath $env:STATS_PYTHON -PathType Leaf)) {
                throw 'STATS_PYTHON must be the complete path to an existing Python 3.12 executable.'
            }
            $pythonInfo = Get-CompatiblePython -Executable $env:STATS_PYTHON
            if ($null -eq $pythonInfo) {
                throw 'STATS_PYTHON does not run compatible 64-bit Python 3.12.'
            }
        }
        if ($null -eq $pythonInfo) {
            $pyCommand = Get-Command py.exe -ErrorAction SilentlyContinue
            if ($pyCommand) {
                $pythonInfo = Get-CompatiblePython -Executable $pyCommand.Source -PrefixArguments @('-3.12')
            }
        }
        if ($null -eq $pythonInfo) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
            # The WindowsApps alias can open the Microsoft Store; it is not an interpreter.
            if ($pythonCommand -and $pythonCommand.Source -notmatch '\\WindowsApps\\') {
                $pythonInfo = Get-CompatiblePython -Executable $pythonCommand.Source
            }
        }
        if ($null -eq $pythonInfo -and $env:USERPROFILE) {
            $codexPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
            if (Test-Path -LiteralPath $codexPython -PathType Leaf) {
                $pythonInfo = Get-CompatiblePython -Executable $codexPython
            }
        }
        if ($null -eq $pythonInfo) {
            throw '64-bit Python 3.12 was not found. Install it from python.org/downloads/windows/ (the Python launcher is useful), or set STATS_PYTHON to its python.exe path, then rerun this setup. No WSL or Docker is required.'
        }
        Write-Host ('Creating .venv with Python ' + $pythonInfo.version)
        & $pythonInfo.executable -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { throw 'Creating the project environment failed.' }
    }

    Write-Host 'Installing the exact dependency versions from requirements.lock.txt...'
    & $venvPython -m pip --disable-pip-version-check install --requirement $lockPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Dependency installation failed. Check network access to PyPI and rerun setup; existing imported data is unaffected.'
    }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
    Write-Host 'Versions below: Python, Streamlit, pandas, Plotly, SQLite'
    & $venvPython -c 'import sys, streamlit, pandas, plotly, sqlite3; print(sys.version.split()[0], streamlit.__version__, pandas.__version__, plotly.__version__, sqlite3.sqlite_version)'
    if ($LASTEXITCODE -ne 0) { throw 'A required package could not be imported.' }
    Write-Host 'Environment ready. No system-wide Python or security settings were changed.'
    exit 0
}
catch {
    Write-Host ('SETUP ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
