# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.3-alpha.8] - 2026-10-27
### Changed
- Clean up and standardize code and shell scripts across the project
- Simplify public IP address detection and DynDNS synchronization

### Fixed
- Improve background service shutdown reliability
- Keep saved DynDNS update link when changing API credentials and fix config file permissions
- Properly close database connections when exiting the CLI or single-run mode

## [1.0.3-alpha.7] - 2026-07-14
### Added
- Native DynDNS update URL (`update_url`) integration for batch domain synchronization
- Server network & router best practices section

### Changed
- Reorganized CLI interactive menus

## [1.0.3-alpha.6] - 2026-06-25
### Changed
- Relocate `config.toml` path from `/usr/local/share/dyndns` to `/etc/dyndns/config.toml` for strict FHS compliance
- Replace dynamic Python systemd unit generation with static Bash template substitution (`template.service`)

## [1.0.3-alpha05] - 2026-06-18
### Added
- Dedicated service user/group with systemd hardening
- Post-write ownership handoff helper (`src/core/ownership.py`) for encryption key and database

### Changed
- Renamed `ionos-dyndns` -> `dyndns` (IONOS is the provider, not the software name). Reinstall required.
- Bash library synced with `cowapi` reference
- `SERVICE_TYPE=forking`, `SERVICE_RESTART_SEC=5`, daemon startup delay 3s
- Venv moved to `/var/lib/dyndns/venv`
- Admin CLI (`config`/`import`/`export`) runs as caller; Python hands off file ownership to service user after write

### Removed
- `recent-logs` / `live-logs` commands (use `journalctl -u dyndns`)
- Service lifecycle actions from setup menu

## [1.0.3alpha04] - 2026-03-17
### Fixed
- Fix double logging 
- Fix comments
- Standardized help/version order

## [1.0.3alpha03] - 2026-02-21
### Added 
- Added explicit systemd timeouts (start: 60s, stop: 15s)
- Added offline-first Python dependency check before network install

### Changed
- Service restart policy from `on-failure` to `always` with exit code 0 prevention
- Reduced service restart delay from 10s to 5s
- Increased Python daemon startup check delay from 1s to 3s
- Export `DAEMON_MODE` to Python environment for logger configuration

## [1.0.3alpha02] - 2026-02-05
### Added
- `purge` command and `--purge` flag for complete removal including data directory
- Zone ID auto-fetch from provider API when adding new zones
- DynDNS record creation wizard after zone setup (Standard setup with @/www or Root domain only)

### Changed
- Data directory path from `/var/` to `/var/lib/`
- Restructured Python modules into `src/core/` and `src/utils/` subdirectories
- Refactored daemon mode handling: Bash wrapper controls daemon mode via DAEMON_MODE environment variable
- Python application reads DAEMON_MODE from environment instead of CLI argument
- Updated all docstrings to Google Style format

### Fixed
- Inconsistent configuration display between menu and application views
- PID file handling causing daemon start failures
- Database write access in systemd service (ReadWritePaths)
- Stop application handling
- Removed install-dependencies from runtime
- Process termination, PID file handling

## [1.0.3alpha01] - 2025-10-31
### Added
- System-wide command `ionos-dyndns` with setup system and backup/restore functionality.
- CLI commands for configuration management (config, import, export).
- Auto-create missing DNS records on provider during sync.
- Enhanced logging with daemon mode support.

### Changed
- Improved Bash wrapper with modular library system.
- Python application restructured with better error handling.
- Configuration via `config.toml`

## [1.0.2] - 2025-04-27
### Added
- Introduced `CHANGELOG.md` to track changes.

### Changed
- Improved user prompts and error handling in `setup.sh`.
- Updated installation instructions in `README.md`.

### Fixed
- Fixed multi-line string handling in Bash functions.

## [1.0.1] - 2025-04-18
### Changed
- Improved user prompts and error handling in `setup.sh`.
- Github handling

## [1.0.0] - 2025-04-17
### Added
- Initial release of IONOS DynDNS.
- Added Python script for dynamic DNS updates.
- Added `setup.sh` for automated installation.
- Added basic documentation (`README.md`).