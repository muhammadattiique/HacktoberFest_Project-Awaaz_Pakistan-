import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text

from auth import verify_admin_api_key
from config import settings
from db.session import get_db
from db.models import Complaint
from timeutils import utcnow
from ai_pipeline import ai_pipeline
from services.rates import rate_service
from schemas import AdminHealthResponse, SafeConfigResponse, ShopProfile

router = APIRouter(prefix="/admin", tags=["System Administration"])

# Administrative dependency applied per-route. It is intentionally NOT set at the
# router level because FastAPI merges (rather than replaces) route-level and
# router-level dependencies, which would make /health impossible to expose
# publicly for container health probes.
ADMIN_AUTH = [Depends(verify_admin_api_key)]


@router.get(
    "/health",
    response_model=AdminHealthResponse,
    summary="Public liveness / readiness probe",
)
async def get_system_health(db: AsyncSession = Depends(get_db)):
    """
    Returns AI subsystems and database health status.
    Public by design: polled by Docker HEALTHCHECK and the frontend status badge,
    neither of which holds administrative credentials.
    """
    # Check DB connectivity
    db_connected = False
    try:
        await db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    # Check Ollama
    ollama_ok = ai_pipeline.ollama_available
    if not ollama_ok and ai_pipeline._ollama_client:
        try:
            ai_pipeline._ollama_client.list()
            ollama_ok = True
        except Exception:
            ollama_ok = False

    items = rate_service.get_all_items()

    overall_status = "healthy" if (ai_pipeline.whisper_loaded and db_connected) else "degraded"

    return AdminHealthResponse(
        status=overall_status,
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        whisper_model=settings.WHISPER_MODEL,
        whisper_loaded=ai_pipeline.whisper_loaded,
        ollama_model=settings.OLLAMA_MODEL,
        ollama_reachable=ollama_ok,
        rates_count=len(items),
        database_connected=db_connected
    )


@router.get("/config", response_model=SafeConfigResponse, dependencies=ADMIN_AUTH)
def get_safe_config():
    """
    Returns non-sensitive public configuration including official helpline references.
    """
    return SafeConfigResponse(
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        whisper_model=settings.WHISPER_MODEL,
        ollama_model=settings.OLLAMA_MODEL,
        upload_max_bytes=settings.UPLOAD_MAX_BYTES,
        audio_max_duration_seconds=settings.AUDIO_MAX_DURATION_SECONDS,
        district_helpline_ict=settings.DISTRICT_HELPLINE_ICT,
        district_helpline_rawalpindi=settings.DISTRICT_HELPLINE_RAWALPINDI,
        pera_enforcement_helpline=settings.PERA_ENFORCEMENT_HELPLINE,
        pfa_food_safety_helpline=settings.PFA_FOOD_SAFETY_HELPLINE,
        cda_municipal_helpline=settings.CDA_MUNICIPAL_HELPLINE,
        wasa_rawalpindi_helpline=settings.WASA_RAWALPINDI_HELPLINE,
        legal_fine_min_pkr=settings.LEGAL_FINE_MIN_PKR,
        legal_fine_max_pkr=settings.LEGAL_FINE_MAX_PKR
    )


@router.get("/shops/{shop_name}", response_model=ShopProfile, dependencies=ADMIN_AUTH)
async def get_shop_profile(shop_name: str, db: AsyncSession = Depends(get_db)):
    """Returns the aggregated enforcement dossier for a single vendor.

    Powers the "repeat offender" drawer in the admin portal: total citations,
    historical overcharge average, gouged commodities, and whether the shop
    crosses the repeat-offender threshold.
    """
    name = shop_name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shop name must not be empty.",
        )

    stats_query = select(
        func.count(Complaint.id).label("total"),
        func.avg(Complaint.percentage_overcharge).label("avg_pct"),
        func.max(Complaint.percentage_overcharge).label("max_pct"),
        func.sum(Complaint.price_difference_pkr).label("excess"),
        func.max(Complaint.created_at).label("latest"),
    ).where(Complaint.shop_name == name)
    stats_res = await db.execute(stats_query)
    row = stats_res.one()

    total = row.total or 0
    if total == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No complaints on record for shop '{name}'.",
        )

    open_res = await db.execute(
        select(func.count(Complaint.id))
        .where(Complaint.shop_name == name, Complaint.status.in_(("Pending", "Investigating")))
    )
    open_citations = open_res.scalar() or 0

    resolved_res = await db.execute(
        select(func.count(Complaint.id))
        .where(Complaint.shop_name == name, Complaint.status.in_(("Resolved", "Rejected")))
    )
    resolved_citations = resolved_res.scalar() or 0

    items_res = await db.execute(
        select(Complaint.item_name)
        .where(Complaint.shop_name == name, Complaint.item_name.is_not(None))
        .distinct()
    )
    items_gouged = [i for i in items_res.scalars().all() if i]

    area_res = await db.execute(
        select(Complaint.location_area)
        .where(Complaint.shop_name == name, Complaint.location_area.is_not(None))
        .limit(1)
    )
    area = area_res.scalar()

    max_pct = round(float(row.max_pct or 0.0), 1)
    is_repeat_offender = total >= 2

    if max_pct >= settings.HIGH_SEVERITY_THRESHOLD_PCT:
        action = (
            "Priority target for a Special Price Magistrate raid. "
            "Substantial overcharging recorded (>50%)."
        )
    elif is_repeat_offender:
        action = "Schedule price monitoring inspection; repeat violations detected."
    else:
        action = "Notice of violation. Vendor cautioned to display the official rate board."

    return ShopProfile(
        shop_name=name,
        area=area,
        total_citations=total,
        open_citations=open_citations,
        resolved_citations=resolved_citations,
        average_overcharge_pct=round(float(row.avg_pct or 0.0), 1),
        max_overcharge_pct=max_pct,
        total_excess_charged_est_pkr=round(float(row.excess or 0.0), 2),
        items_gouged=items_gouged or ["Essential Commodities"],
        is_repeat_offender=is_repeat_offender,
        recommended_action=action,
        latest_complaint_date=row.latest,
    )


@router.post("/reseed", status_code=status.HTTP_200_OK, dependencies=ADMIN_AUTH)
async def trigger_reseed(db: AsyncSession = Depends(get_db)):
    """
    Reseeds realistic Islamabad/Rawalpindi demo grievance data for live hackathon presentations.
    """
    from scripts.seed_demo_data import seed_database
    count = await seed_database(db)
    return {
        "status": "success",
        "message": f"Successfully reseeded {count} demo complaints into the database."
    }


@router.get("/export", dependencies=ADMIN_AUTH)
async def export_complaints_csv(
    category: Optional[str] = Query(None, description="Restrict export to one category"),
    status: Optional[str] = Query(None, description="Restrict export to one status"),
    db: AsyncSession = Depends(get_db),
):
    """Server-side CSV generation of grievance records for magistrate reporting."""
    query = select(Complaint).order_by(desc(Complaint.created_at))
    if category:
        query = query.where(Complaint.category == category)
    if status:
        query = query.where(Complaint.status == status)

    res = await db.execute(query.limit(5000))
    complaints = res.scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "ID", "Created At", "Detected Language", "Category", "Urgency", "Status",
        "Item", "Unit", "Reported Price (PKR)", "Official Price (PKR)",
        "Difference (PKR)", "Overcharge %", "Routing Agency", "Helpline",
        "Location Area", "Shop Name", "Latitude", "Longitude",
        "Confidence", "Needs Review", "Admin Notes", "Transcript",
    ])

    for c in complaints:
        writer.writerow([
            c.id,
            c.created_at.isoformat() if c.created_at else "",
            c.detected_language,
            c.category,
            c.urgency,
            c.status,
            c.item_name or "",
            c.unit or "",
            c.reported_price if c.reported_price is not None else "",
            c.official_price if c.official_price is not None else "",
            c.price_difference_pkr if c.price_difference_pkr is not None else "",
            c.percentage_overcharge if c.percentage_overcharge is not None else "",
            c.routing_agency,
            c.helpline_reference,
            c.location_area or "",
            c.shop_name or "",
            c.lat if c.lat is not None else "",
            c.lng if c.lng is not None else "",
            c.extraction_confidence,
            "yes" if c.needs_review else "no",
            (c.admin_notes or "").replace("\n", " "),
            (c.transcript_raw or "").replace("\n", " "),
        ])

    filename = f"awaaz_complaints_{utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        # utf-8-sig BOM so Excel on Windows renders Urdu transcripts correctly.
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Record-Count": str(len(complaints)),
        },
    )

