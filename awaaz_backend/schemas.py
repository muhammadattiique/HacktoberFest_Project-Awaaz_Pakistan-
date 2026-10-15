from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# --- Rates Schemas ---
class RateItem(BaseModel):
    id: str
    name_en: str
    name_ur: str
    price: float
    unit: str
    category: str
    aliases: List[str] = Field(default_factory=list)


class RateListResponse(BaseModel):
    meta: Dict[str, Any]
    items: List[RateItem]
    total_items: int


class PriceCheckRequest(BaseModel):
    query: Optional[str] = Field(None, description="Natural language price query e.g. 'Aloo 180 rupay'")
    item_name: Optional[str] = None
    reported_price: Optional[float] = None
    unit: Optional[str] = None


class PriceComparisonResult(BaseModel):
    item_canonical_id: Optional[str] = None
    item_name: str
    unit: str
    official_price: float
    reported_price: float
    price_difference_pkr: float
    percentage_overcharge: float
    is_overpriced: bool
    severity: str  # "Normal", "Moderate", "High", "Critical"
    recommended_action: str
    legal_statute_note: str


# --- Complaint Schemas ---
class TextComplaintRequest(BaseModel):
    transcript_text: str = Field(..., min_length=2, description="Urdu, Roman Urdu, or English complaint transcript")
    location_area: Optional[str] = Field(None, description="E.g. 'G-9 Markaz, Islamabad' or 'Raja Bazaar'")
    shop_name: Optional[str] = Field(None, description="Shop or vendor name")
    lat: Optional[float] = None
    lng: Optional[float] = None


class ComplaintUpdateStatusRequest(BaseModel):
    status: str = Field(..., description="Pending, Investigating, Resolved, Rejected")
    admin_notes: Optional[str] = None
    assigned_authority: Optional[str] = Field(
        None,
        description="Enforcement body the grievance is assigned to, e.g. 'Punjab Food Authority (PFA)'",
    )


class ComplaintResponse(BaseModel):
    id: str
    submission_id: Optional[str] = None
    created_at: datetime
    audio_filename: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    transcript_raw: str
    detected_language: str
    category: str
    urgency: str
    status: str
    extraction_confidence: float
    needs_review: bool
    item_name: Optional[str] = None
    item_canonical_id: Optional[str] = None
    unit: Optional[str] = None
    reported_price: Optional[float] = None
    official_price: Optional[float] = None
    price_difference_pkr: Optional[float] = None
    percentage_overcharge: Optional[float] = None
    native_response: str
    location_area: Optional[str] = None
    shop_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    routing_agency: str
    helpline_reference: str
    admin_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MultiComplaintResponse(BaseModel):
    submission_id: str
    complaints: List[ComplaintResponse]
    # ``primary`` is None only when a submission contained items that are ALL
    # priced at or below the official rate (no violation registered).
    primary: Optional[ComplaintResponse] = None
    # Human-readable note, e.g. when nothing was registered because every
    # mentioned item was within the official rate.
    message: Optional[str] = None


class ComplaintListResponse(BaseModel):
    total: int
    items: List[ComplaintResponse]
    page: int
    limit: int


# --- Analytics Schemas ---
class GougedItemMetric(BaseModel):
    item_name: str
    complaint_count: int
    average_overcharge_pct: float
    official_price: float
    highest_reported_price: float


class AnalyticsOverview(BaseModel):
    total_complaints: int
    overpricing_cases: int
    food_safety_cases: int
    infrastructure_cases: int
    average_overcharge_pct: float
    total_excess_charged_est_pkr: float
    most_gouged_items: List[GougedItemMetric]
    high_urgency_count: int
    needs_review_count: int


class HotspotArea(BaseModel):
    area: str
    complaint_count: int
    avg_overcharge_pct: float
    top_violated_item: str
    dominant_category: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class PublicMapPoint(BaseModel):
    """Privacy-preserving spatial point for public macro heatmaps.

    Coordinates are obfuscated and the vendor/shop identity is deliberately
    withheld; exact GPS data is only exposed through the authenticated portal.
    """
    lat: float
    lng: float
    category: str
    urgency: str
    is_overpriced: bool
    overcharge_pct: float


class RepeatOffender(BaseModel):
    shop_name: str
    area: str
    violations_count: int
    items_gouged: List[str]
    max_overcharge_pct: float
    status: str
    latest_complaint_date: datetime


class ShopProfile(BaseModel):
    """Aggregated enforcement dossier for a single vendor."""
    shop_name: str
    area: Optional[str] = None
    total_citations: int
    open_citations: int
    resolved_citations: int
    average_overcharge_pct: float
    max_overcharge_pct: float
    total_excess_charged_est_pkr: float
    items_gouged: List[str]
    is_repeat_offender: bool
    recommended_action: str
    latest_complaint_date: Optional[datetime] = None


class DailyTrendPoint(BaseModel):
    date: str
    complaint_count: int
    avg_overcharge_pct: float


class TrendsResponse(BaseModel):
    trends: List[DailyTrendPoint]
    category_distribution: Dict[str, int]
    urgency_distribution: Dict[str, int]


# --- Admin / Health Schemas ---
class AdminHealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    whisper_model: str
    whisper_loaded: bool
    ollama_model: str
    ollama_reachable: bool
    rates_count: int
    database_connected: bool


class SafeConfigResponse(BaseModel):
    app_name: str
    app_version: str
    environment: str
    whisper_model: str
    ollama_model: str
    upload_max_bytes: int
    audio_max_duration_seconds: float
    district_helpline_ict: str
    district_helpline_rawalpindi: str
    pera_enforcement_helpline: str
    pfa_food_safety_helpline: str
    cda_municipal_helpline: str
    wasa_rawalpindi_helpline: str
    legal_fine_min_pkr: int
    legal_fine_max_pkr: int
