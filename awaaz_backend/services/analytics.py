from datetime import timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from db.models import Complaint
from timeutils import utcnow
from schemas import (
    AnalyticsOverview,
    GougedItemMetric,
    HotspotArea,
    RepeatOffender,
    DailyTrendPoint,
    TrendsResponse
)

# Known twin cities coordinates for map hotspots
TWIN_CITIES_COORDS = {
    "g-9 markaz": {"lat": 33.6897, "lng": 73.0298},
    "karachi company": {"lat": 33.6897, "lng": 73.0298},
    "aabpara": {"lat": 33.7077, "lng": 73.0851},
    "f-10 markaz": {"lat": 33.6961, "lng": 73.0135},
    "i-10 sabzi mandi": {"lat": 33.6552, "lng": 73.0365},
    "f-6 super market": {"lat": 33.7297, "lng": 73.0765},
    "raja bazaar": {"lat": 33.6167, "lng": 73.0560},
    "commercial market": {"lat": 33.6338, "lng": 73.0694},
    "satellite town": {"lat": 33.6338, "lng": 73.0694},
    "saddar": {"lat": 33.5960, "lng": 73.0520},
    "tench bhata": {"lat": 33.5855, "lng": 73.0336},
    "pwd islamabad": {"lat": 33.5880, "lng": 73.1490},
    "barakahu": {"lat": 33.7431, "lng": 73.1762},
    "rawalpindi mandi": {"lat": 33.6185, "lng": 73.0450}
}


def get_area_coords(area_name: Optional[str]) -> Dict[str, float]:
    """Returns approximate lat/lng coordinates for Islamabad/Rawalpindi areas."""
    if not area_name:
        return {"lat": 33.6844, "lng": 73.0479}  # Center of Islamabad
    norm = area_name.lower()
    for key, coords in TWIN_CITIES_COORDS.items():
        if key in norm or norm in key:
            return coords
    return {"lat": 33.6844, "lng": 73.0479}


class AnalyticsService:
    @staticmethod
    async def get_overview(db: AsyncSession) -> AnalyticsOverview:
        # Total count
        total_res = await db.execute(select(func.count(Complaint.id)))
        total_complaints = total_res.scalar() or 0

        # Category counts
        cat_query = select(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category)
        cat_res = await db.execute(cat_query)
        cat_counts = {cat: count for cat, count in cat_res.all()}

        overpricing_cases = cat_counts.get("PERA - Overpricing", 0)
        food_safety_cases = cat_counts.get("PFA - Food Safety", 0)
        infra_cases = cat_counts.get("Municipal - Infrastructure", 0)

        # Average overcharge & total excess
        stats_query = select(
            func.avg(Complaint.percentage_overcharge),
            func.sum(Complaint.price_difference_pkr)
        ).where(Complaint.percentage_overcharge > 0)
        stats_res = await db.execute(stats_query)
        avg_overcharge_raw, total_excess_raw = stats_res.one_or_none() or (0.0, 0.0)

        avg_overcharge_pct = round(float(avg_overcharge_raw or 0.0), 1)
        total_excess_pkr = round(float(total_excess_raw or 0.0), 2)

        # Most gouged items
        item_query = (
            select(
                Complaint.item_name,
                func.count(Complaint.id).label("cnt"),
                func.avg(Complaint.percentage_overcharge).label("avg_pct"),
                func.avg(Complaint.official_price).label("off_pr"),
                func.max(Complaint.reported_price).label("max_pr")
            )
            .where(Complaint.item_name.is_not(None), Complaint.percentage_overcharge > 0)
            .group_by(Complaint.item_name)
            .order_by(desc("cnt"))
            .limit(5)
        )
        item_res = await db.execute(item_query)
        most_gouged = [
            GougedItemMetric(
                item_name=row.item_name,
                complaint_count=row.cnt,
                average_overcharge_pct=round(float(row.avg_pct or 0.0), 1),
                official_price=round(float(row.off_pr or 0.0), 1),
                highest_reported_price=round(float(row.max_pr or 0.0), 1)
            )
            for row in item_res.all()
        ]

        # Urgency & Needs review counts
        urg_res = await db.execute(select(func.count(Complaint.id)).where(Complaint.urgency == "High"))
        high_urgency_count = urg_res.scalar() or 0

        rev_res = await db.execute(select(func.count(Complaint.id)).where(Complaint.needs_review == True))
        needs_review_count = rev_res.scalar() or 0

        return AnalyticsOverview(
            total_complaints=total_complaints,
            overpricing_cases=overpricing_cases,
            food_safety_cases=food_safety_cases,
            infrastructure_cases=infra_cases,
            average_overcharge_pct=avg_overcharge_pct,
            total_excess_charged_est_pkr=total_excess_pkr,
            most_gouged_items=most_gouged,
            high_urgency_count=high_urgency_count,
            needs_review_count=needs_review_count
        )

    @staticmethod
    async def get_hotspots(db: AsyncSession) -> List[HotspotArea]:
        query = (
            select(
                Complaint.location_area,
                func.count(Complaint.id).label("cnt"),
                func.avg(Complaint.percentage_overcharge).label("avg_pct")
            )
            .where(Complaint.location_area.is_not(None))
            .group_by(Complaint.location_area)
            .order_by(desc("cnt"))
            .limit(10)
        )
        res = await db.execute(query)
        hotspots = []
        for row in res.all():
            area = row.location_area
            cnt = row.cnt
            avg_pct = round(float(row.avg_pct or 0.0), 1)

            # Get top violated item for this area
            top_item_query = (
                select(Complaint.item_name)
                .where(Complaint.location_area == area, Complaint.item_name.is_not(None))
                .group_by(Complaint.item_name)
                .order_by(desc(func.count(Complaint.id)))
                .limit(1)
            )
            top_item_res = await db.execute(top_item_query)
            top_item = top_item_res.scalar() or "Assorted Items"

            # Dominant category
            top_cat_query = (
                select(Complaint.category)
                .where(Complaint.location_area == area)
                .group_by(Complaint.category)
                .order_by(desc(func.count(Complaint.id)))
                .limit(1)
            )
            top_cat_res = await db.execute(top_cat_query)
            dominant_cat = top_cat_res.scalar() or "PERA - Overpricing"

            coords = get_area_coords(area)

            hotspots.append(
                HotspotArea(
                    area=area,
                    complaint_count=cnt,
                    avg_overcharge_pct=avg_pct,
                    top_violated_item=top_item,
                    dominant_category=dominant_cat,
                    lat=coords.get("lat"),
                    lng=coords.get("lng")
                )
            )
        return hotspots

    @staticmethod
    async def get_repeat_offenders(db: AsyncSession) -> List[RepeatOffender]:
        query = (
            select(
                Complaint.shop_name,
                Complaint.location_area,
                func.count(Complaint.id).label("violations"),
                func.max(Complaint.percentage_overcharge).label("max_pct"),
                func.max(Complaint.created_at).label("latest_dt")
            )
            .where(Complaint.shop_name.is_not(None), Complaint.shop_name != "")
            .group_by(Complaint.shop_name, Complaint.location_area)
            .having(func.count(Complaint.id) >= 2)
            .order_by(desc("violations"))
            .limit(10)
        )
        res = await db.execute(query)
        offenders = []
        for row in res.all():
            shop = row.shop_name
            area = row.location_area or "Unknown Area"

            # Get distinct items gouged
            items_query = (
                select(Complaint.item_name)
                .where(Complaint.shop_name == shop, Complaint.item_name.is_not(None))
                .distinct()
            )
            items_res = await db.execute(items_query)
            gouged_items = [it for it in items_res.scalars().all() if it]

            offenders.append(
                RepeatOffender(
                    shop_name=shop,
                    area=area,
                    violations_count=row.violations,
                    items_gouged=gouged_items or ["Essential Commodities"],
                    max_overcharge_pct=round(float(row.max_pct or 0.0), 1),
                    status="Pending Enforcement Notice",
                    latest_complaint_date=row.latest_dt or utcnow()
                )
            )
        return offenders

    @staticmethod
    async def get_trends(db: AsyncSession, days: int = 14) -> TrendsResponse:
        start_date = utcnow() - timedelta(days=days)

        # Fetch daily aggregate
        all_comp_query = (
            select(Complaint)
            .where(Complaint.created_at >= start_date)
            .order_by(Complaint.created_at.asc())
        )
        res = await db.execute(all_comp_query)
        complaints = res.scalars().all()

        daily_data: Dict[str, Dict[str, Any]] = {}
        for i in range(days + 1):
            dt_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            daily_data[dt_str] = {"count": 0, "pct_sum": 0.0, "pct_count": 0}

        category_distribution: Dict[str, int] = {}
        urgency_distribution: Dict[str, int] = {}

        for c in complaints:
            dt_str = c.created_at.strftime("%Y-%m-%d")
            if dt_str in daily_data:
                daily_data[dt_str]["count"] += 1
                if c.percentage_overcharge and c.percentage_overcharge > 0:
                    daily_data[dt_str]["pct_sum"] += c.percentage_overcharge
                    daily_data[dt_str]["pct_count"] += 1

            category_distribution[c.category] = category_distribution.get(c.category, 0) + 1
            urgency_distribution[c.urgency] = urgency_distribution.get(c.urgency, 0) + 1

        trends_list = []
        for date_str, stat in sorted(daily_data.items()):
            cnt = stat["count"]
            avg_pct = round(stat["pct_sum"] / stat["pct_count"], 1) if stat["pct_count"] > 0 else 0.0
            trends_list.append(
                DailyTrendPoint(
                    date=date_str,
                    complaint_count=cnt,
                    avg_overcharge_pct=avg_pct
                )
            )

        return TrendsResponse(
            trends=trends_list,
            category_distribution=category_distribution,
            urgency_distribution=urgency_distribution
        )

