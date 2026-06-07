# Desktop EXE Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop control panel that lets non-technical coworkers run the existing hourly/daily automation with visible progress and logs.

**Architecture:** The GUI is a thin PySide6 wrapper around the current command-line automation. It reads project configs, constructs safe subprocess commands, streams output, and displays progress without rewriting Baidu, KST, or Excel logic.

**Tech Stack:** Python 3.14, PySide6, PyInstaller, existing `main.py` commands, pytest for non-visual logic.

---

## File Map

- Create `gui/__init__.py`: package marker.
- Create `gui/project_store.py`: load visible projects and expose lightweight project summaries.
- Create `gui/command_builder.py`: build hourly, daily, and preflight commands.
- Create `gui/environment_check.py`: run safe startup checks.
- Create `gui/task_runner.py`: Qt subprocess wrapper for live output and completion events.
- Create `gui/main_window.py`: PySide6 main window.
- Create `gui/app.py`: GUI entry point.
- Create `run_desktop_gui.bat`: local launcher.
- Create `tools/build_desktop_exe.py`: PyInstaller build helper.
- Create `build_desktop_exe.bat`: packaging launcher.
- Modify `requirements.txt`: add `PySide6` and `pyinstaller`.
- Modify `tests/test_basic.py`: add tests for project loading, command building, and environment checks.

## Task 1: Project Store

**Files:**
- Create: `gui/__init__.py`
- Create: `gui/project_store.py`
- Modify: `tests/test_basic.py`

- [ ] **Step 1: Write failing project store tests**

Add tests that create temporary project configs, call `load_project_summaries(root)`, and assert templates are excluded and project labels are returned.

- [ ] **Step 2: Run test to verify it fails**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui_project_store" -v
```

Expected: fail because `gui.project_store` does not exist.

- [ ] **Step 3: Implement project store**

Create a small dataclass:

```python
@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    project_name: str
    path: str
```

Implement `load_project_summaries(root)` using existing `modules.project_config.list_projects`.

- [ ] **Step 4: Run test to verify it passes**

Run the same targeted pytest command. Expected: pass.

## Task 2: Command Builder

**Files:**
- Create: `gui/command_builder.py`
- Modify: `tests/test_basic.py`

- [ ] **Step 1: Write failing command builder tests**

Test:

- Hourly command contains `.venv\Scripts\python.exe`, `main.py`, `--mode run`, normalized period, `--yes`.
- Daily command contains `--mode run-daily`, `--date`, `--yes`.
- Preflight command contains `--mode preflight`, `--task`, `--quick`.

- [ ] **Step 2: Run RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui_command_builder" -v
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement command builder**

Expose:

```python
def python_exe(root: Path) -> Path
def build_hourly_command(root: Path, period: str) -> list[str]
def build_daily_command(root: Path, date_text: str | None) -> list[str]
def build_preflight_command(root: Path, task: str) -> list[str]
```

Use list arguments, not shell strings.

- [ ] **Step 4: Run GREEN**

Run targeted tests. Expected: pass.

## Task 3: Environment Check

**Files:**
- Create: `gui/environment_check.py`
- Modify: `tests/test_basic.py`

- [ ] **Step 1: Write failing environment check tests**

Test result shape:

```python
{
    "passed": bool,
    "checks": [
        {"name": "Python environment", "passed": bool, "severity": "error" | "warning" | "info", "detail": "..."}
    ],
}
```

Use a temporary root with missing `.venv` and assert the Python environment check fails without throwing.

- [ ] **Step 2: Run RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui_environment" -v
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement environment check**

Implement `run_environment_check(root)` with safe checks only:

- runtime folders exist or can be created
- `.venv\Scripts\python.exe` exists
- project configs can be listed
- `secrets/secrets.json` exists
- required imports are checked by subprocess only when Python exists

- [ ] **Step 4: Run GREEN**

Run targeted tests. Expected: pass.

## Task 4: Task Runner

**Files:**
- Create: `gui/task_runner.py`
- Modify: `tests/test_basic.py`

- [ ] **Step 1: Write non-Qt progress mapping tests**

Add a pure function `infer_stage(line: str) -> str | None` and test Chinese/English command output maps to broad stages such as `preflight`, `baidu`, `kst`, `excel`, `done`, `error`.

- [ ] **Step 2: Run RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui_task_runner" -v
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement task runner**

Implement `infer_stage`. Implement `QtTaskRunner` only if PySide6 is importable; keep import guarded so tests can run before GUI dependencies are installed.

- [ ] **Step 4: Run GREEN**

Run targeted tests. Expected: pass.

## Task 5: PySide6 Main Window

**Files:**
- Create: `gui/main_window.py`
- Create: `gui/app.py`
- Create: `run_desktop_gui.bat`

- [ ] **Step 1: Implement main window**

Build the Codex-style layout:

- left rail: project combo, hourly period segmented buttons, daily date field, task buttons
- center: progress rows
- bottom/right: log console
- footer: open logs, open reports, open folder

- [ ] **Step 2: Wire commands**

Buttons call command builder functions and pass list commands to `QtTaskRunner`.

- [ ] **Step 3: Add friendly empty states**

Show startup environment check results and disable run buttons when `.venv` is missing.

- [ ] **Step 4: Manual smoke run**

Run:

```cmd
run_desktop_gui.bat
```

Expected: GUI opens, no task starts automatically, project list appears.

## Task 6: Packaging

**Files:**
- Create: `tools/build_desktop_exe.py`
- Create: `build_desktop_exe.bat`
- Modify: `requirements.txt`
- Modify: `tests/test_basic.py`

- [ ] **Step 1: Add dependency tests**

Check `requirements.txt` contains `PySide6` and `pyinstaller`.

- [ ] **Step 2: Implement build helper**

Build one-folder PyInstaller output:

```cmd
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onedir --windowed --name 百度日报小时报控制台 gui\app.py
```

- [ ] **Step 3: Add BAT launcher**

`build_desktop_exe.bat` checks `.venv`, installs GUI dependencies if needed, then runs the helper.

- [ ] **Step 4: Verify build path**

Run build helper after dependencies are installed. Expected output under `dist/百度日报小时报控制台/`.

## Task 7: Final Verification

**Files:**
- Existing files only.

- [ ] **Step 1: Run targeted GUI logic tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "desktop_gui" -v
```

- [ ] **Step 2: Run full baseline tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py
```

- [ ] **Step 3: Manual GUI smoke**

Open the GUI and confirm:

- project selector renders
- environment check is visible
- quick preflight streams logs
- failure output is readable
- logs/reports buttons open folders

- [ ] **Step 4: Commit**

```cmd
git add gui run_desktop_gui.bat build_desktop_exe.bat tools/build_desktop_exe.py requirements.txt tests/test_basic.py docs/superpowers
git commit -m "Add desktop console GUI"
```

## Self-Review

- Spec coverage: the plan covers project loading, command construction, environment checks, task execution, visual shell, packaging, and verification.
- Placeholder scan: no task uses open-ended placeholders for behavior. Visual polish details are constrained to the approved Codex console layout.
- Type consistency: command builders return `list[str]`; environment checks return dictionaries; task runner exposes one pure mapping function plus guarded Qt wrapper.
