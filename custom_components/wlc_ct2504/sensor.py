"""Sensor platform for Cisco WLC CT2504."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_NAME
from .coordinator import WlcDataCoordinator

_LOGGER = logging.getLogger(__name__)


# ── STATIC SENSOR DESCRIPTIONS ───────────────────────────────────

@dataclass(frozen=True)
class WlcSensorEntityDescription(SensorEntityDescription):
    data_key: str = ""
    extra_attrs: list[str] | None = None


SYSTEM_SENSORS: tuple[WlcSensorEntityDescription, ...] = (
    WlcSensorEntityDescription(
        key="cpu",
        data_key="cpu",
        name="CPU Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chip",
    ),
    WlcSensorEntityDescription(
        key="memory",
        data_key="memory",
        name="Memory Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
    ),
    WlcSensorEntityDescription(
        key="flash",
        data_key="flash",
        name="Flash Usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
    ),
    WlcSensorEntityDescription(
        key="temperature",
        data_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    WlcSensorEntityDescription(
        key="uptime",
        data_key="uptime",
        name="Uptime",
        native_unit_of_measurement=None,
        icon="mdi:clock-outline",
    ),
    WlcSensorEntityDescription(
        key="firmware",
        data_key="firmware",
        name="Firmware Version",
        icon="mdi:tag-outline",
        entity_registry_enabled_default=False,
    ),
    WlcSensorEntityDescription(
        key="clients_total",
        data_key="clients_total",
        name="Clients Total",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account-multiple",
    ),
    WlcSensorEntityDescription(
        key="clients_24",
        data_key="clients_24",
        name="Clients 2.4GHz",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
    ),
    WlcSensorEntityDescription(
        key="clients_5",
        data_key="clients_5",
        name="Clients 5GHz",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
    ),
    WlcSensorEntityDescription(
        key="ap_total",
        data_key="ap_total",
        name="AP Total",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:router-wireless",
    ),
    WlcSensorEntityDescription(
        key="ap_up",
        data_key="ap_up",
        name="AP Online",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:router-wireless",
    ),
    WlcSensorEntityDescription(
        key="ap_down",
        data_key="ap_down",
        name="AP Offline",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:router-wireless-off",
    ),
    WlcSensorEntityDescription(
        key="ssid_total",
        data_key="ssid_total",
        name="SSID Count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:access-point-network",
    ),
    WlcSensorEntityDescription(
        key="capwap",
        data_key="capwap",
        name="CAPWAP Status",
        icon="mdi:lan-connect",
        entity_registry_enabled_default=False,
    ),
    WlcSensorEntityDescription(
        key="rf_country",
        data_key="rf_country",
        name="RF Country",
        icon="mdi:flag-outline",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WLC sensors from config entry."""
    coordinator: WlcDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    host        = entry.data["host"]

    device_info = DeviceInfo(
        identifiers={(DOMAIN, host)},
        name=device_name,
        manufacturer="Cisco",
        model="AIR-CT2504-K9",
        sw_version=coordinator.data.get("firmware", "Unknown") if coordinator.data else None,
        configuration_url=f"https://{host}",
    )

    entities: list[SensorEntity] = []

    # ── System sensors ────────────────────────────────────────
    for description in SYSTEM_SENSORS:
        entities.append(
            WlcSystemSensor(coordinator, description, device_info, device_name)
        )

    # ── Per-AP sensors ────────────────────────────────────────
    for ap_suffix in coordinator.ap_indexes:
        # Get friendly name from coordinator data if available
        ap_data = {}
        if coordinator.data:
            ap_data = coordinator.data.get("aps", {}).get(ap_suffix, {})
        ap_name = ap_data.get("name") or f"AP-{ap_suffix}"
        ap_slug = ap_data.get("slug") or f"ap_{ap_suffix.replace('.', '_')}"

        for key, label, icon, unit in [
            ("status",  "Status",       "mdi:access-point",      None),
            ("clients", "Clients",      "mdi:account-multiple",  None),
            ("ch24",    "Channel 2.4G", "mdi:wifi",              None),
            ("ch5",     "Channel 5G",   "mdi:wifi",              None),
            ("tx24",    "TxPower 2.4G", "mdi:signal",            "dBm"),
            ("tx5",     "TxPower 5G",   "mdi:signal",            "dBm"),
        ]:
            entities.append(
                WlcApSensor(
                    coordinator=coordinator,
                    ap_idx=ap_suffix,
                    data_key=key,
                    entity_key=f"{ap_slug}_{key}",
                    name=f"{ap_name} {label}",
                    icon=icon,
                    unit=unit,
                    device_info=device_info,
                    device_name=device_name,
                )
            )

    # ── Per-SSID sensors ──────────────────────────────────────
    for ssid_idx in coordinator.ssid_indexes:
        ssid_name = f"WLAN-{ssid_idx}"
        if coordinator.data:
            ssid_name = coordinator.data.get("ssids", {}).get(ssid_idx, {}).get("name", f"WLAN-{ssid_idx}")

        for key, label, icon in [
            ("clients",  "Clients",  "mdi:account-multiple"),
            ("security", "Security", "mdi:lock"),
            ("band",     "Band",     "mdi:wifi"),
            ("vlan",     "VLAN",     "mdi:lan"),
        ]:
            entities.append(
                WlcSsidSensor(
                    coordinator=coordinator,
                    ssid_idx=ssid_idx,
                    data_key=key,
                    entity_key=f"ssid_{ssid_idx}_{key}",
                    name=f"{ssid_name} {label}",
                    icon=icon,
                    device_info=device_info,
                    device_name=device_name,
                )
            )

    async_add_entities(entities)


# ── BASE ENTITY ───────────────────────────────────────────────────

class WlcBaseEntity(CoordinatorEntity[WlcDataCoordinator], SensorEntity):
    """Base WLC sensor entity."""

    def __init__(
        self,
        coordinator: WlcDataCoordinator,
        unique_id_suffix: str,
        device_info: DeviceInfo,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        host = list(device_info["identifiers"])[0][1]
        self._attr_unique_id  = f"wlc_{host}_{unique_id_suffix}"
        self._attr_device_info = device_info
        self._attr_has_entity_name = True


# ── SYSTEM SENSOR ─────────────────────────────────────────────────

class WlcSystemSensor(WlcBaseEntity):
    entity_description: WlcSensorEntityDescription

    def __init__(
        self,
        coordinator: WlcDataCoordinator,
        description: WlcSensorEntityDescription,
        device_info: DeviceInfo,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, description.key, device_info, device_name)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get(self.entity_description.data_key)
        # Uptime: return formatted string
        if self.entity_description.key == "uptime" and isinstance(val, dict):
            return val.get("formatted", "—")
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        if self.entity_description.key == "uptime":
            uptime = self.coordinator.data.get("uptime", {})
            return {
                "seconds": uptime.get("seconds", 0),
                "raw_ticks": uptime.get("raw", "—"),
            }
        if self.entity_description.key == "clients_total":
            return {
                "clients_2_4ghz": self.coordinator.data.get("clients_24", 0),
                "clients_5ghz":   self.coordinator.data.get("clients_5", 0),
            }
        if self.entity_description.key == "ap_up":
            return {
                "ap_total": self.coordinator.data.get("ap_total", 0),
                "ap_down":  self.coordinator.data.get("ap_down", 0),
            }
        return {}


# ── AP SENSOR ─────────────────────────────────────────────────────

class WlcApSensor(WlcBaseEntity):
    def __init__(
        self,
        coordinator: WlcDataCoordinator,
        ap_idx: str,          # MAC suffix string e.g. '0.167.66.179.98.192'
        data_key: str,
        entity_key: str,
        name: str,
        icon: str,
        unit: str | None,
        device_info: DeviceInfo,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, entity_key, device_info, device_name)
        self._ap_idx    = ap_idx
        self._data_key  = data_key
        self._attr_name = name
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("aps", {}).get(self._ap_idx, {}).get(self._data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        ap = self.coordinator.data.get("aps", {}).get(self._ap_idx, {})
        if self._data_key == "status":
            return {
                "ap_name":  ap.get("name"),
                "ap_model": ap.get("model"),
                "ap_ip":    ap.get("ip"),
                "clients":  ap.get("clients"),
            }
        return {}


# ── SSID SENSOR ───────────────────────────────────────────────────

class WlcSsidSensor(WlcBaseEntity):
    def __init__(
        self,
        coordinator: WlcDataCoordinator,
        ssid_idx: int,
        data_key: str,
        entity_key: str,
        name: str,
        icon: str,
        device_info: DeviceInfo,
        device_name: str,
    ) -> None:
        super().__init__(coordinator, entity_key, device_info, device_name)
        self._ssid_idx  = ssid_idx
        self._data_key  = data_key
        self._attr_name = name
        self._attr_icon = icon
        if data_key == "clients":
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("ssids", {}).get(self._ssid_idx, {}).get(self._data_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        ssid = self.coordinator.data.get("ssids", {}).get(self._ssid_idx, {})
        if self._data_key == "clients":
            return {
                "ssid_name": ssid.get("name"),
                "vlan":      ssid.get("vlan"),
                "band":      ssid.get("band"),
                "security":  ssid.get("security"),
            }
        return {}
