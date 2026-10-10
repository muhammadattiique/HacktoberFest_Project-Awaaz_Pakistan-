from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from db.session import get_db
from db.models import Complaint
from services.analytics import AnalyticsService
from schemas import (
    AnalyticsOverview,
    HotspotArea,
    RepeatOffender,
    TrendsResponse,
    PublicMapPoint,
)

router = APIRouter(prefix="/analytics", tags=["Governance Analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(db: AsyncSession = Depends(get_db)):
    """
    Returns governance KPIs: total complaints, overpricing cases,
    estimated excess charged to citizens, and top gouged commodities.
    """
    return await AnalyticsService.get_overview(db)


@router.get("/hotspots", response_model=List[HotspotArea])
async def get_hotspots(db: AsyncSession = Depends(get_db)):
    """
    Returns geographic complaint hotspots across Islamabad and Rawalpindi markets
    with coordinates for dashboard mapping.
    """
    return await AnalyticsService.get_hotspots(db)


@router.get("/repeat-offenders", response_model=List[RepeatOffender])
async def get_repeat_offenders(db: AsyncSession = Depends(get_db)):
    """
    Identifies repeat price-gouging shops and vendors for priority enforcement actions.
    """
    return await AnalyticsService.get_repeat_offenders(db)


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    days: int = Query(14, ge=1, le=90, description="Number of past days for trend series"),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns daily time-series trends of citizen grievances and inflation rate deviations.
    """
    return await AnalyticsService.get_trends(db, days=days)


@router.get("/map/points", response_model=List[PublicMapPoint])
async def get_public_map_points(
    limit: int = Query(500, ge=1, le=2000, description="Maximum points to return"),
    db: AsyncSession = Depends(get_db)
):
    """Coarse, obfuscated spatial points for public macro heatmaps.

    Privacy by design: coordinates are rounded to 3 decimal places (~110 m
    grid), far too coarse to identify a shop or a citizen's residence. Vendor
    names, transcripts and citizen metadata are never returned here — those
    remain behind the authenticated administrative portal.
    """
    query = (
        select(
            Complaint.lat,
            Complaint.lng,
            Complaint.category,
            Complaint.urgency,
            Complaint.percentage_overcharge,
        )
        .where(Complaint.lat.is_not(None), Complaint.lng.is_not(None))
        .order_by(desc(Complaint.created_at))
        .limit(limit)
    )
    res = await db.execute(query)

    points: List[PublicMapPoint] = []
    for lat, lng, category, urgency, pct in res.all():
        pct_value = round(float(pct or 0.0), 1)
        points.append(
            PublicMapPoint(
                lat=round(float(lat), 3),
                lng=round(float(lng), 3),
                category=category,
                urgency=urgency,
                is_overpriced=pct_value > 0,
                overcharge_pct=pct_value,
            )
        )
    return points

