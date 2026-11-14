# DynDNS

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)](https://www.linux.org/)

Automatically update IONOS DNS records (`A`/`AAAA`) for domains with dynamic IPv4/IPv6 addresses. Built for unattended reliability on Linux & Raspberry Pi OS with Fernet-encrypted credential storage, wear-leveled SQLite WAL persistence, native systemd journald socket logging, and interactive CLI management.

---

## Applied Standards & Specifications

| Domain          | Standards                              | Scope in DynDNS                    |
| --------------- | -------------------------------------- | ---------------------------------- |
| DNS & Naming    | `RFC 1035`, `RFC 2136`, `RFC 3596`     | Domain syntax, `A`/`AAAA` & TTL    |
| IP Addressing   | `RFC 791`, `RFC 4291`, `EUI-64`        | Strict IP validation & SLAAC guide |
| HTTP & REST API | `RFC 9110`, `RFC 6585` (`429`)         | Session pool, `updateUrl` & retry  |
| System & Init   | `FHS 3.0`, `POSIX.1`, `systemd(5)`     | FHS paths, signals & strict unit   |
| CLI & TUI UX    | `POSIX.1-2017`, `clig.dev`, `NO_COLOR` | Stream split, symbols & safe menus |
| App Security    | `OWASP ASVS 4.0`, `API Top 10`         | URI/key redaction & `0640`/`0600`  |
| Cryptography    | `Fernet` (`AES-128-CBC`, `RFC 2104`)   | Encrypted API keys (`0600` key)    |
| Persistence     | `SQLite WAL`, `ACID`, `TOML 1.0`       | Wear-leveled WAL pool & config     |
| Governance      | `SemVer 2.0.0`, `PEP 8/484`, `MIT`     | `CHANGELOG` SSoT, DAG & types      |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/manuelziel/dyndns.git
cd dyndns
sudo ./setup.sh

# 2. Configure zones and API keys
sudo dyndns config

# 3. Validate TOML configuration (optional)
sudo dyndns validate

# 4. Enable and start service
sudo systemctl enable --now dyndns
```

---

## Requirements

- IONOS account with DNS API access ([Get API credentials](https://developer.hosting.ionos.de/docs/dns))
- Python 3.11 or higher
- Linux system with systemd (Debian, Ubuntu, Raspberry Pi OS)
- Existing DNS zone for your domain

---

## Installation

```bash
# Fresh installation
git clone https://github.com/manuelziel/dyndns.git
cd dyndns
sudo ./setup.sh install

# Update code, config & virtualenv in-place (preserves /var/lib/dyndns database & keys)
sudo ./setup.sh update
```

**Setup Actions**: `install`, `update`, `reinstall` (preserves `/var/lib/dyndns` database & encryption key, refreshes `/etc/dyndns/config.toml`), `uninstall` (keeps `/var/lib/dyndns`), `purge` (removes config & data), `--interactive` (menu mode).

---

## Configuration

### Interactive Setup

```bash
sudo dyndns config
```

You will be prompted for:
- **Zone name**: Your domain (`RFC 1035` validated, e.g. `example.com`)
- **API credentials**: IONOS Bulk ID and API Key (stored Fernet-encrypted in SQLite)
- **DNS records**: `A`/`AAAA` records to manage (e.g. `@`, `www`)

### Configuration File & Validation

Edit `/etc/dyndns/config.toml` (`0640` `root:dyndns`) for runtime settings and verify changes before restarting:

```toml
[debug]
level = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

[network]
ipv4_enabled = true
ipv6_enabled = true

[dns]
update_method = "dyndns"  # "dyndns" (native updateUrl) or "rest"
default_ttl = 3600

[daemon]
check_interval = 300  # Check IP every 5 minutes
sync_checks = true    # Enable automatic orphan detection (recommended)
```

```bash
# Validate active configuration or an arbitrary TOML file
sudo dyndns validate
./dyndns.py validate --file ./config.toml
```

**Note**: Zones and API credentials are stored encrypted in `/var/lib/dyndns/dyndns.db`, not in `config.toml`. Use `sudo dyndns config` to manage them.

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

# Filter by time or priority
sudo journalctl -u dyndns --since "1 hour ago"
sudo journalctl -u dyndns -p warning
```

### Backup / Restore

```bash
# Export configuration (creates restricted 0600 file; pure YAML/JSON when piped to stdout)
sudo dyndns export --output backup.yaml
sudo dyndns export --format json > backup.json

# Import configuration
sudo dyndns import backup.yaml --overwrite
```

---

## Sync Operations

### Automatic Daemon Sync & Self-Healing (Recommended)

The daemon (`dyndns.service`) automatically verifies and heals your DNS configuration at startup and on each check interval when `sync_checks = true`:

- **Orphan Detection & Recovery (`dyndns` + `rest` modes)**: Detects if configured `A`/`AAAA` records (`@`, `www`, etc.) were deleted on the IONOS dashboard and recreates missing entries automatically via `POST /v1/zones/{id}/records`.
- **DynDNS Bundle Auto-Binding (`dyndns` mode)**: After restoring missing subdomains on IONOS, the daemon activates a fresh DynDNS `updateUrl` bundle (`bulkId`) and executes it immediately with your current IPv4/IPv6.
- **Transient Outage Resilience**: If external IP detection endpoints temporarily time out, cached local IP state is preserved without triggering false updates or unnecessary flash writes.
- **Real-Time CLI Execution**: Adding, editing, or deleting records inside `sudo dyndns config` immediately updates the IONOS DynDNS bundle and executes the `updateUrl` in real time.

### Manual Sync Options

- **Zone Sync** (`sudo dyndns config -> 3) Manage DNS Records -> 5) Sync records from provider`): Reconcile local database state with remote provider records after manual dashboard changes or imports.
- **Force Update** (`sudo dyndns config -> 4) Force DNS Update`): Immediately push current public IPv4/IPv6 addresses to all enabled zones and records.

---

## Troubleshooting

### Service & API Issues

- **Service health**: Check `sudo systemctl status dyndns` and `sudo journalctl -u dyndns -n 50 --no-pager`.
- **Authentication error**: Update credentials via `sudo dyndns config`. Query tokens (`?q=...`) and `X-API-Key` headers are automatically redacted as `**REDACTED**` in logs.
- **IPv6 disabled**: Set `ipv6_enabled = false` in `/etc/dyndns/config.toml` and run `sudo dyndns validate`.
- **Firewall**: Ensure outbound HTTPS (`TCP 443`) is allowed.

### Server Network & Router Best Practices (IPv6 / Timeouts)

If DNS records update cleanly (`Record updated`), but browser access yields `ERR_CONNECTION_TIMED_OUT`, verify your host SLAAC and router port-forwarding settings:

#### 1. Force Permanent Static IPv6 Interface-ID (`EUI-64`)
Modern Linux distributions default to `RFC 7217` Stable-Privacy or `RFC 4941` temporary addresses, which can rotate the IPv6 suffix across reboots or prefix renewals while router port-forwarding still points to the old Interface-ID. Bind the suffix permanently to the hardware MAC (`eui64`):

```bash
# Identify active NetworkManager connection:
nmcli -f NAME,DEVICE connection show --active

# Disable privacy extensions and enforce EUI-64 MAC derivation:
sudo nmcli connection modify "Wired connection 1" ipv6.ip6-privacy 0 ipv6.addr-gen-mode eui64
sudo nmcli connection up "Wired connection 1"

# Verify permanent EUI-64 Interface-ID:
ip -br -6 a
```

#### 2. Synchronize Router Port Forwarding & Rebind Protection
- Set your router's **IPv6 Interface-ID** target to match the `EUI-64` suffix from `ip -br -6 a` and enable *"Always assign this Interface-ID"*.
- For LAN loopback access (`Split-Horizon DNS`), add your domains to the router's **DNS Rebind Protection** exception list.

### Update / Reinstall / Purge

```bash
# In-place update (refreshes binaries & /etc/dyndns/config.toml; preserves /var/lib/dyndns)
sudo ./setup.sh update

# Full reinstall preserving /var/lib/dyndns database, .encryption_key, and venv
sudo ./setup.sh reinstall

# Uninstall binaries/service while keeping /var/lib/dyndns data
sudo ./setup.sh uninstall

# Complete removal including /etc/dyndns and /var/lib/dyndns
sudo ./setup.sh purge
```

---

## Security & Architecture Highlights

- **Encryption at Rest**: API keys are encrypted with `Fernet` (`AES-128-CBC` + `HMAC-SHA256`, key file `/var/lib/dyndns/.encryption_key` enforced at `0600` without symlink traversal).
- **Log & URI Redaction**: `sanitize_log_uri()` across `PlainFormatter`, `ColoredFormatter`, and `RingBufferHandler` automatically strips `?q=...` DynDNS tokens and credentials before writing to `stderr` or `/run/systemd/journal/socket`.
- **Systemd Sandboxing**: Hardened unit (`StateDirectory=dyndns`, `ProtectSystem=full`, `ProtectHome=true`, `PrivateTmp=true`, `PrivateDevices=true`, `ProtectKernelTunables=true`, `ProtectControlGroups=true`, `NoNewPrivileges=true`, `RestrictSUIDSGID=true`, `LockPersonality=true`) running unprivileged as `dyndns`.

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
