import uuid
from sqlalchemy import Column, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base

from timeutils import utcnow

Base = declarative_base()


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Audio details (if submitted via voice)
    audio_filename = Column(String(255), nullable=True)
    audio_duration_seconds = Column(Float, nullable=True)

    # Transcription & Language
    transcript_raw = Column(Text, nullable=False)
    detected_language = Column(String(50), nullable=False, default="Urdu")

    # Governance Routing
    category = Column(String(100), nullable=False, index=True)  # e.g. "PERA - Overpricing", "PFA - Food Safety", "Municipal - Infrastructure"
    urgency = Column(String(20), nullable=False, default="Medium", index=True)  # "Low", "Medium", "High"
    status = Column(String(30), nullable=False, default="Pending", index=True)  # "Pending", "Investigating", "Resolved", "Rejected"

    # AI Quality Assessment
    extraction_confidence = Column(Float, nullable=False, default=1.0)
    needs_review = Column(Boolean, nullable=False, default=False, index=True)

    # Price / Item Details (for Overpricing)
    item_name = Column(String(100), nullable=True, index=True)
    item_canonical_id = Column(String(50), nullable=True, index=True)
    unit = Column(String(50), nullable=True)
    reported_price = Column(Float, nullable=True)
    official_price = Column(Float, nullable=True)
    price_difference_pkr = Column(Float, nullable=True)
    percentage_overcharge = Column(Float, nullable=True)

    # Citizen Acknowledgment & Routing
    native_response = Column(Text, nullable=False)
    routing_agency = Column(String(100), nullable=False)
    helpline_reference = Column(String(100), nullable=False)

    # Location & Vendor metadata
    location_area = Column(String(200), nullable=True, index=True)
    shop_name = Column(String(200), nullable=True, index=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    # Admin resolution notes
    admin_notes = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "audio_filename": self.audio_filename,
            "audio_duration_seconds": self.audio_duration_seconds,
            "transcript_raw": self.transcript_raw,
            "detected_language": self.detected_language,
            "category": self.category,
            "urgency": self.urgency,
            "status": self.status,
            "extraction_confidence": self.extraction_confidence,
            "needs_review": self.needs_review,
            "item_name": self.item_name,
            "item_canonical_id": self.item_canonical_id,
            "unit": self.unit,
            "reported_price": self.reported_price,
            "official_price": self.official_price,
            "price_difference_pkr": self.price_difference_pkr,
            "percentage_overcharge": self.percentage_overcharge,
            "native_response": self.native_response,
            "location_area": self.location_area,
            "shop_name": self.shop_name,
            "lat": self.lat,
            "lng": self.lng,
            "routing_agency": self.routing_agency,
            "helpline_reference": self.helpline_reference,
            "admin_notes": self.admin_notes,
        }

