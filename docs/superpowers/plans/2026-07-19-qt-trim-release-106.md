# Qt Trim And Release 106 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible Windows release `2026.7.19.106` whose ZIP is approximately 38 MB, excludes unused Qt runtime components, and provides a persistent user-controlled online-update flow without changing hourly, daily, tray, or Excel behavior.

**Architecture:** Keep the existing PyInstaller one-file application and introduce a checked-in spec file that filters only Qt modules/plugins proven unused by this QtCore/QtGui/QtWidgets application. The normal build entry remains `tools/build_desktop_exe.py`; it invokes the spec, writes the existing manifest, and supplies the black EXE icon while runtime code continues using the transparent taskbar/tray icon.

**Tech Stack:** Python 3.14, PyInstaller 6.20, PySide6, pytest, ZIP release builder.

## Global Constraints

- Release version is exactly `2026.7.19.106`; GitHub tag is `v2026.7.19.106`.
- Release asset is exactly `Hourlyreport_automation_v2026.7.19.106.zip`.
- Do not package `configs/`, `secrets/`, logs, reports, backups, browser data, or user exports in the online update ZIP.
- Do not run real hourly/daily tasks or write Excel during verification.
- Preserve `.claude/settings.local.json` and `configs/app_config.json` as unrelated local changes.
- Keep the full Microsoft YaHei Bold font in this release; only Qt is trimmed.

---

### Task 1: Lock The Qt Trim Contract With Tests

**Files:**
- Modify: `tests/test_basic.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: `tools/hourlyreport_automation.spec` as checked-in build configuration.
- Produces: assertions that the spec removes the audited unused Qt components and retains the Windows platform plugin.

- [ ] **Step 1: Write the failing test**

```python
def test_desktop_build_spec_filters_unused_qt_components():
    source = (ROOT / "tools" / "hourlyreport_automation.spec").read_text(encoding="utf-8")
    for token in ("Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "opengl32sw"):
        assert token in source
    assert "qwindows" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py::test_desktop_build_spec_filters_unused_qt_components`

Expected: FAIL because `tools/hourlyreport_automation.spec` does not exist.

- [ ] **Step 3: Do not modify production code until the expected failure is observed.**

### Task 2: Add A Reproducible Trimmed PyInstaller Build

**Files:**
- Create: `tools/hourlyreport_automation.spec`
- Modify: `tools/build_desktop_exe.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Consumes: project root and `assets/app_icon.ico` supplied through PyInstaller spec globals.
- Produces: `dist/hourlyreport_automation.exe` and `dist/hourlyreport_automation.build.json` through the existing build command.

- [ ] **Step 1: Implement the minimal spec filter**

Filter binaries/data entries whose normalized names contain audited unused Qt libraries or plugin directories: Quick, QML, PDF, VirtualKeyboard, OpenGL/software OpenGL, qpdf, virtualkeyboard, platform input contexts, TLS, network information, and non-Windows platform plugins. Explicitly retain `qwindows.dll`.

- [ ] **Step 2: Update the build entry**

Run PyInstaller with `tools/hourlyreport_automation.spec`, passing `--distpath`, `--workpath`, and `--specpath`-equivalent fixed paths only where supported. Continue writing the manifest with the current source version.

- [ ] **Step 3: Run the focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py::test_desktop_build_spec_filters_unused_qt_components tests\test_basic.py::test_desktop_gui_app_icon_assets_and_build_icon_are_configured`

Expected: both PASS.

- [ ] **Step 4: Build and inspect the EXE archive**

Run: `.venv\Scripts\python.exe tools\build_desktop_exe.py`

Expected: exit 0; EXE approximately 30 MB; archive listing contains `qwindows.dll` and excludes the audited modules.

### Task 3: Verify Runtime-Critical GUI Paths

**Files:**
- Test: `tests/test_basic.py`

**Interfaces:**
- Consumes: trimmed `dist/hourlyreport_automation.exe`.
- Produces: evidence that the application starts and remains responsive.

- [ ] **Step 1: Start the EXE from the project root**

Expected: process remains alive and responsive after 8 seconds with no console window.

- [ ] **Step 2: Run focused GUI/update tests**

Run tests covering single instance, tray creation/exit, calendar popup, file dialog actions, update dialog/helper, A/B mode control, and default 11:00 selection.

Expected: all selected tests PASS.

### Task 4: Upgrade To Version 106

**Files:**
- Modify: `gui/version.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Produces: `CURRENT_VERSION = "2026.7.19.106"` and matching update-selection/build assertions.

- [ ] **Step 1: Change version expectations first**

Update current-version and current online-package assertions to `2026.7.19.106`; keep historical versions unchanged where they are fixtures for upgrade/rollback behavior.

- [ ] **Step 2: Run the changed tests and observe failure**

Expected: FAIL while `gui/version.py` is still `2026.7.19.105`.

- [ ] **Step 3: Change `gui/version.py`**

Set `CURRENT_VERSION = "2026.7.19.106"`.

- [ ] **Step 4: Rebuild the EXE and manifest**

Run: `.venv\Scripts\python.exe tools\build_desktop_exe.py`

Expected: manifest version and source fingerprint match 106 sources.

### Task 5: Make Online Update Progress Explicit And Persistent

**Files:**
- Modify: `gui/update_manager.py`
- Modify: `gui/main_window.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Consumes: `ReleaseUpdate` returned by the GitHub release check.
- Produces: `available` notification, explicit `start_download(update)`, visible download percentage, and `更新重启` ready state.

- [ ] **Step 1: Write failing state-machine tests**

Assert startup checking remains hidden, a newer release emits `available` without downloading, clicking `更新` starts the download, progress text remains visible, failures return to a retryable `更新` state, and completion displays `更新重启`.

- [ ] **Step 2: Verify the old behavior fails**

Run the two focused manager/GUI tests and confirm failures show the missing `available` signal and visible checking flash.

- [ ] **Step 3: Split checking from downloading**

Keep startup checks silent; store the selected `ReleaseUpdate`; start a separate download thread only after the user clicks the available button.

- [ ] **Step 4: Implement persistent button states**

Use `hidden -> available -> downloading -> ready -> installing`, with `下载中`, percentage text, retry after failure, and `更新重启` labels.

- [ ] **Step 5: Run focused update security and rollback tests**

Expected: release selection, archive validation, download integrity, install dialog, protected config preservation, and rollback tests all PASS.

### Task 6: Build And Validate The Online Update ZIP

**Files:**
- Create: `dist/Hourlyreport_automation_v2026.7.19.106.zip`

**Interfaces:**
- Consumes: validated 106 EXE and source tree.
- Produces: online update asset and SHA-256 digest.

- [ ] **Step 1: Run the full test suite**

Run: `.venv\Scripts\python.exe -m pytest tests\test_basic.py`

Expected: all tests PASS.

- [ ] **Step 2: Build the online update ZIP**

Run: `.venv\Scripts\python.exe tools\build_release.py --version 2026.7.19.106 --online-update`

Expected: asset name exactly `Hourlyreport_automation_v2026.7.19.106.zip`, approximately 38 MB.

- [ ] **Step 3: Inspect package boundaries**

Assert the ZIP contains the EXE, GUI/module sources, assets, and runtime requirements; assert it contains no `configs/`, `secrets/`, logs, reports, backups, browser data, `.git`, `.venv`, build directories, or prior ZIP files.

- [ ] **Step 4: Compute SHA-256 and launch from an extracted copy**

Expected: extracted EXE starts and remains responsive; package hash is recorded for the release note.

### Task 7: Commit And Prepare Release Notes

**Files:**
- Modify/Create: files listed above.

**Interfaces:**
- Produces: one Git commit and a copy-ready GitHub Release description.

- [ ] **Step 1: Review `git diff` and stage only task files**

Exclude `.claude/settings.local.json` and `configs/app_config.json`.

- [ ] **Step 2: Commit**

Run: `git commit -m "Release 2026.7.19.106 with trimmed Qt runtime"`

- [ ] **Step 3: Report release metadata**

Include version, tag, asset path, size, SHA-256, test count, and recent user-facing changes: Qt package reduction, persistent click-to-download updater with visible percentage and update-restart action, A/B circular waterdrop styling, 11:00 default hourly period, title/system spacing, bold daily title, split EXE/runtime crab icons, and release-test output isolation.

## Self-Review

- Spec coverage: Qt-only trimming, persistent online-update states, 106 versioning, package generation, commit, release notes, and sensitive-data boundaries are each covered.
- Placeholder scan: no TBD/TODO/implement-later placeholders remain.
- Type consistency: `build_release(..., output_dir=...)`, `CURRENT_VERSION`, manifest naming, and release asset naming match existing interfaces.
