# Desktop EXE Console Design

## Goal

Build a Windows 10/11 desktop EXE for non-technical coworkers to run the existing Baidu hourly and daily automation safely, with a Codex-style control panel, visible progress, friendly status text, and easy access to logs and reports.

## Product Direction

The first GUI version is a polished operator panel, not a rewrite of the automation engine. It keeps the stable command-line flow as the source of truth and wraps it with:

- A left project/task navigation area.
- A central task progress area.
- A Codex-like live log console.
- Clear success, failure, and next-step messages.
- Buttons to open logs, reports, and the working folder.

The interface should feel calm, modern, and slightly soft: rounded corners, restrained colors, clear hierarchy, and no dense technical clutter on the first screen.

## First Version Scope

The first EXE includes five entries:

1. Hourly report: choose project and period, then run the existing hourly command.
2. Daily report: choose project and date, defaulting to yesterday, then run the existing daily command.
3. Quick preflight: run the existing quick preflight for hourly or daily.
4. Open logs and reports: open the local `logs/` and `reports/` folders.
5. Environment check: verify Python environment, key dependencies, project config, credentials, Chrome debug readiness, and common runtime folders.

The first version does not edit project configs, Excel paths, or account passwords. Those remain file-based to avoid accidental damage by non-technical users.

## Architecture

The GUI process is a thin orchestration layer. It starts subprocesses that call the current `.venv\Scripts\python.exe main.py ...` commands and streams stdout/stderr into the log console. It does not import browser automation internals or duplicate the Excel writing workflow.

Core pieces:

- `gui/app.py`: PySide6 application entry.
- `gui/main_window.py`: main window layout and interaction wiring.
- `gui/task_runner.py`: subprocess execution, output streaming, cancellation state, and exit code reporting.
- `gui/project_store.py`: read project list and current app config without mutating config unless explicitly requested later.
- `gui/environment_check.py`: safe checks for local folders, `.venv`, Python package presence, configs, secrets, and Chrome debug endpoint.
- `run_desktop_gui.bat`: development/runtime launcher.
- `build_desktop_exe.bat` and `tools/build_desktop_exe.py`: PyInstaller packaging helpers.

## UI Layout

The window uses a three-zone console layout:

- Left rail: project selector, task buttons, period/date controls, and quick folder shortcuts.
- Main progress area: task title, active project, progress steps, current status, and final result card.
- Log console: live text output with error highlighting and automatic scroll.

Progress steps are shown as stable rows:

1. Environment
2. Project config
3. Preflight
4. Baidu data
5. KST export
6. Excel write
7. Report output

The GUI maps command output to broad progress stages by matching safe keywords and by command lifecycle. Exact business judgment remains in the existing JSON reports.

## Runtime Behavior

Hourly command:

```cmd
.venv\Scripts\python.exe main.py --mode run --period "15点" --yes
```

Daily command:

```cmd
.venv\Scripts\python.exe main.py --mode run-daily --date "2026-06-06" --yes
```

Quick preflight command:

```cmd
.venv\Scripts\python.exe main.py --mode preflight --task hourly --quick
```

The GUI may use a temporary app config copy when running a selected project so it does not unexpectedly overwrite `configs/app_config.json`. The existing OpenClaw BAT entry remains unchanged.

## Safety Rules

- Do not rebuild Excel files.
- Do not write to unrelated sheets.
- Do not bypass the existing `main.py` execution path.
- Do not launch Edge.
- Do not hide long-running work; always show progress and logs.
- Do not print or reveal stored passwords in the UI.
- Do not allow concurrent task runs in the first version.
- Keep OpenClaw BAT compatibility intact.

## Environment Check

On startup, the GUI runs a lightweight check and shows progress:

- Runtime folders: `logs/`, `reports/`, `backups/`, `kst_exports/`.
- `.venv\Scripts\python.exe` exists.
- Required imports are available: `openpyxl`, `pandas`, `xlrd`, `dateutil`, `playwright`, `rich`.
- GUI imports are available: `PySide6`.
- Project configs parse.
- Required credential profiles exist, without displaying values.
- Chrome debug endpoint readiness is shown as OK, warning, or needs manual start.

If dependencies are missing, the GUI displays a friendly repair action that runs the existing installer BAT or a GUI dependency installer step.

## Packaging

The desktop build uses PyInstaller after `PySide6` and `pyinstaller` are installed. The first packaging target is a one-folder build for stability and easier debugging. A one-file EXE can come after the first operator version is stable.

The visible top-level launcher should be easy to find. Later internal packaging can put the GUI EXE at the outermost release folder while keeping Python modules inside the application directory.

## Testing

Automated tests focus on non-visual logic:

- Project list loading.
- Command construction.
- Environment check result shape.
- Secret/profile reference checks without printing passwords.
- Task runner output parsing and status transitions.

Manual GUI checks cover:

- Startup on Windows 10/11.
- Missing `.venv` guidance.
- Running quick preflight.
- Running a safe command with logs visible.
- Error display when command exits non-zero.

## Out of Scope For First Version

- Editing Excel or project config paths in the GUI.
- Editing account usernames or passwords.
- Running two projects in parallel.
- Replacing OpenClaw BAT workflows.
- Sending QQ, WeChat, screenshots, or external messages.
