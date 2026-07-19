# Persistent GUI Log And Windows Installer Design

## Goal

Finish the single-project desktop baseline by retaining all GUI output and providing one standard Windows installer for new colleagues.

## Log Flow

Every line reaches two independent sinks. The history sink immediately appends a timestamped, credential-redacted line to `logs/gui_history.log`; it is never cleared by a new task. The display sink queues the original line and reveals it through a 16 ms timer. The batch size scales with pending characters, preserving a visible typing effect under normal output while catching up quickly during dense command output.

Clearing the real-time panel only resets the display queue. Disk history remains intact. A logging write failure must not interrupt hourly or daily execution.

## Installer

Inno Setup produces `Hourlyreport_automation_setup_v<version>.exe`. It defaults to the current user's application directory, keeps the normal directory-selection page, creates desktop and Start Menu shortcuts, and launches the GUI after installation. Reinstalling program files must preserve existing configs, secrets, logs, reports, backups, and KST exports.

The installer embeds the same credential-free first-install payload used by release tests. It never includes `secrets/secrets.json` or exported OAuth/configuration bundles. Online update ZIPs remain separate and continue to preserve user data.

## Verification

- Unit tests cover history append, redaction, adaptive display batching, and installer safety declarations.
- GUI tests verify queued output renders completely.
- A real silent install and reinstall into a temporary directory must confirm required files, absence of real secrets, and preservation of a modified config.
- Full tests, API read-only readiness, EXE startup, package hashes, and release-boundary audits remain mandatory.
