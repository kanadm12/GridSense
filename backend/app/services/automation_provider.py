"""Device control providers for home automation."""

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import Settings
from app.models.automation import SmartDevice


class AutomationProviderError(RuntimeError):
    """Raised when a device provider cannot execute a command."""


class AutomationProvider(ABC):
    """Interface shared by simulated and real device providers."""

    @abstractmethod
    async def execute(self, device: SmartDevice, command: str, params: dict[str, Any] | None) -> dict[str, Any]:
        """Execute a command and return the provider-reported state."""


class SimulatorProvider(AutomationProvider):
    """Deterministic provider used for development and automated tests."""

    async def execute(self, device: SmartDevice, command: str, params: dict[str, Any] | None) -> dict[str, Any]:
        state = dict(device.current_state or {})
        params = params or {}
        if command == "on":
            state["power"] = "on"
        elif command == "off":
            state["power"] = "off"
        elif command == "set_temp":
            if "temperature" not in params:
                raise AutomationProviderError("set_temp requires a temperature")
            state["temperature"] = params["temperature"]
        elif command == "set_mode":
            if "mode" not in params:
                raise AutomationProviderError("set_mode requires a mode")
            state["mode"] = params["mode"]
        else:
            raise AutomationProviderError(f"Unsupported command: {command}")
        state["provider"] = "simulator"
        return state


class HomeAssistantProvider(AutomationProvider):
    """Home Assistant REST provider for common household commands."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def execute(self, device: SmartDevice, command: str, params: dict[str, Any] | None) -> dict[str, Any]:
        if not device.device_id:
            raise AutomationProviderError("Home Assistant device requires an entity ID")
        if not self.settings.home_assistant_token:
            raise AutomationProviderError("Home Assistant token is not configured")

        service_domain, service, data = self._service_for(command, params or {})
        base_url = (device.api_endpoint or self.settings.home_assistant_url).rstrip("/")
        headers = {"Authorization": f"Bearer {self.settings.home_assistant_token}"}
        payload = {"entity_id": device.device_id, **data}

        try:
            async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=10.0) as client:
                response = await client.post(f"/api/services/{service_domain}/{service}", json=payload)
                response.raise_for_status()
                state_response = await client.get(f"/api/states/{device.device_id}")
                state_response.raise_for_status()
                state = state_response.json()
                return {
                    "provider": "home_assistant",
                    "entity_id": device.device_id,
                    "state": state.get("state"),
                    "attributes": state.get("attributes", {}),
                }
        except (httpx.HTTPError, ValueError) as exc:
            raise AutomationProviderError(f"Home Assistant command failed: {exc}") from exc

    @staticmethod
    def _service_for(command: str, params: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        if command == "on":
            return "homeassistant", "turn_on", {}
        if command == "off":
            return "homeassistant", "turn_off", {}
        if command == "set_temp":
            if "temperature" not in params:
                raise AutomationProviderError("set_temp requires a temperature")
            return "climate", "set_temperature", {"temperature": params["temperature"]}
        if command == "set_mode":
            if "mode" not in params:
                raise AutomationProviderError("set_mode requires a mode")
            return "climate", "set_hvac_mode", {"hvac_mode": params["mode"]}
        raise AutomationProviderError(f"Unsupported command: {command}")


def get_automation_provider(device: SmartDevice, settings: Settings) -> AutomationProvider:
    """Select a provider from device metadata, falling back to the configured default."""
    integration_type = (device.integration_type or settings.automation_provider).lower()
    if integration_type == "home_assistant":
        return HomeAssistantProvider(settings)
    return SimulatorProvider()
