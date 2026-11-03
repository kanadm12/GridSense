"""Read-only adapter for AER Energy Product Reference Data APIs."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

_REGISTRY_PATH = Path(__file__).parents[1] / "data" / "aer_retailer_uris_2026_01.json"
_REGISTRY = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
_RETAILERS = {item["brand"]: item for item in _REGISTRY["retailers"]}
_POSTCODE = re.compile(r"^\d{4}$")
_POSTCODE_RANGE = re.compile(r"^(\d{4})-(\d{4})$")
_VICTORIAN_POSTCODE_RANGES = ((3000, 3999), (8000, 8999))


class AERProviderError(RuntimeError):
    """AER request failure with an API-safe HTTP status and optional retry delay."""

    def __init__(self, message: str, *, status_code: int = 502, retry_after: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def retailer_catalog() -> dict:
    """Return the versioned public AER retailer URI registry."""
    return {
        "source": _REGISTRY["source"],
        "document_version": _REGISTRY["document_version"],
        "source_url": _REGISTRY["source_url"],
        "source_last_updated": _REGISTRY["source_last_updated"],
        "retailers": [
            {
                "retailer": item["retailer"],
                "brand": item["brand"],
                "base_uri": item["base_uri"],
            }
            for item in _REGISTRY["retailers"]
        ],
    }


def registry_metadata() -> dict[str, str]:
    return {
        "source": _REGISTRY["source"],
        "document_version": _REGISTRY["document_version"],
        "source_url": _REGISTRY["source_url"],
    }


def _retailer(brand: str) -> dict:
    try:
        return _RETAILERS[brand]
    except KeyError as exc:
        raise AERProviderError("Unknown AER retailer brand.", status_code=404) from exc


def _plan_matches_postcode(plan: dict, postcode: str) -> bool:
    if not _is_victorian_postcode(postcode):
        raise ValueError("A valid Victorian four-digit postcode is required.")
    if "geography" not in plan:
        return True
    geography = plan["geography"]
    if not isinstance(geography, dict):
        raise AERProviderError("AER plan geography response schema changed.")

    def contains_postcode(entries: list, field: str) -> bool:
        for entry in entries:
            if not isinstance(entry, str):
                raise AERProviderError(
                    f"AER plan {field} response schema changed."
                )
            if _POSTCODE.fullmatch(entry):
                if postcode == entry:
                    return True
                continue
            match = _POSTCODE_RANGE.fullmatch(entry)
            if match is None:
                raise AERProviderError(
                    f"AER plan {field} contains an invalid postcode range."
                )
            first, last = (int(value) for value in match.groups())
            if first > last:
                raise AERProviderError(
                    f"AER plan {field} contains an invalid postcode range."
                )
            if first <= int(postcode) <= last:
                return True
        return False

    excluded = geography.get("excludedPostcodes", [])
    included = geography.get("includedPostcodes")
    if not isinstance(excluded, list) or (
        "includedPostcodes" in geography and not isinstance(included, list)
    ):
        raise AERProviderError("AER plan geography response schema changed.")
    if contains_postcode(excluded, "excludedPostcodes"):
        return False
    return included is None or contains_postcode(included, "includedPostcodes")


def _is_victorian_postcode(postcode: str) -> bool:
    if not _POSTCODE.fullmatch(postcode):
        return False
    value = int(postcode)
    return any(first <= value <= last for first, last in _VICTORIAN_POSTCODE_RANGES)


def _summary(plan: dict, brand: str, postcode: str) -> dict:
    required = ("planId", "brand", "fuelType", "displayName")
    if any(not isinstance(plan.get(field), str) for field in required):
        raise AERProviderError(
            "AER generic-plan response schema changed; the plan was not returned."
        )
    geography = plan.get("geography")
    if not isinstance(geography, dict):
        geography = {}
    return {
        "plan_id": plan["planId"],
        "brand": brand,
        "brand_name": plan.get("brandName"),
        "display_name": plan["displayName"],
        "plan_type": plan.get("type"),
        "fuel_type": plan["fuelType"],
        "effective_from": plan.get("effectiveFrom"),
        "effective_to": plan.get("effectiveTo"),
        "last_updated": plan.get("lastUpdated"),
        "customer_type": plan.get("customerType"),
        "included_postcodes": geography.get("includedPostcodes", []),
        "distributors": geography.get("distributors", []),
        "requested_postcode": postcode,
        "source_api_version": 1,
        "source_registry_version": _REGISTRY["document_version"],
        "retrieved_at": datetime.now(timezone.utc),
        "source_url": (
            _retailer(brand)["base_uri"].rstrip("/")
            + "/cds-au/v1/energy/plans"
        ),
    }


class AERPRDClient:
    """Fetch current generic plan data without persisting or caching provider responses."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15.0,
        max_pages: int = 20,
    ):
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages

    async def _get(
        self, url: str, *, params: dict | None = None, version: int
    ) -> tuple[dict, str | None]:
        headers = {
            "Accept": "application/json",
            "x-v": str(version),
            "x-min-v": str(version),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise AERProviderError(
                "AER Product Reference Data request timed out.", status_code=504
            ) from exc
        except httpx.HTTPError as exc:
            raise AERProviderError(
                "AER Product Reference Data is unavailable.", status_code=502
            ) from exc
        if response.status_code == 429:
            raise AERProviderError(
                "AER Product Reference Data rate limit was reached.",
                status_code=503,
                retry_after=response.headers.get("Retry-After"),
            )
        if response.status_code >= 500:
            raise AERProviderError(
                "AER Product Reference Data is unavailable.", status_code=502
            )
        if response.status_code >= 400:
            raise AERProviderError(
                f"AER Product Reference Data rejected the request ({response.status_code}).",
                status_code=502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AERProviderError(
                "AER Product Reference Data returned invalid JSON."
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise AERProviderError(
                "AER Product Reference Data response schema changed."
            )
        actual_version = response.headers.get("x-v")
        if actual_version != str(version):
            raise AERProviderError(
                "AER Product Reference Data returned an unexpected API version."
            )
        return payload, actual_version

    async def list_victorian_electricity_plans(
        self, brand: str, postcode: str
    ) -> list[dict]:
        retailer = _retailer(brand)
        if not _is_victorian_postcode(postcode):
            raise ValueError("A valid Victorian four-digit postcode is required.")
        endpoint = retailer["base_uri"].rstrip("/") + "/cds-au/v1/energy/plans"
        plans: list[dict] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            if page > self.max_pages:
                raise AERProviderError(
                    "AER plan pagination exceeded the configured safety limit.",
                    status_code=502,
                )
            payload, _ = await self._get(
                endpoint,
                params={
                    "type": "ALL",
                    "fuelType": "ELECTRICITY",
                    "effective": "CURRENT",
                    "brand": brand,
                    "page-size": 1000,
                    "page": page,
                },
                version=1,
            )
            data = payload["data"]
            page_plans = data.get("plans")
            meta = payload.get("meta")
            if (
                not isinstance(page_plans, list)
                or not isinstance(meta, dict)
                or not isinstance(meta.get("totalPages"), int)
                or meta["totalPages"] < 0
            ):
                raise AERProviderError(
                    "AER generic-plan response schema changed."
                )
            total_pages = meta["totalPages"]
            for plan in page_plans:
                if (
                    isinstance(plan, dict)
                    and plan.get("fuelType") == "ELECTRICITY"
                    and plan.get("brand") == brand
                    and _plan_matches_postcode(plan, postcode)
                ):
                    plans.append(_summary(plan, brand, postcode))
            page += 1
        return plans

    async def get_plan_detail(self, brand: str, plan_id: str) -> dict:
        retailer = _retailer(brand)
        if not plan_id or len(plan_id) > 160:
            raise ValueError("A valid AER plan identifier is required.")
        endpoint = (
            retailer["base_uri"].rstrip("/")
            + "/cds-au/v1/energy/plans/"
            + quote(plan_id, safe="")
        )
        payload, version = await self._get(endpoint, version=3)
        detail = payload["data"]
        if detail.get("planId") != plan_id or detail.get("brand") != brand:
            raise AERProviderError(
                "AER plan detail did not match the requested plan and retailer."
            )
        contract = detail.get("electricityContract")
        if not isinstance(contract, dict):
            raise AERProviderError(
                "AER plan detail does not contain a supported electricity contract."
            )
        unsupported = [
            "generic reference plan; not evidence of this customer's contract",
            "eligibility conditions require retailer verification",
            "discounts and incentives are not modeled",
            "controlled-load and metering terms are not modeled",
            "conditional fees and other contract terms are not modeled",
        ]
        return {
            "plan_id": plan_id,
            "brand": brand,
            "brand_name": detail.get("brandName"),
            "display_name": detail.get("displayName"),
            "effective_from": detail.get("effectiveFrom"),
            "effective_to": detail.get("effectiveTo"),
            "last_updated": detail.get("lastUpdated"),
            "source_api_version": int(version or 3),
            "source_registry_version": _REGISTRY["document_version"],
            "retrieved_at": datetime.now(timezone.utc),
            "terms": contract,
            "unsupported_components": unsupported,
            "requires_manual_user_review": True,
            "source_url": endpoint,
        }
