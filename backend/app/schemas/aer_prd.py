"""Response models for read-only AER generic plan references."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AERRetailer(BaseModel):
    retailer: str
    brand: str
    base_uri: str


class AERRetailerCatalogResponse(BaseModel):
    source: str
    document_version: str
    source_url: str
    source_last_updated: str
    retailers: list[AERRetailer]


class AERPlanSummary(BaseModel):
    plan_id: str
    brand: str
    brand_name: str | None = None
    display_name: str
    plan_type: str | None = None
    fuel_type: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    last_updated: datetime | None = None
    customer_type: str | None = None
    included_postcodes: list[str] = Field(default_factory=list)
    distributors: list[str] = Field(default_factory=list)
    requested_postcode: str
    source_api_version: int
    source_registry_version: str
    retrieved_at: datetime
    source_url: str


class AERPlanSearchResponse(BaseModel):
    source: str
    source_registry_version: str
    retrieved_at: datetime
    plans: list[AERPlanSummary]


class AERPlanDetailResponse(BaseModel):
    plan_id: str
    brand: str
    brand_name: str | None = None
    display_name: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    last_updated: datetime | None = None
    source_api_version: int
    source_registry_version: str
    retrieved_at: datetime
    terms: dict[str, Any]
    unsupported_components: list[str]
    requires_manual_user_review: bool
    source_url: str
