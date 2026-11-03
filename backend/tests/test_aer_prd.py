import httpx
import pytest

from app.services.aer_prd import AERPRDClient, AERProviderError, retailer_catalog


def _plan(
    plan_id: str,
    *,
    brand: str = "agl",
    postcode: str = "3000",
) -> dict:
    return {
        "planId": plan_id,
        "brand": brand,
        "brandName": "AGL",
        "displayName": f"Reference plan {plan_id}",
        "type": "MARKET",
        "fuelType": "ELECTRICITY",
        "effectiveFrom": "2026-10-01T00:00:00.000Z",
        "effectiveTo": "2026-11-10T00:00:00.000Z",
        "lastUpdated": "2026-10-28T22:39:40.384Z",
        "customerType": "RESIDENTIAL",
        "geography": {
            "includedPostcodes": [postcode],
            "excludedPostcodes": [],
            "distributors": ["AusNet Services"],
        },
    }


def test_aer_registry_is_versioned_and_uses_official_base_uris():
    catalog = retailer_catalog()

    assert catalog["document_version"] == "January 2026"
    assert catalog["source_last_updated"] == "2026-01-15"
    assert len(catalog["retailers"]) >= 80
    assert all(
        retailer["brand"] and retailer["base_uri"].startswith("https://")
        for retailer in catalog["retailers"]
    )


@pytest.mark.asyncio
async def test_list_uses_list_v1_paginates_and_filters_by_victorian_postcode():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-v"] == "1"
        assert request.headers["x-min-v"] == "1"
        assert request.url.params["fuelType"] == "ELECTRICITY"
        assert request.url.params["effective"] == "CURRENT"
        assert request.url.params["brand"] == "agl"
        assert request.url.params["page-size"] == "1000"
        page = request.url.params["page"]
        plan = _plan("vic-plan" if page == "2" else "qld-plan")
        if page == "1":
            plan["geography"]["includedPostcodes"] = ["4000"]
        return httpx.Response(
            200,
            headers={"x-v": "1"},
            json={
                "data": {"plans": [plan]},
                "meta": {"totalRecords": 2, "totalPages": 2},
                "links": {},
            },
        )

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    plans = await client.list_victorian_electricity_plans("agl", "3000")

    assert len(requests) == 2
    assert len(plans) == 1
    assert plans[0]["plan_id"] == "vic-plan"
    assert plans[0]["requested_postcode"] == "3000"
    assert plans[0]["source_api_version"] == 1
    assert plans[0]["source_registry_version"] == "January 2026"


@pytest.mark.asyncio
async def test_geography_honors_postcode_ranges_exclusions_and_unrestricted_plans():
    async def handler(_: httpx.Request) -> httpx.Response:
        range_plan = _plan("postcode-range")
        range_plan["geography"]["includedPostcodes"] = ["3000-3099"]
        excluded_plan = _plan("excluded-postcode")
        excluded_plan["geography"]["includedPostcodes"] = ["3000-3099"]
        excluded_plan["geography"]["excludedPostcodes"] = ["3000"]
        unrestricted_plan = _plan("unrestricted")
        unrestricted_plan.pop("geography")
        return httpx.Response(
            200,
            headers={"x-v": "1"},
            json={
                "data": {
                    "plans": [range_plan, excluded_plan, unrestricted_plan]
                },
                "meta": {"totalRecords": 3, "totalPages": 1},
            },
        )

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    plans = await client.list_victorian_electricity_plans("agl", "3000")

    assert {plan["plan_id"] for plan in plans} == {
        "postcode-range",
        "unrestricted",
    }


@pytest.mark.asyncio
async def test_plan_detail_uses_version_3_and_requires_manual_review():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-v"] == "3"
        assert request.headers["x-min-v"] == "3"
        assert request.url.path.endswith("AGL123%40EME") or request.url.path.endswith(
            "AGL123@EME"
        )
        return httpx.Response(
            200,
            headers={"x-v": "3"},
            json={
                "data": {
                    **_plan("AGL123@EME"),
                    "electricityContract": {
                        "pricingModel": "SINGLE_RATE",
                        "tariffPeriod": [{"singleRate": {"rates": []}}],
                        "controlledLoad": [{"displayName": "Controlled Load"}],
                    },
                },
                "meta": {},
                "links": {},
            },
        )

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    detail = await client.get_plan_detail("agl", "AGL123@EME")

    assert detail["source_api_version"] == 3
    assert detail["terms"]["pricingModel"] == "SINGLE_RATE"
    assert detail["requires_manual_user_review"] is True
    assert any("not evidence" in item for item in detail["unsupported_components"])


@pytest.mark.asyncio
async def test_aer_429_preserves_retry_after():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"})

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AERProviderError) as error:
        await client.list_victorian_electricity_plans("agl", "3000")

    assert error.value.status_code == 503
    assert error.value.retry_after == "30"


@pytest.mark.asyncio
async def test_aer_changed_response_schema_fails_explicitly():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-v": "1"},
            json={"data": {"unexpected": []}, "meta": {"totalPages": 1}},
        )

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AERProviderError, match="schema changed"):
        await client.list_victorian_electricity_plans("agl", "3000")


@pytest.mark.asyncio
async def test_aer_unexpected_response_version_fails_closed():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-v": "2"},
            json={
                "data": {"plans": []},
                "meta": {"totalRecords": 0, "totalPages": 0},
            },
        )

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AERProviderError, match="unexpected API version"):
        await client.list_victorian_electricity_plans("agl", "3000")


@pytest.mark.asyncio
async def test_aer_page_fanout_is_bounded():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-v": "1"},
            json={
                "data": {"plans": []},
                "meta": {"totalRecords": 21, "totalPages": 21},
            },
        )

    client = AERPRDClient(
        transport=httpx.MockTransport(handler),
        max_pages=20,
    )
    with pytest.raises(AERProviderError, match="safety limit"):
        await client.list_victorian_electricity_plans("agl", "3000")


@pytest.mark.asyncio
async def test_aer_timeout_is_reported_as_gateway_timeout():
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out")

    client = AERPRDClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AERProviderError, match="timed out") as error:
        await client.list_victorian_electricity_plans("agl", "3000")

    assert error.value.status_code == 504


@pytest.mark.asyncio
async def test_invalid_postcode_and_unknown_retailer_are_rejected():
    client = AERPRDClient()
    with pytest.raises(ValueError, match="postcode"):
        await client.list_victorian_electricity_plans("agl", "not-a-postcode")
    with pytest.raises(ValueError, match="Victorian"):
        await client.list_victorian_electricity_plans("agl", "2000")
    with pytest.raises(AERProviderError) as error:
        await client.list_victorian_electricity_plans("unknown-brand", "3000")
    assert error.value.status_code == 404
