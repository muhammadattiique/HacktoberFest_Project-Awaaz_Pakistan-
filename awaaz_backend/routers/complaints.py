import os
import uuid
import shutil
import tempfile
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_

from db.session import get_db
from db.models import Complaint
from auth import verify_admin_api_key
from schemas import (
    ComplaintResponse,
    ComplaintListResponse,
    MultiComplaintResponse,
    TextComplaintRequest,
    ComplaintUpdateStatusRequest
)
from services.audio import validate_and_convert_audio
from services.nlp_rules import extract_price_and_normalize
from ai_pipeline import ai_pipeline

logger = logging.getLogger(__name__)

# Starlette renamed the 422 constant; prefer the new name and fall back to the
# legacy alias so the API returns a correct status code on any Starlette version.
UNPROCESSABLE = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", None) or status.HTTP_422_UNPROCESSABLE_ENTITY

router = APIRouter(prefix="/complaints", tags=["Citizen Complaints"])

# Known Islamabad / Rawalpindi localities to extract if not explicitly provided
NOTABLE_AREAS = [
    "G-9 Markaz", "Karachi Company", "Raja Bazaar", "Commercial Market",
    "Aabpara", "F-10 Markaz", "F-6 Super Market", "I-10 Sabzi Mandi",
    "Saddar", "Tench Bhata", "PWD Islamabad", "Barakahu", "Satellite Town"
]


def extract_area_from_text(text: str) -> Optional[str]:
    lowered = text.lower()
    for area in NOTABLE_AREAS:
        if area.lower() in lowered:
            return area
    return None


_URGENCY_RANK = {"High": 3, "Medium": 2, "Low": 1}


def _select_primary(responses: List[ComplaintResponse]) -> ComplaintResponse:
    """Highest overcharge wins; ties broken by urgency rank, then original order.

    An under-rate item (percentage_overcharge <= 0) is never chosen as primary
    while any item is a real violation (percentage_overcharge > 0). Only when no
    item is a violation does selection fall back to the overall max.
    """
    def _rank(r: ComplaintResponse) -> Tuple[float, int]:
        return (
            r.percentage_overcharge or 0.0,
            _URGENCY_RANK.get(r.urgency, 0),
        )

    violations = [r for r in responses if (r.percentage_overcharge or 0.0) > 0]
    pool = violations if violations else responses
    return max(pool, key=_rank)


async def _persist_submission(
    db: AsyncSession,
    *,
    transcript_text: str,
    shared: Dict[str, Any],
) -> MultiComplaintResponse:
    """Extract every item, persist one Complaint row per item under one shared
    ``submission_id`` in a single transaction, and return a MultiComplaintResponse.
    """
    items = await run_in_threadpool(ai_pipeline.parse_complaint_items, transcript_text)
    submission_id = str(uuid.uuid4())

    complaints: List[Complaint] = []
    for extracted in items:
        complaints.append(
            Complaint(
                submission_id=submission_id,
                transcript_raw=transcript_text,
                detected_language=extracted["detected_language"],
                category=extracted["category"],
                urgency=extracted["urgency"],
                status="Pending",
                extraction_confidence=extracted["extraction_confidence"],
                needs_review=extracted["needs_review"],
                item_name=extracted.get("item_name"),
                item_canonical_id=extracted.get("item_canonical_id"),
                unit=extracted.get("unit"),
                reported_price=extracted.get("reported_price"),
                official_price=extracted.get("official_price"),
                price_difference_pkr=extracted.get("price_difference_pkr"),
                percentage_overcharge=extracted.get("percentage_overcharge"),
                native_response=extracted["native_response"],
                routing_agency=extracted["routing_agency"],
                helpline_reference=extracted["helpline_reference"],
                **shared,
            )
        )

    db.add_all(complaints)
    await db.commit()
    for complaint in complaints:
        await db.refresh(complaint)

    responses = [ComplaintResponse.model_validate(c) for c in complaints]
    responses.sort(key=lambda r: r.percentage_overcharge or 0.0, reverse=True)
    primary = _select_primary(responses)

    return MultiComplaintResponse(
        submission_id=submission_id,
        complaints=responses,
        primary=primary,
    )


def _parse_date_bound(value: str, end_of_day: bool = False) -> datetime:
    """Parse an ISO ``YYYY-MM-DD`` (or full timestamp) query bound.

    Returns a naive UTC datetime. Raises 422 with a clear message on bad input
    so magistrates get actionable feedback instead of a silent 500.
    """
    raw = (value or "").strip()
    formats = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
    parsed: Optional[datetime] = None
    for fmt in formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail=f"Invalid date '{value}'. Use ISO format YYYY-MM-DD.",
        )

    if end_of_day and len(raw) == 10:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)

    return parsed


def _parse_bbox(value: str) -> Tuple[float, float, float, float]:
    """Parse a 'min_lat,min_lng,max_lat,max_lng' bounding box."""
    try:
        parts = [float(p.strip()) for p in (value or "").split(",")]
    except ValueError:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail="Invalid bbox. Expected 'min_lat,min_lng,max_lat,max_lng'.",
        )

    if len(parts) != 4:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail="Invalid bbox. Expected exactly 4 comma-separated numbers.",
        )

    min_lat, min_lng, max_lat, max_lng = parts
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail="Invalid bbox. Latitude must be between -90 and 90.",
        )
    if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180):
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail="Invalid bbox. Longitude must be between -180 and 180.",
        )
    if min_lat > max_lat or min_lng > max_lng:
        raise HTTPException(
            status_code=UNPROCESSABLE,
            detail="Invalid bbox. min values must not exceed max values.",
        )

    return min_lat, min_lng, max_lat, max_lng


@router.post("/voice", response_model=MultiComplaintResponse, status_code=status.HTTP_201_CREATED)
async def submit_voice_complaint(
    audio: UploadFile = File(..., description="Audio file (m4a, mp3, wav, webm, ogg, aac)"),
    location_area: Optional[str] = Form(None, description="E.g. 'G-9 Markaz, Islamabad' or 'Raja Bazaar'"),
    shop_name: Optional[str] = Form(None, description="Shop or vendor name"),
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Submits a voice note complaint in Urdu, Roman Urdu, Punjabi, Pashto, or English.
    Converts audio via FFmpeg, transcribes with Whisper, extracts structured intelligence
    with Ollama 1.5B / deterministic rules, and routes to the appropriate authority.
    """
    # Create temp directory for file processing
    temp_dir = tempfile.mkdtemp(prefix="awaaz_audio_")
    raw_path = os.path.join(temp_dir, f"input_{audio.filename or 'audio.wav'}")
    wav_path = os.path.join(temp_dir, "processed_16k.wav")

    try:
        # Save uploaded file. Reading the UploadFile and writing to disk is
        # blocking I/O, so run it in a worker thread to keep the event loop free.
        def _save_upload() -> None:
            with open(raw_path, "wb") as f:
                shutil.copyfileobj(audio.file, f)

        await run_in_threadpool(_save_upload)

        # Validate and convert audio to 16kHz mono WAV.
        # ffmpeg runs as a blocking subprocess; offload it to a worker thread
        # so concurrent requests and health checks are not stalled.
        is_valid, duration_sec, msg = await run_in_threadpool(
            validate_and_convert_audio, raw_path, wav_path
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audio validation failed: {msg}"
            )

        # Transcribe with Whisper (CPU-heavy, blocking) -> worker thread.
        transcription_res = await run_in_threadpool(
            ai_pipeline.transcribe_audio_detailed, wav_path
        )
        transcription_error = transcription_res.get("error")
        if transcription_error:
            logger.error("Voice transcription service failure: %s", transcription_error)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Voice transcription is temporarily unavailable. Please try again or submit your complaint as text."
            )

        transcript_text = transcription_res.get("text", "").strip()
        if not transcript_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No audible speech detected. The audio file was silent or contained unrecognised background noise."
            )

        # Resolve location if not provided
        inferred_area = location_area or extract_area_from_text(transcript_text)

        # Persist one Complaint per extracted item under one submission_id.
        return await _persist_submission(
            db,
            transcript_text=transcript_text,
            shared={
                "audio_filename": audio.filename,
                "audio_duration_seconds": duration_sec,
                "location_area": inferred_area,
                "shop_name": shop_name,
                "lat": lat,
                "lng": lng,
            },
        )

    finally:
        # Clean up temporary audio files
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/text", response_model=MultiComplaintResponse, status_code=status.HTTP_201_CREATED)
async def submit_text_complaint(
    request: TextComplaintRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Submits a text-based complaint in Urdu (Urdu script), Roman Urdu, Punjabi, Pashto, or English.
    """
    text = request.transcript_text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complaint text cannot be empty"
        )

    inferred_area = request.location_area or extract_area_from_text(text)

    # Persist one Complaint per extracted item under one submission_id.
    return await _persist_submission(
        db,
        transcript_text=text,
        shared={
            "audio_filename": None,
            "audio_duration_seconds": None,
            "location_area": inferred_area,
            "shop_name": request.shop_name,
            "lat": request.lat,
            "lng": request.lng,
        },
    )


@router.get("", response_model=ComplaintListResponse)
async def list_complaints(
    category: Optional[str] = Query(None, description="Filter by category"),
    urgency: Optional[str] = Query(None, description="Filter by urgency: Low, Medium, High"),
    status: Optional[str] = Query(None, description="Filter by status: Pending, Investigating, Resolved, Rejected"),
    needs_review: Optional[bool] = Query(None, description="Filter complaints requiring human review"),
    location_area: Optional[str] = Query(None, description="Filter by location area"),
    search: Optional[str] = Query(None, description="Search transcript, item, or shop"),
    shop: Optional[str] = Query(None, description="Exact/partial shop or vendor name"),
    authority: Optional[str] = Query(None, description="Filter by routing agency"),
    date_from: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) lower bound on created_at"),
    date_to: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) upper bound on created_at"),
    bbox: Optional[str] = Query(
        None,
        description="Spatial filter as 'min_lat,min_lng,max_lat,max_lng' (WGS84)",
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Lists complaints with comprehensive filtering, search, and pagination."""
    query = select(Complaint)

    if category:
        query = query.where(Complaint.category == category)
    if urgency:
        query = query.where(Complaint.urgency == urgency)
    if status:
        query = query.where(Complaint.status == status)
    if needs_review is not None:
        query = query.where(Complaint.needs_review == needs_review)
    if location_area:
        query = query.where(Complaint.location_area.ilike(f"%{location_area}%"))
    if shop:
        query = query.where(Complaint.shop_name.ilike(f"%{shop}%"))
    if authority:
        query = query.where(Complaint.routing_agency.ilike(f"%{authority}%"))
    if date_from:
        query = query.where(Complaint.created_at >= _parse_date_bound(date_from, end_of_day=False))
    if date_to:
        query = query.where(Complaint.created_at <= _parse_date_bound(date_to, end_of_day=True))
    if bbox:
        min_lat, min_lng, max_lat, max_lng = _parse_bbox(bbox)
        query = query.where(
            Complaint.lat.is_not(None),
            Complaint.lng.is_not(None),
            Complaint.lat >= min_lat,
            Complaint.lat <= max_lat,
            Complaint.lng >= min_lng,
            Complaint.lng <= max_lng,
        )
    if search:
        search_filter = or_(
            Complaint.transcript_raw.ilike(f"%{search}%"),
            Complaint.item_name.ilike(f"%{search}%"),
            Complaint.shop_name.ilike(f"%{search}%")
        )
        query = query.where(search_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    count_res = await db.execute(count_query)
    total = count_res.scalar() or 0

    # Paginate and order by newest first
    query = query.order_by(desc(Complaint.created_at)).offset((page - 1) * limit).limit(limit)
    res = await db.execute(query)
    items = res.scalars().all()

    return ComplaintListResponse(
        total=total,
        items=[ComplaintResponse.model_validate(i) for i in items],
        page=page,
        limit=limit
    )


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(complaint_id: str, db: AsyncSession = Depends(get_db)):
    """Fetches full details of a specific complaint."""
    res = await db.execute(select(Complaint).where(Complaint.id == complaint_id))
    complaint = res.scalar_one_or_none()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint with ID '{complaint_id}' not found"
        )
    return ComplaintResponse.model_validate(complaint)


@router.patch(
    "/{complaint_id}",
    response_model=ComplaintResponse,
    dependencies=[Depends(verify_admin_api_key)],
)
async def update_complaint_status(
    complaint_id: str,
    update: ComplaintUpdateStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """Updates the administrative resolution status and notes of a complaint.

    Restricted to authorized magistrates via the ``X-API-Key`` header.
    """
    res = await db.execute(select(Complaint).where(Complaint.id == complaint_id))
    complaint = res.scalar_one_or_none()
    if not complaint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint with ID '{complaint_id}' not found"
        )

    valid_statuses = ["Pending", "Investigating", "Resolved", "Rejected"]
    if update.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    complaint.status = update.status
    if update.admin_notes is not None:
        complaint.admin_notes = update.admin_notes
    if update.assigned_authority is not None:
        complaint.routing_agency = update.assigned_authority.strip() or complaint.routing_agency

    # If resolved or rejected, clear review flag
    if update.status in ["Resolved", "Rejected"]:
        complaint.needs_review = False

    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)

