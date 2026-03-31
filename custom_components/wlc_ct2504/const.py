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
SNMP_VERSION_OPTIONS = [SNMP_VERSION_2C]  # CT2504 suporta doar v1/v2c

# ── OID DEFINITIONS ──────────────────────────────────────────────
# Standard MIBs
OID_SYS_DESCR   = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME  = "1.3.6.1.2.1.1.3.0"
OID_SYS_NAME    = "1.3.6.1.2.1.1.5.0"
OID_SERIAL      = "1.3.6.1.2.1.47.1.1.1.1.11.1"

# CISCO-LWAPP-SYS-MIB (bsOperating)
OID_CPU         = "1.3.6.1.4.1.14179.1.1.5.1.0"
OID_MEM_FREE    = "1.3.6.1.4.1.14179.1.1.5.2.0"
OID_MEM_TOTAL   = "1.3.6.1.4.1.14179.1.1.5.3.0"
OID_FLASH       = "1.3.6.1.4.1.14179.1.1.5.4.0"
OID_TEMPERATURE = "1.3.6.1.4.1.14179.1.1.6.1.0"
OID_MGMT_IP     = "1.3.6.1.4.1.14179.1.1.1.4.0"
OID_AP_MGR_IP   = "1.3.6.1.4.1.14179.1.1.1.7.0"

# CISCO-LWAPP-DOT11-MIB
OID_RF_COUNTRY  = "1.3.6.1.4.1.14179.2.3.1.2.0"
OID_CAPWAP      = "1.3.6.1.4.1.14179.2.3.1.29.0"

# Clients total
OID_CLIENTS_TOTAL = "1.3.6.1.4.1.14179.2.1.1.1.38.0"

# AP Table base OIDs (append .<ap_index>)
OID_AP_NAME     = "1.3.6.1.4.1.14179.2.2.1.1.3"
OID_AP_STATUS   = "1.3.6.1.4.1.14179.2.2.1.1.6"
OID_AP_MODEL    = "1.3.6.1.4.1.14179.2.2.1.1.16"
OID_AP_IP       = "1.3.6.1.4.1.14179.2.2.1.1.19"
OID_AP_CLIENTS  = "1.3.6.1.4.1.14179.2.2.1.1.38"

# AP Radio Table (append .<ap_index>.<slot>)  slot 0=2.4GHz, 1=5GHz
OID_AP_CHANNEL  = "1.3.6.1.4.1.14179.2.2.2.1.4"
OID_AP_TXPOWER  = "1.3.6.1.4.1.14179.2.2.2.1.6"
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
