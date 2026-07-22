# Excel Root Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an atomic GUI workflow that remaps all production Excel paths from a user-selected `【竞价】` directory.

**Architecture:** A focused service module derives candidate paths, validates the complete batch, creates configuration backups, and atomically writes only `excel.path`. `MainWindow` owns folder selection and user feedback; `InlineConfigMenu` exposes the command.

**Tech Stack:** Python 3.14, pathlib, JSON, shutil, PySide6, pytest.

## Global Constraints

- Keep version `2026.7.22.108`.
- Do not run real report tasks or write business Excel files.
- Do not commit or publish this work.
- Any validation failure must produce zero configuration changes.
- Only `excel.path` may change in project JSON.

---

### Task 1: Atomic Excel Path Migration Service

**Files:**
- Create: `modules/excel_path_config.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Produces: `configure_excel_paths(root: Path, selected_root: Path) -> ExcelPathConfigResult`
- Produces: result fields `updated`, `errors`, `paths`, and `backup_dir`

- [ ] Write failing tests for exact `【竞价】` suffix derivation, all-or-nothing validation, template exclusion, backup creation, and preservation of non-path fields.
- [ ] Run the focused tests and confirm they fail because the service does not exist.
- [ ] Implement planning, validation, backup, atomic writes, and rollback after write failure.
- [ ] Run the focused tests and confirm they pass.

### Task 2: System Menu Integration

**Files:**
- Modify: `gui/main_window.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `configure_excel_paths(root, selected_root)`
- Produces: `MainWindow.configure_excel_paths_from_folder()`

- [ ] Write a failing GUI test that verifies the new system-menu row, folder selection, success refresh, cancel behavior, and validation-error feedback.
- [ ] Run the focused GUI tests and confirm the new row and handler are missing.
- [ ] Add the inline menu signal/row and connect it to a folder chooser restricted by post-selection validation.
- [ ] Display a concise success or failure message and refresh project summaries only after success.
- [ ] Run focused GUI tests and confirm they pass.

### Task 3: Verification and Local Build

**Files:**
- Modify: `tests/test_basic.py`
- Build: `dist/hourlyreport_automation.exe`

- [ ] Run `python -m py_compile` for modified modules and `git diff --check`.
- [ ] Run `.venv\Scripts\python.exe -m pytest tests\test_basic.py`.
- [ ] Rebuild local version `2026.7.22.108` with `tools\build_desktop_exe.py`.
- [ ] Re-run the build-integrity and Excel path configuration tests.
