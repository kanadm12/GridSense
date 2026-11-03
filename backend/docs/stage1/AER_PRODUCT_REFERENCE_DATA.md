# AER Energy Product Reference Data — Evidence and Implementation

**Evidence checked:** 31 October 2026\
**Purpose:** Record the authoritative interface, source version, live smoke
checks, implementation boundary and unresolved use-rights questions for
GridSense's read-only generic-plan catalog.

## Source-grounded interpretation matrix

| Interpretation | Authoritative source/version | Page or section | Source wording/semantics | Applicability | GridSense implementation |
|---|---|---|---|---|---|
| Public generic-plan data access | AER, [Energy Product Reference Data](https://www.aer.gov.au/energy-product-reference-data), current page checked 31 Oct 2026 | “Who can access the APIs?”; “How to use the Energy PRD APIs”; “Does the Get Generic Plans API only show current plans?” | The APIs are public and do not require accreditation. The list is restricted to one retailer per request; detail is restricted to one plan. The list contains current plans, not historical or future plans. | Consumer-facing generic plan discovery; not customer-contract evidence. | Read-only catalog endpoints; no contract write, activation or historic plan lookup. |
| Data purpose and fields | AER, same page | “Consumer fact sheets” | AER and Victoria's DEECA publish the data also used by Energy Made Easy and Victoria Energy Compare. Listed fields include plan names, fuel, brand, geography, metering charges, terms, incentives/discounts, fees and eligibility. | Public reference-plan browsing and inspection. | List summaries plus unmodified `electricityContract` detail; unsupported terms are disclosed. |
| API technical instructions | AER, [Fact Sheet on Accessing Energy Product Reference Data](https://www.aer.gov.au/node/72498), “CDR API Fact Sheet - February 2025” | “Steps to run Get Generic Plans API” (paras 9–22); “Steps to run Get Generic Plan Detail API” (paras 24–34) | Use the retailer URI from AER's base-URI registry; send HTTP requests, not browser navigation; public API authorization is “No Auth”; list remains v1 while detail supports v3; v2 detail support ended 3 Mar 2025. | Request URLs, public access and distinct endpoint versions. | Uses the versioned official AER registry, no provider credentials, list `x-v: 1`, detail `x-v: 3`. |
| Current retailer URI discovery | AER, [Consumer Data Right - Energy Retailer Base URIs and CDR Brands - January 2026](https://www.aer.gov.au/documents/consumer-data-right-energy-retailer-base-uris-and-cdr-brands) | PDF pp. 1–3 (retailer/brand/base-URI table); p. 4 (change log) | Each retailer brand is paired with its CDR base URI. The change log records an update on 15 January 2026. | The host/base path for the approved retailer API. The list can change after the snapshot. | Bundled 83-entry January 2026 snapshot at `backend/app/data/aer_retailer_uris_2026_01.json`; every entry is HTTPS and user input cannot supply a URL. Refresh is a controlled source update, not automatic. |
| Get Generic Plans URL and filters | Consumer Data Standards Australia (CDS), [Standards v1.36.0](https://consumerdatastandardsaustralia.github.io/standards/), **Energy APIs → Get Generic Plans** | [Endpoint](https://consumerdatastandardsaustralia.github.io/standards/#get-generic-plans), endpoint version table and Parameters | `GET {retailer-base-uri}/cds-au/v1/energy/plans`; endpoint version 1. Parameters include `type`, `fuelType`, `effective`, `updated-since`, `brand`, `page`, and `page-size`. Defaults include `ALL`, `CURRENT`, page 1 and page size 25. `x-v` is mandatory; `x-min-v` is optional. | Retrieve current electric plans from a selected AER retailer endpoint. | Requests `type=ALL`, `fuelType=ELECTRICITY`, `effective=CURRENT`, the retailer brand, `page-size=1000`, and each page. Sends `x-v: 1` and `x-min-v: 1`. |
| Get Generic Plan Detail URL/version | CDS, Standards v1.36.0 | [Energy APIs → Get Generic Plan Detail](https://consumerdatastandardsaustralia.github.io/standards/#get-generic-plan-detail), Endpoint Version and Parameters | `GET {retailer-base-uri}/cds-au/v1/energy/plans/{planId}`; endpoint version 3; `planId` and `x-v` are mandatory; `x-min-v` is optional. The endpoint describes one openly offered plan. | Retrieve terms for a selected plan, not an account-specific contract. | Percent-encodes the source plan ID as one path segment, requests v3, and verifies the returned plan ID and brand match. |
| Response pagination | CDS, Standards v1.36.0 | [Pagination](https://consumerdatastandardsaustralia.github.io/standards/#pagination); AER PRD page “What is the maximum number of records per API call?” | Standard pagination uses `page` and `page-size`; CDR maximum page size is 1000. AER says page size defaults to 25 and caps at 1000, and a separate request is needed per page. | Avoid excess provider requests while retrieving all pages for one retailer. | Uses page size 1000, validates `meta.totalPages`, and fails closed above 20 pages per request. No automatic retry or persistent cache. |
| Geography and postcode ranges | CDS, Standards v1.36.0 | [EnergyPlan properties](https://consumerdatastandardsaustralia.github.io/standards/#schemacdr-energy-apienergyplan), `geography`, `includedPostcodes`, `excludedPostcodes` | If `geography` is absent, the plan is not geographically limited. If `includedPostcodes` is absent, all non-excluded postcodes are included. Postcode entries can be a four-digit postcode or inclusive `NNNN-NNNN` range. | Determine whether a current offer is listed for the supplied Victorian postcode. | Requires a Victorian postcode; supports exact values and ranges; exclusions take precedence. Malformed geography fails closed. |
| Plan data schema | CDS, Standards v1.36.0 | Get Generic Plans response schema; [EnergyPlan properties](https://consumerdatastandardsaustralia.github.io/standards/#schemacdr-energy-apienergyplan); [EnergyPlanDetailV3](https://consumerdatastandardsaustralia.github.io/standards/#schemacdr-energy-apienergyplandetailv3) | List records identify the plan, brand, fuel, display name, effective dates, last update and geography. Detail v3 exposes contract terms, rates, tariff periods, fees, controlled loads, incentives and solar feed-in terms. | Different plan structures may contain components GridSense cannot price. | Preserve source plan ID, last update, raw contract terms, retrieval timestamp and endpoint version in API responses. No mapping from generic data into `TariffRevision` is performed. |
| Version negotiation and throttling | CDS, Standards v1.36.0 | [Request Headers](https://consumerdatastandardsaustralia.github.io/standards/#request-headers); [Exemptions to Protect Service](https://consumerdatastandardsaustralia.github.io/standards/#exemptions-to-protect-service) | `x-v` requests the endpoint version; `x-min-v` sets the acceptable lower bound. CDS describes HTTP 429 for excessive traffic/misbehaving clients. AER's PRD page contains no numeric requests-per-minute limit. | Handle endpoint version drift and provider throttling without hammering the service. | Validate response `x-v`; return a gateway error on mismatch; expose 429/`Retry-After`, do not retry automatically; local catalog/detail routes are limited to 5 requests/minute per client IP. |
| Use, attribution, retention and caching | AER PRD page and AER February 2025 fact sheet; CDS Standards v1.36.0 | AER “Who can access the APIs?” and “Are there any specific guidelines…”; CDS Non-Functional Requirements → “Data Latency” | Public access/no accreditation is documented. The reviewed AER materials do not state an explicit redistribution licence, mandatory attribution text, or permission to retain/cache plan content. The CDS short-lived-cache statement applies to Shared Responsibility Data Requests, not an explicit AER generic-plan reuse grant. | Must be resolved before treating server-side redistribution as production-cleared. | No cache or persisted provider payload. Responses label AER source and endpoint/registry versions. **Production redistribution/use-rights approval remains blocked.** |

## Exact interface and live smoke evidence

Verified request forms:

```text
GET https://{retailer-base-uri}/cds-au/v1/energy/plans
    ?type=ALL&fuelType=ELECTRICITY&effective=CURRENT&brand={brand}
    &page-size=1000&page={page}
Accept: application/json
x-v: 1
x-min-v: 1

GET https://{retailer-base-uri}/cds-au/v1/energy/plans/{planId}
Accept: application/json
x-v: 3
x-min-v: 3
```

The base URI is selected only from the versioned AER registry. The exact AGL
base URI in that source is `https://cdr.energymadeeasy.gov.au/agl/`.

On 31 October 2026, a live AGL list request returned HTTP 200 and response
header `x-v: 1`, with `data.plans`, `meta.totalRecords`, `meta.totalPages`, and
pagination links. A live detail request for the returned plan ID, sent with
`x-v: 3` and `x-min-v: 3`, returned HTTP 200 and `x-v: 3`, with
`data.electricityContract`. The calls verified connectivity and response
shape only; the live plan and rates are volatile and are not test fixtures or
customer evidence. Automated tests use mocked responses.

## Implementation and operational boundary

- Provider code: `backend/app/services/aer_prd.py`.
- Routes: `GET /api/v1/tariffs/catalog/aer/retailers`,
  `GET /api/v1/tariffs/catalog/aer/plans?brand=...&postcode=...`, and
  `GET /api/v1/tariffs/catalog/aer/plans/{plan_id}?brand=...`.
- List and detail responses are transient; the adapter does not write
  provider data, confirmed tariffs, or customer tariff revisions.
- Provider timeouts become 504; malformed/changed schemas, unexpected
  versions and upstream failures fail explicitly; 429 is exposed as 503 with
  `Retry-After` when supplied. No response body or retailer error detail is
  echoed to the client.
- Local request rate limit: five calls per minute per client IP for plan-list
  and detail routes. The pagination loop is bounded at 20 pages.
- Generic detail includes an explicit manual-review requirement and
  unsupported-component disclosure. A user must independently enter and
  confirm the tariff; public plan data is never proof of a customer's terms.

## Remaining blockers

1. Obtain written/official confirmation of redistribution, attribution,
   retention and caching conditions for AER/DEECA generic plan data before
   production use. Current implementation avoids persistence and caching but
   still relays data to the app.
2. The January 2026 retailer URI snapshot must be checked and updated before
   deployment if a newer official registry exists.
3. Automated tests prove mocked pagination, version headers, postcode
   eligibility, timeout, 429/`Retry-After`, and schema-change handling; they
   do not establish AER's unpublished numeric request quota or legal terms.
