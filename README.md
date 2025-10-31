# IONOS DynDNS

[![Python](https://img.shields.io/badge/python-3.6%2B-blue.svg)](https://www.python.org/)
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
ionos-dyndns config

# 3. Start service
sudo systemctl start ionos-dyndns
sudo systemctl enable ionos-dyndns
```
---

## Requirements

- IONOS account with DNS API access ([Get API credentials](https://developer.hosting.ionos.de/docs/dns))
- Python 3.6 or higher
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
ionos-dyndns config
```

You'll be prompted for:
- **Zone name**: Your domain (e.g., `example.com`)
- **API credentials**: IONOS Bulk ID and API Key
- **DNS records**: A/AAAA records to manage (e.g., `@`, `www`, `mail`)

### Configuration File

Edit `/usr/local/share/ionos-dyndns/config.toml` for advanced settings:

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

**Note**: Zones and API credentials are stored in database, not config file. Use `ionos-dyndns config` to manage.

---

## Usage

### Service Management

```bash
# Start/stop/restart
sudo systemctl start ionos-dyndns
sudo systemctl restart ionos-dyndns

# Enable auto-start on boot
sudo systemctl enable ionos-dyndns

# View logs
sudo journalctl -u ionos-dyndns -f
```

### Backup/Restore

```bash
# Export configuration
ionos-dyndns export --output backup.yaml

# Import configuration
ionos-dyndns import backup.yaml --overwrite
```

**Note**: Export creates `~/dyndns-export_YYYYMMDD_HHMMSS.yaml` by default. Records auto-sync on next daemon run after import.

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
ionos-dyndns config → "2. Manage records" → "5. Sync records from provider"
```
Use when: After import, manual changes at IONOS dashboard, or to verify sync status

**Force Update** - Update all records immediately:
```bash
ionos-dyndns config → "4. Force DNS Update"
```
Use when: Testing, force IP refresh, or records deleted from provider

---

## Troubleshooting

### Service Issues

```bash
# Check status and logs
sudo systemctl status ionos-dyndns
sudo journalctl -u ionos-dyndns -n 50

# Restart service
sudo systemctl restart ionos-dyndns
```

### Sync Issues

**Records out of sync:** Run `ionos-dyndns config` → "2. Manage records" → "5. Sync records from provider"

**Missing provider IDs:** Auto-fixed by daemon when `sync_checks = true` (default)

**Check sync status:**
```bash
sqlite3 /usr/local/share/ionos-dyndns/db.db "SELECT record_name, record_type, sync_status FROM records;"
```

**Sync status values:** `synced` (up to date), `local_only` (no API), `orphaned` (deleted at provider)

### API/Network Issues

- **Authentication error:** Update credentials via `ionos-dyndns config`
- **IPv6 disabled:** Edit `config.toml` → `ipv6_enabled = false`
- **Firewall:** Ensure HTTPS (443) outbound allowed

### Reinstall

```bash
# Keep config
sudo ./setup.sh install --force

# Fresh install (removes config)
sudo ./setup.sh uninstall
sudo ./setup.sh install
```

---

## Advanced

- **Encryption**: API keys use Fernet (AES-128 CBC). Key at `/usr/local/share/ionos-dyndns/.encryption_key` (0600 permissions)
- **Backup encryption key**: `sudo cp /usr/local/share/ionos-dyndns/.encryption_key ~/backup.key`
- **Export/Import**: Export creates YAML with decrypted API keys for editing
- **Systemd**: Service runs as root for network access. Logs via `journalctl -u ionos-dyndns`

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