# DynDNS

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://www.linux.org/)

Automatically update IONOS DNS records (A/AAAA) for domains with dynamic IP addresses. Built for reliability with encrypted API key storage, systemd integration, and interactive CLI configuration.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/manuelziel/dyndns.git
cd dyndns
sudo ./setup.sh

# 2. Configure zones and API keys
sudo dyndns config

# 3. Enable and start service
sudo systemctl enable --now dyndns
```
---

## Requirements

- IONOS account with DNS API access ([Get API credentials](https://developer.hosting.ionos.de/docs/dns))
- Python 3.11 or higher
- Linux system with systemd (for daemon mode)
- Existing DNS zone for your domain

---

## Installation

```bash
# Clone and install
git clone https://github.com/manuelziel/dyndns.git
cd dyndns
sudo ./setup.sh
```

**Options**: `--force` (reinstall), `--interactive` (menu mode)

---

## Configuration

### Interactive Setup

```bash
sudo dyndns config
```

You'll be prompted for:
- **Zone name**: Your domain (e.g., `example.com`)
- **API credentials**: IONOS Bulk ID and API Key
- **DNS records**: A/AAAA records to manage (e.g., `@`, `www`)

### Configuration File

Edit `/etc/dyndns/config.toml` for advanced settings:

```toml
[debug]
level = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

[network]
ipv4_enabled = true
ipv6_enabled = true

[daemon]
check_interval = 300  # Check IP every 5 minutes
sync_checks = true  # Enable automatic orphan detection (recommended)
```

**Note**: Zones and API credentials are stored in database, not config file. Use `sudo dyndns config` to manage.

---

## Usage

### Service Management

```bash
# Start/stop/restart
sudo systemctl start dyndns
sudo systemctl stop dyndns
sudo systemctl restart dyndns

# Enable auto-start on boot
sudo systemctl enable --now dyndns

# Check service status
sudo systemctl status dyndns
```

### View Logs

```bash
# Last 50 lines (no pager)
sudo journalctl -u dyndns -n 50 --no-pager

# Follow live
sudo journalctl -u dyndns -f

# Filter by time
sudo journalctl -u dyndns --since "1 hour ago"
sudo journalctl -u dyndns --since today

# Only errors/warnings
sudo journalctl -u dyndns -p warning
```

### Backup/Restore

```bash
# Export configuration
sudo dyndns export --output backup.yaml

# Import configuration
sudo dyndns import backup.yaml --overwrite
```

**Note**: Export creates `~/config-export_YYYYMMDD_HHMMSS.yaml` by default. Records auto-sync on next daemon run after import.

---

## Sync Operations

### Automatic Daemon Sync (Recommended)

The daemon automatically handles synchronization when `sync_checks = true` (enabled by default):

- **Orphan Detection**: Detects deleted records → marks as orphaned → recreates automatically
- **Provider ID Recovery**: Missing provider_record_id → syncs zone → recreates record
- **Self-Healing**: No manual intervention needed

### Manual Sync Options

**Zone Sync** - Reconcile database with provider:
```bash
sudo dyndns config -> "2. Manage records" -> "5. Sync records from provider"
```
Use when: After import, manual changes at IONOS dashboard, or to verify sync status

**Force Update** - Update all records immediately:
```bash
sudo dyndns config -> "4. Force DNS Update"
```
Use when: Testing, force IP refresh, or records deleted from provider

---

## Troubleshooting

### Service Issues

```bash
# Check status and logs
sudo systemctl status dyndns
sudo journalctl -u dyndns -n 50

# Restart service
sudo systemctl restart dyndns
```

### API/Network Issues

- **Authentication error:** Update credentials via `sudo dyndns config`
- **IPv6 disabled:** Edit `config.toml` -> `ipv6_enabled = false`
- **Firewall:** Ensure HTTPS (443) outbound allowed

### Reinstall / Uninstall

```bash
# Keep config
sudo ./setup.sh install --force

# Fresh install (removes config but keeps data)
sudo ./setup.sh uninstall
sudo ./setup.sh install

# Complete removal including all data
sudo ./setup.sh purge
# or
sudo ./setup.sh uninstall --purge
```

---

## Advanced

- **Encryption**: API keys use Fernet (AES-128-CBC with HMAC-SHA256). Key at `/var/lib/dyndns/.encryption_key` (0600 permissions)
- **Backup encryption key**: `sudo cp /var/lib/dyndns/.encryption_key ~/backup.key`
- **Export/Import**: Export creates YAML with decrypted API keys for editing
- **Systemd**: Service is hardened with `ProtectSystem=full`, `PrivateTmp`, `NoNewPrivileges` (see `SERVICE_*` in `lib/core/config.sh`). Logs via `journalctl -u dyndns`

---

## Contributing

Contributions welcome! Open an issue or submit a pull request on [GitHub](https://github.com/manuelziel/dyndns).

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

## Contact

**Author**: Manuel Ziel  
**GitHub**: [manuelziel](https://github.com/manuelziel)  
**IONOS DNS API**: [Developer Documentation](https://developer.hosting.ionos.de/docs/dns)