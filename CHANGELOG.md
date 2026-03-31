# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2024-03-31

### Added
- Initial release
- GUI config flow with SNMP connectivity validation
- Auto-discovery of APs and SSIDs via SNMP walk at setup
- `DataUpdateCoordinator` with separate fast/slow poll intervals
- System sensors: CPU, memory, flash, temperature, uptime, firmware, CAPWAP status, RF country
- Client sensors: total, per 2.4 GHz radio, per 5 GHz radio
- Per-AP sensors: status, clients, channel (2.4/5 GHz), TxPower (2.4/5 GHz)
- Per-SSID sensors: clients, security type, band, VLAN
- Options flow to change poll intervals and community string post-install
- Lovelace card `wlc-card.js` — dark industrial theme, prefix-based autodiscovery
- Romanian and English translations
- HACS-compatible repository structure

---

## [Unreleased]

### Planned
- Re-discover button in options flow (refresh AP/SSID indexes without reinstall)
- Binary sensors for AP up/down (for automations and alerts)
- Support for CT5508 / CT8510 (same MIB structure)
- HACS default repository submission
