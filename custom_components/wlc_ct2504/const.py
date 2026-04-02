"""Constants for Cisco WLC CT2504 integration — OIDs validated from device walk."""

DOMAIN = "wlc_ct2504"
DEFAULT_NAME = "Cisco WLC 2504"
DEFAULT_PORT = 161
DEFAULT_COMMUNITY = "public"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_SCAN_INTERVAL_CLIENTS = 15

CONF_COMMUNITY = "community"
CONF_SCAN_INTERVAL_CLIENTS = "scan_interval_clients"

# ── SYSTEM OIDs ───────────────────────────────────────────────────────────────
OID_SYS_DESCR    = "1.3.6.1.2.1.1.1.0"        # "Cisco Controller"
OID_SYS_UPTIME   = "1.3.6.1.2.1.1.3.0"        # "97 hours 16 min (35017400)" — parse parens
OID_SYS_NAME     = "1.3.6.1.2.1.1.5.0"        # "WLC-Magazin"
OID_SERIAL       = "1.3.6.1.2.1.47.1.1.1.1.11.1"  # "PSZ17421EY4"

# CISCO-LWAPP-SYS-MIB (validated from walk)
OID_INVENTORY_NAME = "1.3.6.1.4.1.14179.1.1.1.1.0"   # "Cisco Controller"
OID_MODEL          = "1.3.6.1.4.1.14179.1.1.1.3.0"   # "AIR-CT2504-K9"  ✓
OID_FIRMWARE       = "1.3.6.1.4.1.14179.1.1.1.14.0"  # "8.5.182.0"  ✓ (NOT sysDescr!)
OID_WLC_MAC        = "1.3.6.1.4.1.14179.1.1.1.9.0"   # "C0-8C-60-C7-40-00"

OID_CPU            = "1.3.6.1.4.1.14179.1.1.5.1.0"   # CPU 5min avg % (returns 0 when <1%)
OID_MEM_FREE       = "1.3.6.1.4.1.14179.1.1.5.2.0"   # Free memory KB (only memory OID available)
OID_TEMPERATURE    = "1.3.6.1.4.1.14179.1.1.5.3.0"   # Temperature in millidegrees C (/10000 = °C)

# ── CLIENTS ───────────────────────────────────────────────────────────────────
# .2.6.1.2.0 = 53 (associated clients) ✓ — validated from walk
# .2.6.1.1.0 = 197008 (bytes counter, NOT clients)

# ── AP TABLE (index = MAC suffix e.g. 0.167.66.179.98.192) ───────────────────
OID_AP_NAME    = "1.3.6.1.4.1.14179.2.2.1.1.3"    # AP name string
OID_AP_STATUS  = "1.3.6.1.4.1.14179.2.2.1.1.6"    # 1=associated, 2=disassoc, 3=downloading
OID_AP_MODEL   = "1.3.6.1.4.1.14179.2.2.1.1.16"   # e.g. AIR-CAP3702I-E-K9
OID_AP_IP      = "1.3.6.1.4.1.14179.2.2.1.1.19"   # Returns dotted IP string directly ✓
OID_AP_LOCATION= "1.3.6.1.4.1.14179.2.2.1.1.4"    # AP location string

# ── AP RADIO TABLE (index = MAC.slot, slot 0=2.4GHz, 1=5GHz) ─────────────────
OID_AP_CHANNEL       = "1.3.6.1.4.1.14179.2.2.2.1.4"    # Channel number
OID_AP_TXPOWER       = "1.3.6.1.4.1.14179.2.2.2.1.6"    # TxPower index 1-8
OID_AP_CLIENTS_RADIO = "1.3.6.1.4.1.14179.2.2.2.1.15"   # Clients per radio
OID_AP_CHANUTIL      = "1.3.6.1.4.1.14179.2.2.2.1.22"   # Chan util% (comma list, first=current)
OID_AP_RXUTIL        = "1.3.6.1.4.1.14179.2.2.2.1.23"   # RX utilization %

# ── WLAN / SSID TABLE (index = WLAN ID 1..N) ─────────────────────────────────
OID_SSID_NAME     = "1.3.6.1.4.1.14179.2.1.1.1.2"
OID_SSID_STATUS   = "1.3.6.1.4.1.14179.2.1.1.1.6"    # 1=enabled
OID_SSID_CLIENTS  = "1.3.6.1.4.1.14179.2.1.1.1.38"
OID_SSID_VLAN     = "1.3.6.1.4.1.14179.2.1.1.1.61"
OID_SSID_SECURITY = "1.3.6.1.4.1.14179.2.1.1.1.19"
OID_SSID_BAND     = "1.3.6.1.4.1.14179.2.1.1.1.29"

# ── PHYSICAL PORTS (ifTable / ifXTable, index 1-4) ───────────────────────────
# Port 5 is "Virtual Interface" — skip it
OID_IF_NAME       = "1.3.6.1.2.1.31.1.1.1.1"    # "GigabitEthernet0/0/1"
OID_IF_OPER       = "1.3.6.1.2.1.2.2.1.8"        # 1=up, 2=down
OID_IF_SPEED      = "1.3.6.1.2.1.2.2.1.5"        # bps (1000000000 = 1G)
OID_IF_IN_OCTETS  = "1.3.6.1.2.1.31.1.1.1.6"     # HC (64-bit) InOctets
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"    # HC (64-bit) OutOctets
OID_IF_IN_ERRORS  = "1.3.6.1.2.1.2.2.1.14"       # InErrors
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"       # OutErrors

PORT_INDEXES = [1, 2, 3, 4]  # Physical GigabitEthernet ports only (5 = virtual)

# ── VALUE MAPS ────────────────────────────────────────────────────────────────
AP_STATUS_MAP = {
    "1": "associated",
    "2": "disassociating",
    "3": "downloading",
}

SSID_SECURITY_MAP = {
    "0": "Open",
    "2": "WPA",
    "4": "WPA2",
    "6": "WPA2-Enterprise",
    "8": "WPA3",
}

SSID_BAND_MAP = {
    "0": "dual",
    "1": "5",
    "2": "2.4",
    "3": "2.4",
    "4": "dual",
}

# TxPower index (1=max power) → dBm, AIR-CAP3702 series
TXPOWER_INDEX_TO_DBM = {
    "1": 20, "2": 17, "3": 14, "4": 11,
    "5": 8,  "6": 5,  "7": 2,  "8": -1,
}
