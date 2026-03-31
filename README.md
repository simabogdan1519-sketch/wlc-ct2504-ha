# Cisco WLC CT2504 — Home Assistant Integration

<p align="center">
  <img src="docs/card-preview.png" alt="WLC Card Preview" width="680"/>
</p>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-orange?logo=home-assistant&logoColor=white" alt="HACS Custom"/></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1+-41BDF5?logo=home-assistant&logoColor=white" alt="HA Version"/></a>
  <img src="https://img.shields.io/badge/Protocol-SNMP%20v2c-blue" alt="SNMP v2c"/>
  <img src="https://img.shields.io/badge/Polling-Local-green" alt="Local Polling"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License"/>
</p>

> Native Home Assistant integration for the **Cisco Wireless LAN Controller CT2504** (AIR-CT2504-K9).  
> Connects via SNMP v2c, auto-discovers all APs and SSIDs, and creates sensor entities for everything — no YAML entity config needed.

---

## ✨ Features

- **GUI config flow** — set up entirely from the HA UI, no YAML required
- **Auto-discovery** — finds all registered APs and SSIDs via SNMP walk at setup time
- **Live polling** — separate fast/slow intervals for clients vs system stats
- **Full sensor coverage** — CPU, memory, flash, temperature, uptime, per-AP status/clients/channel/TxPower, per-SSID clients/VLAN/security/band
- **Options flow** — change poll intervals and community string without reinstalling
- **Dark industrial Lovelace card** — matching dashboard card included (`wlc-card.js`)
- **Romanian + English UI** — translations for both languages

---

## 📦 What's Included

```
custom_components/wlc_ct2504/
├── __init__.py            # Integration setup & entry management
├── manifest.json          # HA integration manifest
├── const.py               # All SNMP OIDs and constants
├── snmp_client.py         # Async SNMP v2c client (pysnmp)
├── coordinator.py         # DataUpdateCoordinator + SNMP discovery
├── config_flow.py         # GUI config flow + options flow
├── sensor.py              # All sensor entities
├── strings.json           # UI label definitions
└── translations/
    ├── en.json            # English
    └── ro.json            # Romanian

lovelace/
└── wlc-card.js            # Custom Lovelace card (dark industrial theme)
```

---

## 🖥️ Sensors Created

### System
| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.wlc_cpu_usage` | CPU utilization (5-min avg) | % |
| `sensor.wlc_memory_usage` | RAM used | % |
| `sensor.wlc_flash_usage` | Flash storage used | % |
| `sensor.wlc_temperature` | Chassis temperature | °C |
| `sensor.wlc_uptime` | Controller uptime | — |
| `sensor.wlc_firmware_version` | Software version | — |
| `sensor.wlc_capwap_status` | CAPWAP tunnel status | — |
| `sensor.wlc_rf_country` | RF regulatory domain | — |

### Clients
| Entity | Description |
|--------|-------------|
| `sensor.wlc_clients_total` | All associated clients |
| `sensor.wlc_clients_24ghz` | Clients on 2.4 GHz radio |
| `sensor.wlc_clients_5ghz` | Clients on 5 GHz radio |

### Access Points *(one set per AP, auto-discovered)*
| Entity | Description |
|--------|-------------|
| `sensor.wlc_ap_<n>_status` | `associated` / `down` |
| `sensor.wlc_ap_<n>_clients` | Total clients on AP |
| `sensor.wlc_ap_<n>_channel_24` | Active 2.4 GHz channel |
| `sensor.wlc_ap_<n>_channel_5` | Active 5 GHz channel |
| `sensor.wlc_ap_<n>_txpower_24` | Tx power 2.4 GHz (dBm) |
| `sensor.wlc_ap_<n>_txpower_5` | Tx power 5 GHz (dBm) |

### SSIDs *(one set per WLAN, auto-discovered)*
| Entity | Description |
|--------|-------------|
| `sensor.wlc_ssid_<n>_clients` | Associated clients |
| `sensor.wlc_ssid_<n>_security` | `Open` / `WPA2` / `WPA3` |
| `sensor.wlc_ssid_<n>_band` | `2.4` / `5` / `dual` |
| `sensor.wlc_ssid_<n>_vlan` | VLAN ID |

---

## 🔧 Prerequisites

### On the WLC (CLI)
SNMP v2c must be enabled before adding the integration. Connect via SSH or the serial console:

```
config snmp community create public
config snmp community accessmode ro public
config snmp community ipaddr <HA_IP> 255.255.255.255 public
config snmp version v2c enable
save config
```

> Replace `<HA_IP>` with your Home Assistant server IP, or use `0.0.0.0` to allow any source (less secure).

**Verify from a Linux machine:**
```bash
snmpwalk -v2c -c public <WLC_IP> 1.3.6.1.2.1.1
```
You should see the sysDescr and related fields. If you get a timeout, SNMP is not enabled or the community ACL is blocking you.

---

## 📥 Installation

### Option A — HACS (recommended)

1. Open HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add URL: `https://github.com/your-username/wlc-ct2504-ha`  
   Category: **Integration**
3. Find **Cisco WLC CT2504** in HACS and click **Download**
4. Restart Home Assistant

### Option B — Manual

1. Download the [latest release](https://github.com/your-username/wlc-ct2504-ha/releases/latest) zip
2. Extract and copy the `wlc_ct2504` folder to:
   ```
   /config/custom_components/wlc_ct2504/
   ```
3. Restart Home Assistant

---

## ⚙️ Configuration

After installation and restart:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Cisco WLC CT2504**
3. Fill in the form:

| Field | Description | Default |
|-------|-------------|---------|
| **WLC IP Address** | Management IP of the controller | — |
| **SNMP Community** | Read-only community string | `public` |
| **SNMP Port** | UDP port | `161` |
| **Device Name** | Friendly name in HA | `Cisco WLC 2504` |

4. The integration will connect, run an SNMP walk, and show you a **discovery summary** with all APs and SSIDs found before you confirm.

### Options (post-install)

Click **Configure** on the integration card to change:
- System poll interval (default 30s)
- Client poll interval (default 15s)  
- SNMP community string

---

## 📊 Lovelace Card

A matching custom card is included in `lovelace/wlc-card.js`.

### Install the card

Copy `wlc-card.js` to `/config/www/wlc-card.js`, then add the resource in HA:

**Settings → Dashboards → ⋮ → Resources → Add Resource**
```
URL:  /local/wlc-card.js
Type: JavaScript Module
```

Restart or reload the browser.

### Add to dashboard

```yaml
type: custom:wlc-card
prefix: wlc_ct2504
```

Optional overrides:
```yaml
type: custom:wlc-card
prefix: wlc_ct2504
title: "My WLC"        # override card title
```

That's it — the card autodiscovers everything from the prefix.

---

## 🗂️ SNMP OID Reference

Key OIDs used by this integration (Cisco AIR-MIB / CISCO-LWAPP-*):

| OID | Description |
|-----|-------------|
| `1.3.6.1.4.1.14179.1.1.5.1.0` | CPU utilization 5-min |
| `1.3.6.1.4.1.14179.1.1.5.2.0` | Free memory (bytes) |
| `1.3.6.1.4.1.14179.1.1.5.3.0` | Total memory (bytes) |
| `1.3.6.1.4.1.14179.1.1.5.4.0` | Flash usage % |
| `1.3.6.1.4.1.14179.1.1.6.1.0` | Chassis temperature |
| `1.3.6.1.4.1.14179.2.2.1.1.3.<n>` | AP name (index n) |
| `1.3.6.1.4.1.14179.2.2.1.1.6.<n>` | AP status (1=up) |
| `1.3.6.1.4.1.14179.2.2.1.1.38.<n>` | AP client count |
| `1.3.6.1.4.1.14179.2.2.2.1.4.<n>.<s>` | AP channel (slot s) |
| `1.3.6.1.4.1.14179.2.1.1.1.2.<w>` | SSID name (WLAN w) |
| `1.3.6.1.4.1.14179.2.1.1.1.38.<w>` | SSID client count |
| `1.3.6.1.4.1.14179.2.1.1.1.61.<w>` | SSID VLAN ID |

> Full OID table in [`custom_components/wlc_ct2504/const.py`](custom_components/wlc_ct2504/const.py)

---

## ⚠️ Known Limitations

- **SNMP v2c only** — CT2504 firmware 8.x does not support SNMPv3 in a way that's reliably readable by pysnmp without enterprise MIB files
- **AP indexes are not stable** — they depend on association order and may shift after a WLC reboot. If AP data appears on the wrong entity after a reboot, go to **Settings → Devices & Services → WLC → Configure** and click **Re-discover** (coming in v1.1)
- **Max 25 APs** — hardware limit of the CT2504 license

---

## 🗺️ Roadmap

- [ ] Re-discover button in options flow (refresh AP/SSID indexes)
- [ ] Binary sensor for AP up/down (for automations/alerts)
- [ ] HACS default repository submission
- [ ] Support for CT5508 / CT8510 (same MIBs, different scale)

---

## 🤝 Contributing

Pull requests are welcome. For major changes, open an issue first.

```bash
# Clone
git clone https://github.com/your-username/wlc-ct2504-ha.git
cd wlc-ct2504-ha

# Test locally — copy to your HA config
cp -r custom_components/wlc_ct2504 /path/to/ha/config/custom_components/
```

Please follow the existing code style and test against a real CT2504 or a mock SNMP agent before submitting.

---

## 📄 License

[MIT](LICENSE) © 2024

---

<p align="center">
  Built for home lab use · Tested on WLC CT2504 firmware 8.10.185.0
</p>
