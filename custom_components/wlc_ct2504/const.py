"""Constants for Cisco WLC CT2504 integration."""

DOMAIN = "wlc_ct2504"
DEFAULT_NAME = "Cisco WLC 2504"
DEFAULT_PORT = 161
DEFAULT_COMMUNITY = "public"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_SCAN_INTERVAL_CLIENTS = 15
DEFAULT_SCAN_INTERVAL_SLOW = 300

CONF_COMMUNITY = "community"
CONF_SNMP_VERSION = "snmp_version"
CONF_SCAN_INTERVAL_CLIENTS = "scan_interval_clients"

SNMP_VERSION_2C = "2c"
SNMP_VERSION_OPTIONS = [SNMP_VERSION_2C]

# ── OID DEFINITIONS ──────────────────────────────────────────────
# Standard MIBs
OID_SYS_DESCR   = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME  = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME    = "1.3.6.1.2.1.1.5.0"
OID_SERIAL      = "1.3.6.1.2.1.47.1.1.1.1.11.1"

# CISCO-LWAPP-SYS-MIB (bsOperating)
OID_CPU         = "1.3.6.1.4.1.14179.1.1.5.1.0"
OID_MEM_FREE    = "1.3.6.1.4.1.14179.1.1.5.2.0"   # free memory KB
OID_MEM_USED    = "1.3.6.1.4.1.14179.1.1.5.3.0"   # used memory KB (NOT total — naming in MIB is misleading)
OID_FLASH       = "1.3.6.1.4.1.14179.1.1.5.4.0"
OID_TEMPERATURE = "1.3.6.1.4.1.14179.1.1.6.1.0"

# NOTE: OID_MGMT_IP (1.4.0) actually returns serial on some firmware versions.
# We skip it and use sysName instead.
OID_AP_MGR_IP   = "1.3.6.1.4.1.14179.1.1.1.7.0"

# CISCO-LWAPP-DOT11-MIB
# bsnRFNetworkName (2.3.1.2.0) returns a numeric index on some firmware,
# not the country string. We skip it.
OID_CAPWAP      = "1.3.6.1.4.1.14179.2.3.1.29.0"

# Clients total — OID .0 unreliable on CT2504, computed from radio sums instead
OID_CLIENTS_TOTAL = "1.3.6.1.4.1.14179.2.1.1.1.38.0"

# AP Table base OIDs (append .<mac_suffix>)
OID_AP_NAME     = "1.3.6.1.4.1.14179.2.2.1.1.3"
OID_AP_STATUS   = "1.3.6.1.4.1.14179.2.2.1.1.6"
OID_AP_MODEL    = "1.3.6.1.4.1.14179.2.2.1.1.16"
OID_AP_IP       = "1.3.6.1.4.1.14179.2.2.1.1.19"   # returned as hex IP
OID_AP_CLIENTS  = "1.3.6.1.4.1.14179.2.2.1.1.38"

# AP Radio Table (append .<mac_suffix>.<slot>)  slot 0=2.4GHz, 1=5GHz
OID_AP_CHANNEL       = "1.3.6.1.4.1.14179.2.2.2.1.4"
OID_AP_TXPOWER       = "1.3.6.1.4.1.14179.2.2.2.1.6"   # index 1-8, not dBm
OID_AP_CLIENTS_RADIO = "1.3.6.1.4.1.14179.2.2.2.1.15"

# WLAN/SSID Table (append .<wlan_id>)
OID_SSID_NAME     = "1.3.6.1.4.1.14179.2.1.1.1.2"
OID_SSID_CLIENTS  = "1.3.6.1.4.1.14179.2.1.1.1.38"
OID_SSID_VLAN     = "1.3.6.1.4.1.14179.2.1.1.1.61"
OID_SSID_SECURITY = "1.3.6.1.4.1.14179.2.1.1.1.19"
OID_SSID_BAND     = "1.3.6.1.4.1.14179.2.1.1.1.29"
OID_SSID_STATUS   = "1.3.6.1.4.1.14179.2.1.1.1.6"

# Value mappings
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

# TxPower index → dBm (AIR-CAP3702, 3 dBm steps)
# Index 1 = max power (~20 dBm), index 8 = min power
TXPOWER_INDEX_TO_DBM = {
    "1": 20, "2": 17, "3": 14, "4": 11,
    "5": 8,  "6": 5,  "7": 2,  "8": -1,
}
