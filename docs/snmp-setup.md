# SNMP Setup Guide — Cisco WLC CT2504

This guide covers everything you need to configure SNMP on the WLC before adding the integration.

---

## Enable SNMP on the WLC

Connect to the WLC via SSH or the serial console and run:

```
config snmp community create public
config snmp community accessmode ro public
config snmp community ipaddr <HA_IP> 255.255.255.255 public
config snmp version v2c enable
save config
```

Replace `<HA_IP>` with the IP of your Home Assistant server.

> **Tip:** Use `0.0.0.0 0.0.0.0` instead of a specific IP to allow any source — useful during setup, but tighten it afterwards.

### Verify from a Linux machine

```bash
# Basic connectivity (sysDescr)
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.2.1.1

# Check AP table
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.4.1.14179.2.2.1.1.3

# Check SSID table
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.4.1.14179.2.1.1.1.2
```

If you get a timeout, SNMP is not enabled or the ACL is blocking you.  
If you get `No Such Object`, the OID is correct but the MIB table is empty (no APs registered yet).

---

## Finding AP indexes

AP indexes in the WLC MIB are assigned in association order and are **not stable** across reboots. Before the integration's auto-discovery runs, you can check them manually:

```bash
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.4.1.14179.2.2.1.1.3
```

Example output:
```
SNMPv2-SMI::enterprises.14179.2.2.1.1.3.1 = STRING: "AP-Living"
SNMPv2-SMI::enterprises.14179.2.2.1.1.3.2 = STRING: "AP-Office"
SNMPv2-SMI::enterprises.14179.2.2.1.1.3.3 = STRING: "AP-Terrace"
SNMPv2-SMI::enterprises.14179.2.2.1.1.3.4 = STRING: "AP-Garage"
```

The last number in each OID (`.1`, `.2`, `.3`, `.4`) is the AP index. These are the indexes the integration uses.

> If APs get different indexes after a WLC reboot, the sensor names will be wrong. A **Re-discover** option is planned for v1.1.

---

## Full OID Reference

### System — CISCO-LWAPP-SYS-MIB

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.2.1.1.1.0` | sysDescr | Model + firmware string |
| `1.3.6.1.2.1.1.3.0` | sysUpTime | Uptime in TimeTicks (centiseconds) |
| `1.3.6.1.2.1.1.5.0` | sysName | WLC hostname |
| `1.3.6.1.2.1.47.1.1.1.1.11.1` | entPhysicalSerialNum | Serial number |
| `1.3.6.1.4.1.14179.1.1.5.1.0` | bsOperCpuUsage5Min | CPU 5-min avg % |
| `1.3.6.1.4.1.14179.1.1.5.2.0` | bsOperMemoryFree | Free memory bytes |
| `1.3.6.1.4.1.14179.1.1.5.3.0` | bsOperMemorySize | Total memory bytes |
| `1.3.6.1.4.1.14179.1.1.5.4.0` | bsOperFlashUsage | Flash usage % |
| `1.3.6.1.4.1.14179.1.1.6.1.0` | bsOperTemperature | Temperature °C |
| `1.3.6.1.4.1.14179.1.1.1.4.0` | bsnMgmtInterfaceIPAddress | Management IP |
| `1.3.6.1.4.1.14179.1.1.1.7.0` | bsnApManagerIPAddress | AP-manager IP |

### Wireless Global — CISCO-LWAPP-DOT11-MIB

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.4.1.14179.2.3.1.2.0` | bsnRFNetworkName | RF country code |
| `1.3.6.1.4.1.14179.2.3.1.29.0` | bsnSyslogEnable | CAPWAP active (1=yes) |

### Clients

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.4.1.14179.2.1.1.1.38.0` | bsClientTotalCount | Total associated clients |
| `1.3.6.1.4.1.14179.2.2.2.1.15.<ap>.<slot>` | bsnAPIfLoadNumAssociation | Clients per AP radio |

### AP Table — bsnAPTable (index = AP ordinal)

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.4.1.14179.2.2.1.1.3.<n>` | bsnAPName | AP name |
| `1.3.6.1.4.1.14179.2.2.1.1.6.<n>` | bsnAPOperationStatus | 1=associated, 2=disassociating, 3=downloading |
| `1.3.6.1.4.1.14179.2.2.1.1.16.<n>` | bsnAPModel | AP model string |
| `1.3.6.1.4.1.14179.2.2.1.1.19.<n>` | bsnApIpAddress | AP IP address |
| `1.3.6.1.4.1.14179.2.2.1.1.38.<n>` | bsnAPNumOfClientsOnAP | Total clients on AP |

### AP Radio Table — bsnAPIfTable (index = AP.slot, slot 0=2.4GHz, 1=5GHz)

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.4.1.14179.2.2.2.1.4.<n>.<s>` | bsnAPIfPhyChannelNumber | Active channel |
| `1.3.6.1.4.1.14179.2.2.2.1.6.<n>.<s>` | bsnAPIfPhyTxPowerLevel | Tx power dBm |
| `1.3.6.1.4.1.14179.2.2.2.1.15.<n>.<s>` | bsnAPIfLoadNumAssociation | Clients on radio |

### WLAN/SSID Table — bsnDot11EssTable (index = WLAN ID)

| OID | Name | Description |
|-----|------|-------------|
| `1.3.6.1.4.1.14179.2.1.1.1.2.<w>` | bsnDot11EssSsid | SSID name |
| `1.3.6.1.4.1.14179.2.1.1.1.38.<w>` | bsnDot11EssNumberOfMobileStations | Client count |
| `1.3.6.1.4.1.14179.2.1.1.1.61.<w>` | bsnDot11EssVlanIdentifier | VLAN ID |
| `1.3.6.1.4.1.14179.2.1.1.1.19.<w>` | bsnDot11EssSecurityAuthType | 0=Open, 4=WPA2, 6=WPA2-Ent, 8=WPA3 |
| `1.3.6.1.4.1.14179.2.1.1.1.29.<w>` | bsnDot11EssRadioPolicy | 0=all, 1=5GHz, 2=2.4GHz |
