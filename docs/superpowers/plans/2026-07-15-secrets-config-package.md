# Authorization Configuration Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paired plaintext full-secrets export/import actions to the GUI system menu, with silent backup, atomic replacement, automatic project configuration checking, and actionable retry errors.

**Architecture:** A Qt-independent `modules/secrets_package.py` owns package serialization, SHA-256 validation, backup, and atomic replacement. `gui/main_window.py` owns only menu wiring, file dialogs, retry UX, logging, and triggering the existing project configuration check. Release filtering prevents exported `.baidu-secrets` files from entering any package.

**Tech Stack:** Python 3.11+, standard library JSON/hashlib/os/shutil/tempfile, PySide6, pytest.

## Global Constraints

- Package format is plaintext `baidu-secrets-package-v1` with extension `.baidu-secrets`.
- Import fully replaces `secrets/secrets.json`; it does not merge fields.
- The old secrets file is silently backed up before replacement.
- Replacement is atomic and must not leave a partially written target.
- Successful import immediately runs the existing project configuration check without a success confirmation dialog.
- Failed import shows the concrete reason and offers retry or cancel.
- No password or token value may appear in logs, dialogs, tests, docs, Git, releases, or update packages.
- Do not run real `run` / `run-daily` and do not write any business Excel file.
- Rebuild the GUI EXE after verification, but do not generate an internal release package.

---

### Task 1: Secrets Package Domain Module

**Files:**
- Create: `modules/secrets_package.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Produces: `SecretsPackageError(RuntimeError)`.
- Produces: `export_secrets_package(secrets_path: str | Path, output_path: str | Path) -> dict[str, Any]`.
- Produces: `import_secrets_package(package_path: str | Path, secrets_path: str | Path, backup_dir: str | Path) -> dict[str, Any]`.

- [ ] **Step 1: Write failing round-trip and replacement tests**

```python
def test_secrets_package_round_trip_fully_replaces_target_and_backs_up(tmp_path):
    source = tmp_path / "source.json"
    package = tmp_path / "team.baidu-secrets"
    target = tmp_path / "receiver" / "secrets" / "secrets.json"
    source_payload = {"baidu": {"demo": {"username": "u", "password": "p"}}, "baidu_api": {"demo": {"access_token": "a.b.c"}}}
    old_payload = {"baidu": {"old": {"username": "old", "password": "old"}}, "local_only": True}
    source.write_text(json.dumps(source_payload, ensure_ascii=False), encoding="utf-8")
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(old_payload, ensure_ascii=False), encoding="utf-8")

    export_secrets_package(source, package)
    report = import_secrets_package(package, target, tmp_path / "backups")

    assert json.loads(target.read_text(encoding="utf-8")) == source_payload
    assert json.loads(Path(report["backup_path"]).read_text(encoding="utf-8")) == old_payload
```

- [ ] **Step 2: Write failing corruption and structure tests**

```python
def test_secrets_package_rejects_checksum_mismatch_without_changing_target(tmp_path):
    target = tmp_path / "secrets.json"
    target.write_text('{"baidu":{"keep":{}}}', encoding="utf-8")
    before = target.read_bytes()
    package = tmp_path / "bad.baidu-secrets"
    package.write_text(json.dumps({
        "format": "baidu-secrets-package-v1",
        "exported_at": "2026-07-15T15:30:00",
        "payload_sha256": "0" * 64,
        "secrets": {"baidu": {}},
    }), encoding="utf-8")

    with pytest.raises(SecretsPackageError, match="校验"):
        import_secrets_package(package, target, tmp_path / "backups")
    assert target.read_bytes() == before
```

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "secrets_package" -q
```

Expected: collection/import failure because `modules.secrets_package` does not exist.

- [ ] **Step 4: Implement the minimal domain module**

```python
PACKAGE_FORMAT = "baidu-secrets-package-v1"

def _payload_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def _validate_secrets(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("baidu"), dict):
        raise SecretsPackageError("授权配置缺少有效的 baidu 配置")
    if "baidu_api" in payload and not isinstance(payload["baidu_api"], dict):
        raise SecretsPackageError("授权配置中的 baidu_api 结构无效")
```

Implement UTF-8 JSON reads, wrapper validation, SHA-256, timestamped backup, temporary sibling file with `flush()` plus `os.fsync()`, `os.replace()`, temporary cleanup, and reports containing paths/counts but no secret values.

- [ ] **Step 5: Run the domain tests and verify GREEN**

Run the Step 3 command. Expected: all `secrets_package` tests pass.

---

### Task 2: Prevent Sensitive Packages from Entering Releases

**Files:**
- Modify: `tools/build_release.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Updates: `EXCLUDE_SUFFIXES` to include `.baidu-secrets`.

- [ ] **Step 1: Add the failing filter assertion**

```python
def test_release_filter_excludes_exported_authorization_packages():
    assert should_include_file(Path("百度授权配置.baidu-secrets"), internal=True) is False
    assert should_include_file(Path("exports") / "team.baidu-secrets", online_update=True) is False
```

- [ ] **Step 2: Run the focused test and verify RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "excludes_exported_authorization" -q
```

Expected: assertions fail because the suffix is currently allowed.

- [ ] **Step 3: Add `.baidu-secrets` to `EXCLUDE_SUFFIXES`**

```python
EXCLUDE_SUFFIXES = {".pyc", ".tmp", ".bak", ".spec", ".baidu-secrets"}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: pass.

---

### Task 3: GUI Menu, Export Flow, and Retryable Import Flow

**Files:**
- Modify: `gui/main_window.py`
- Modify: `tests/test_basic.py`

**Interfaces:**
- Adds signals: `InlineConfigMenu.import_secrets_requested`, `InlineConfigMenu.export_secrets_requested`.
- Adds methods: `MainWindow.import_authorization_config()`, `MainWindow.export_authorization_config()`.
- Consumes Task 1 domain functions.

- [ ] **Step 1: Update menu layout assertions before production code**

```python
expected = [
    "项目配置检查", "导入授权配置", "导出授权配置", "恢复备份", "桌面宠物", "退出程序"
]
assert [action.text() for action in window.system_config_menu.actions() if not action.isSeparator()] == expected
assert "导入授权配置" in inline_labels
assert "导出授权配置" in inline_labels
```

- [ ] **Step 2: Add failing GUI behavior tests**

Test export by monkeypatching `QFileDialog.getSaveFileName` and `export_secrets_package`. Test import success by monkeypatching `QFileDialog.getOpenFileName`, `import_secrets_package`, and `window.run_environment_preflight`, then assert exactly one import and one preflight call with no success `QMessageBox.information`. Test failure by returning a bad package first, monkeypatching `QMessageBox.warning` to return `Retry`, returning a good package second, and asserting the file dialog opens twice.

- [ ] **Step 3: Run GUI-focused tests and verify RED**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "config_actions_live_in_title_menu or authorization_config" -q
```

Expected: missing menu rows, signals, or methods.

- [ ] **Step 4: Wire both menu implementations**

Add action rows after the first separator in `InlineConfigMenu`. Add matching `QAction` objects after the first separator in `system_config_menu`. Connect both paths to the same `MainWindow` methods. Preserve the existing menu style and spacing.

- [ ] **Step 5: Implement export and import UI methods**

```python
def import_authorization_config(self) -> None:
    while True:
        selected, _ = QFileDialog.getOpenFileName(...)
        if not selected:
            return
        try:
            report = import_secrets_package(selected, self.credentials_config_path(), self.root / "backups")
        except SecretsPackageError as exc:
            choice = QMessageBox.warning(..., QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Retry)
            if choice == QMessageBox.StandardButton.Retry:
                continue
            return
        self.append_log(f"授权配置导入完成：{report['package_path']}")
        self.run_environment_preflight()
        return
```

Implement export with a default timestamped filename, automatic `.baidu-secrets` suffix, domain call, non-sensitive log, and a plaintext sensitivity notice after success.

- [ ] **Step 6: Run GUI-focused tests and verify GREEN**

Run the Step 3 command. Expected: pass.

---

### Task 4: Documentation, Full Verification, and EXE Build

**Files:**
- Modify: `README_同事使用说明.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-15-secrets-config-package-design.md`
- Modify: `tests/test_basic.py` only if verification exposes an actual regression.

**Interfaces:**
- Documents the exact GUI workflow and plaintext handling warning.

- [ ] **Step 1: Document administrator export and colleague import**

Add concise instructions stating that import fully overwrites secrets, creates a silent backup, automatically runs project configuration checking, and must never be sent through GitHub Release.

- [ ] **Step 2: Run focused tests**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -k "secrets_package or authorization_config or online_update" -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run the complete basic suite**

```cmd
.venv\Scripts\python.exe -m pytest tests\test_basic.py -q
```

Expected: all tests pass, no business task runs.

- [ ] **Step 4: Check the diff and sensitive files**

```cmd
git diff --check
git status --short
git diff | rg -n "access_token|refresh_token|password"
```

Expected: only schema/example key names appear; no real values or `.baidu-secrets` files are tracked.

- [ ] **Step 5: Rebuild the GUI EXE**

```cmd
build_desktop_exe.bat
```

Expected: `dist/百度数据自动化控制台.exe` exists, exits build successfully, launches without a console window, and shows both new system menu actions.

- [ ] **Step 6: Do not generate an internal package**

Confirm no new internal ZIP or version `102` exists. Leave `CURRENT_VERSION` at `2026.7.15.101` until a separately approved release.
