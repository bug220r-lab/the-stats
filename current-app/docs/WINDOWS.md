# Windows setup, launch, and troubleshooting

## Requirements and installation

- Native Windows with PowerShell and a working 64-bit Python **3.12** interpreter.
- Internet access for the first dependency installation. After setup, importing local exports and using the dashboard works without platform APIs or API keys.
- A local writable data directory. The default is `%LOCALAPPDATA%\TheStats`, separate from the project and OneDrive.

Open the project folder and double-click `setup_windows.bat`. Setup checks the existing `.venv` first. When creating a new environment, interpreter discovery uses `STATS_PYTHON` if supplied, then `py -3.12`, a compatible `python.exe` on PATH, and finally an available compatible Codex runtime. Windows Store execution aliases are not treated as Python installations. An invalid explicit `STATS_PYTHON` fails with an explanation rather than selecting a different interpreter.

If discovery fails, install [Python 3.12 for Windows](https://www.python.org/downloads/windows/) and rerun setup. You can also choose an already installed interpreter from PowerShell:

```powershell
# Substitute the actual executable path on this computer.
$env:STATS_PYTHON = '<path-to-Python-3.12>\python.exe'
.\setup_windows.bat
```

The script creates a project-local environment and installs `requirements.lock.txt`, then runs `pip check` and imports the main libraries. It does not replace an incompatible or incomplete `.venv`. Preserve or rename that directory yourself before rebuilding it. A virtual environment is machine-specific: recreate it when moving the project instead of copying it to another PC or Linux.

`setup_windows.bat` runs its PowerShell script with `-ExecutionPolicy Bypass` for that child process. It does not call `Set-ExecutionPolicy` or change machine/user policy, firewall configuration, antivirus settings, or system Python. Organization-enforced policies may still prohibit script execution; do not weaken them. The manual commands below use the same dependency lock file in an ordinary PowerShell window:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --requirement requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
```

These manual commands assume no existing incompatible environment and an installed Python launcher. Interpreter activation is unnecessary.

## Normal operation

Double-click `launch_windows.bat`. It uses its own project directory and `.venv\Scripts\python.exe`, starts Streamlit on `127.0.0.1:8501`, checks the local health endpoint, then opens the default browser. The application refuses unauthenticated local access if it is started with any other bind address.

Leave the console open. To shut down, press **Ctrl+C in that console**, then wait for the process to stop. If Windows asks `Terminate batch job (Y/N)?`, choose `Y`. You may then close the browser tab. Closing only the browser leaves the server running. Do not use Task Manager or force a console closed as the normal shutdown procedure.

After shutdown, double-click the launcher again. The existing database and imports are reused. Browser refresh and new browser tabs use the same data store.

Advanced local launch from the project folder:

```powershell
.\launch_windows.bat --no-browser --port 8502
```

Open `http://127.0.0.1:8502` manually for that command. Port options never change the bind address.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| “Python 3.12 was not found” | Install 64-bit Python 3.12 with its launcher, or set `STATS_PYTHON` to a real executable. A Microsoft Store shortcut alone is insufficient. |
| Existing `.venv` is incompatible/incomplete | Stop the app. Preserve/rename `.venv`, then rerun setup. Imported data lives separately. |
| Dependency install failed | Check the network connection and access to PyPI; rerun setup. Do not disable TLS validation or security controls. |
| `No module named streamlit` | Run setup again from the complete project. Launch through the batch file so system Python is not used. |
| Port already in use | Stop the earlier dashboard in its console, or use `--port 8502`. The launcher will not terminate another application or open an unverified occupied port. |
| Browser did not open | Copy the exact `http://127.0.0.1:<port>` address printed after “Dashboard ready” into the browser. Keep the console open. |
| Local access refused | Use `launch_windows.bat`; it supplies `--server.address 127.0.0.1`. Do not expose local unauthenticated mode through a proxy or tunnel. |
| Hosted configuration error during local launch | Remove `STATS_MODE` from the current session with `Remove-Item Env:STATS_MODE`, or explicitly set it to `local`, then relaunch. |
| Database unavailable/read-only | Confirm the configured data folder is writable and on a local disk. Stop another process holding a lock; do not delete database files. |
| Database appears empty after changing a path | Check `STATS_DATA_DIR`: a different directory has a different database. Point back to the intended data directory; do not re-import merely to hide a path mistake. |
| Import validation error | Read the row/column explanation, correct a separate working copy or the column mapping, and preview again. Keep the original evidence file intact. |
| Conflicting observation or sealed archive | Choose a new snapshot label for newer/revised evidence. Sealed snapshots cannot be replaced through import. Original October 20 baseline membership remains unverified. |
| Private exports absent on another PC | They are intentionally excluded from Git. Transfer approved source files and/or a verified database backup through a private channel. |
| Dashboard shows no data | Select the intended snapshot and filters, then import the actual required export. An honest empty state is expected when that evidence is unavailable. |

Record the console error and the exact action that produced it when reporting a problem. Never paste credentials, private tokens, or unredacted exports into public issue trackers.
