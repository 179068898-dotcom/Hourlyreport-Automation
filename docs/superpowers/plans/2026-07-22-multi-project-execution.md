# Multi-Project API Parallel Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add production-ready 1-to-3 project execution with parallel API preparation, serial Excel pipelines, queue-safe stop behavior, persisted selection, and final GUI summary.

**Architecture:** A new coordinator owns validation, API-only parallel preparation, ordered serial pipelines, stop state, and the aggregate report. Existing single-project pipelines remain unchanged; each serial multi-project pipeline receives a cached API result through its existing injected fetch function. GUI launches one `run-multi` subprocess and reads the coordinator report on completion.

**Tech Stack:** Python 3.11+, `concurrent.futures.ThreadPoolExecutor`, PySide6, pytest, existing JSON configuration and pipeline modules.

## Global Constraints

- Select 1 to 3 unique projects and preserve user order.
- API runs in parallel; Excel pipelines run serially in selection order.
- Multi-project mode never starts or falls back to Chrome.
- Failure skips only that project; no partial API/browser mixing.
- Stop lets the current project finish and prevents the next queued project from starting.
- Open all successful Excel files only after all writes finish.
- Do not touch real Excel, credentials, browsers, release version, or installer during implementation tests.

---

### Task 1: Selection persistence and validation

**Files:**
- Create: `modules/multi_project_selection.py`
- Test: `tests/test_multi_project.py`

**Interfaces:**
- Produces: `load_multi_project_selection(root, available_ids, fallback_id) -> list[str]`
- Produces: `save_multi_project_selection(root, project_ids) -> Path`
- Produces: `validate_multi_project_ids(project_ids, available_ids, max_projects=3) -> list[str]`

- [x] **Step 1: Write failing tests** for ordered round-trip, atomic file creation, filtering removed projects, 1-project acceptance, duplicate rejection, unknown rejection, and 4-project rejection.
- [x] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests\test_multi_project.py -k selection -v` and verify failures are caused by the missing module.
- [x] **Step 3: Implement** JSON `{ "project_ids": [...] }` persistence at `configs/multi_project_selection.json` using temp file, `fsync`, and `os.replace`; validation returns normalized ordered IDs or raises `ValueError`.
- [x] **Step 4: Re-run** the selection tests and verify all pass.

### Task 2: API-only project fetch

**Files:**
- Modify: `modules/baidu_data_source.py`
- Modify: `modules/data_merger.py`
- Test: `tests/test_multi_project.py`

**Interfaces:**
- Produces: `fetch_baidu_api_only_hourly(config, root, logger, period, ...) -> dict`
- Produces: `fetch_baidu_api_only_daily(config, root, logger, target_date, ...) -> dict`
- Daily merge consumes `config["baidu"]["daily_output_path"]` with the existing default when absent.

- [x] **Step 1: Write failing tests** proving API-only success commits the configured output, API failure returns route metadata without invoking any browser callable, multi-source failure is atomic, and daily merge reads a configured API artifact path.
- [x] **Step 2: Run** the focused tests and confirm expected failures.
- [x] **Step 3: Implement** a private API-only route reusing `_api_attempts` and `_collect_baidu_multi_source_api`; expose hourly/daily wrappers and never accept a browser fetcher.
- [x] **Step 4: Update** `merge_daily_files` to resolve `daily_output_path`, preserving `reports/baidu_daily_data.json` as the single-project default.
- [x] **Step 5: Re-run** the focused API-only tests and existing Baidu source tests.

### Task 3: Multi-project coordinator

**Files:**
- Create: `modules/multi_project_runner.py`
- Test: `tests/test_multi_project.py`

**Interfaces:**
- Produces: `run_multi_project_pipeline(root, logger, project_ids, task, period=None, target_date=None, stop_gate=None, api_fetch_hourly=..., api_fetch_daily=..., hourly_pipeline=..., daily_pipeline=..., max_workers=3) -> dict`
- Produces: aggregate report at `reports/multi_project_run_report.json`.

- [x] **Step 1: Write failing tests** using barriers/events to prove API overlap, serial pipeline non-overlap, selection-order writes despite out-of-order API completion, isolated project failure, one-project operation, duplicate Excel-path preflight rejection, and no pipeline call for API failures.
- [x] **Step 2: Run** the coordinator tests and confirm they fail because the runner is absent.
- [x] **Step 3: Implement** project config loading, runtime config building, unique per-run API paths, a maximum-three-worker pool, ordered serial execution with cached fetch callbacks, and atomic aggregate report writes.
- [x] **Step 4: Add failing stop tests** for stop-before-first-project, stop-during-current-project, and successful API results discarded after stop.
- [x] **Step 5: Implement** queue stop checks only before each serial project. Do not expose the queue stop gate to child single-project pipelines.
- [x] **Step 6: Re-run** all coordinator tests.

### Task 4: CLI and GUI integration

**Files:**
- Modify: `main.py`
- Modify: `gui/command_builder.py`
- Modify: `gui/main_window.py`
- Test: `tests/test_multi_project.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- CLI: `--mode run-multi --projects id1,id2 --task hourly|daily [--period ...] [--date ...]`
- GUI command builders: `build_multi_hourly_command(...)`, `build_multi_daily_command(...)`.

- [x] **Step 1: Write failing tests** for command construction, CLI limits, GUI accepting one multi selection, selection restoration, and removal of the preview blocker.
- [x] **Step 2: Run** focused CLI/GUI tests and confirm expected failures.
- [x] **Step 3: Implement** the `run-multi` CLI branch and use `pipeline_exit_code` only for fatal coordinator failures.
- [x] **Step 4: Implement** GUI persistence on confirmed selection, multi command dispatch, queue stop file creation, and stop controls that remain available during the current project.
- [x] **Step 5: Add failing GUI completion tests** for aggregate status and ordered deduplicated Excel opening after task completion.
- [x] **Step 6: Implement** aggregate report rendering and delayed opening of successful Excel paths; leave single-project completion unchanged.
- [x] **Step 7: Re-run** focused GUI and command tests.

### Task 5: Regression, docs, and review

**Files:**
- Modify: `docs/gui_multi_project_selection_design.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `tests/test_multi_project.py`
- Test: `tests/test_basic.py`

**Interfaces:**
- Documents the production behavior and preserves the warning that browser fallback is single-project only.

- [x] **Step 1: Update docs** to match 1-to-3 selection, API parallelism, serial Excel, stop semantics, and report location.
- [x] **Step 2: Run** `.venv\Scripts\python.exe -m pytest tests\test_multi_project.py -v`.
- [x] **Step 3: Run** `.venv\Scripts\python.exe -m pytest tests\test_basic.py`（发布构建指纹门禁在未重建 EXE 的开发阶段单独排除）。
- [x] **Step 4: Inspect** `git diff --check`, `git diff --stat`, and changed-file diff; verify no secrets, local configs, reports, or real workbooks are staged.
- [x] **Step 5: Perform code review** against the design checklist and fix any critical or high findings before reporting completion.
