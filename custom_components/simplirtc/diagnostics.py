"""Diagnostics support for SimpliRTC."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from simplipy.device.camera import Camera
from simplipy.system.v3 import SystemV3

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.components.simplisafe import SimpliSafe
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {
	"entry_id",
	"config_entry_id",
	"system_id",
	"title",
	"unique_id",
}


async def async_get_config_entry_diagnostics(
	hass: HomeAssistant, entry: ConfigEntry[SimpliSafe]
) -> dict[str, Any]:
	"""Return diagnostics for a config entry."""
	_ = hass
	simplisafe = entry.runtime_data
	data: dict[str, Any] = {
		"entry": async_redact_data(entry.as_dict(), TO_REDACT),
		"systems": [
			_describe_system(system, index)
			for index, system in enumerate(simplisafe.systems.values())
		],
	}
	return data


def _describe_system(system: object, index: int) -> dict[str, Any]:
	version = getattr(system, "version", None)
	system_data: dict[str, Any] = {
		"index": index,
		"version": version,
		"supported_system": isinstance(system, SystemV3),
		"cameras": [],
	}

	if not isinstance(system, SystemV3):
		system_data["skip_reason"] = "unsupported_system_version"
		return system_data

	system_data["cameras"] = [
		_describe_camera(camera, system)
		for camera in system.cameras.values()
	]
	return system_data


def _describe_camera(camera: Camera, system: SystemV3) -> dict[str, Any]:
	"""Describe stream-ID consistency without returning identifiers or URLs."""
	raw_provider, backend, supported, skip_reason = _describe_webrtc_provider(
		camera.camera_settings.get("admin")
	)
	# The current live-view endpoint uses camera.serial as its path identifier.
	# Camera metadata may expose a different UUID. Compare without revealing it.
	camera_data = system.camera_data.get(camera.serial)
	metadata = camera_data if isinstance(camera_data, Mapping) else {}
	uuid = metadata.get("uuid")
	serial = metadata.get("serial")
	return {
		"name": camera.name,
		"webRTCProvider": raw_provider,
		"backend": backend,
		"supported": supported,
		"skip_reason": skip_reason,
		"identifier_checks": {
			"camera_data_found_by_entity_serial": isinstance(camera_data, Mapping),
			"camera_data_uuid_present": isinstance(uuid, str) and bool(uuid),
			"camera_data_uuid_matches_entity_serial": uuid == camera.serial if isinstance(uuid, str) else None,
			"camera_data_serial_present": isinstance(serial, str) and bool(serial),
			"camera_data_serial_matches_entity_serial": serial == camera.serial if isinstance(serial, str) else None,
		},
	}


def _describe_webrtc_provider(
	settings: object,
) -> tuple[str | None, str, bool, str | None]:
	if not isinstance(settings, Mapping):
		return None, "unknown", False, "unexpected_settings_schema"

	provider = settings.get("webRTCProvider")
	raw_provider = str(provider)

	match provider:
		case "mist":
			return raw_provider, "livekit", True, None
		case "kvs":
			return raw_provider, "kinesis", True, None
		case None:
			return None, "unknown", False, "missing_webrtc_provider"
		case _:
			return raw_provider, "unknown", False, "unknown_webrtc_provider"
