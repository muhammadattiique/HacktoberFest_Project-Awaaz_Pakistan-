import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# The admin portal transmits this shared secret via the X-API-Key header.
ADMIN_HEADERS = {"X-API-Key": "awaaz-admin-2024"}


def test_root_endpoint():
    """Verify root status and metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "Awaaz Pakistan"
    assert data["status"] == "online"
    assert "helplines" in data


def test_rates_endpoints():
    """Verify official rates listing, single item, search, and check."""
    # List all
    res = client.get("/api/rates")
    assert res.status_code == 200
    data = res.json()
    assert data["total_items"] >= 25
    assert len(data["items"]) >= 25

    # Filter category
    res_cat = client.get("/api/rates?category=vegetable")
    assert res_cat.status_code == 200
    veg_data = res_cat.json()
    assert all(item["category"] == "vegetable" for item in veg_data["items"])

    # Search item
    res_srch = client.get("/api/rates?search=potato")
    assert res_srch.status_code == 200
    assert len(res_srch.json()["items"]) >= 1

    # Single item
    res_single = client.get("/api/rates/aloo")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == "aloo"
    assert res_single.json()["price"] == 100.0

    # Non-existent item
    res_404 = client.get("/api/rates/non_existent_item_xyz")
    assert res_404.status_code == 404

    # Reload rate list
    res_reload = client.post("/api/rates/reload")
    assert res_reload.status_code == 200
    assert res_reload.json()["status"] == "success"

    # Price check
    res_chk = client.post("/api/rates/check", json={"query": "Aloo 180 rupay"})
    assert res_chk.status_code == 200
    chk_data = res_chk.json()
    assert chk_data["reported_price"] == 180.0
    assert chk_data["official_price"] == 100.0
    assert chk_data["is_overpriced"] is True
    assert chk_data["percentage_overcharge"] == 80.0


def test_complaints_endpoints():
    """Verify complaint creation, listing, detail, and status updates."""
    # Submit text complaint
    payload = {
        "transcript_text": "Raja Bazaar mein doodh 280 rupay litre bech rahe hain.",
        "location_area": "Raja Bazaar, Rawalpindi",
        "shop_name": "Test Milk Shop"
    }
    create_res = client.post("/api/complaints/text", json=payload)
    assert create_res.status_code == 201
    body = create_res.json()
    created_comp = body["primary"]
    assert body["submission_id"] is not None
    assert len(body["complaints"]) == 1
    assert created_comp["id"] is not None
    assert created_comp["submission_id"] == body["submission_id"]
    assert created_comp["category"] == "PERA - Overpricing"
    assert created_comp["reported_price"] == 280.0
    assert created_comp["official_price"] == 210.0
    comp_id = created_comp["id"]

    # Get single complaint
    get_res = client.get(f"/api/complaints/{comp_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == comp_id
    assert get_res.json()["submission_id"] == body["submission_id"]

    # List complaints
    list_res = client.get("/api/complaints?limit=10")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert len(list_data["items"]) >= 1

    # Filter complaints
    filter_res = client.get("/api/complaints?category=PERA%20-%20Overpricing")
    assert filter_res.status_code == 200
    assert all(c["category"] == "PERA - Overpricing" for c in filter_res.json()["items"])

    # Update complaint status (requires the administrative API key)
    update_res = client.patch(
        f"/api/complaints/{comp_id}",
        json={"status": "Investigating", "admin_notes": "Assigned to Price Magistrate Rawalpindi"},
        headers=ADMIN_HEADERS,
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "Investigating"
    assert update_res.json()["admin_notes"] == "Assigned to Price Magistrate Rawalpindi"


def test_multi_item_complaint_splits_into_two_rows():
    """A submission naming two commodities creates two grouped complaint rows."""
    driver = (
        "Bhai sahab, Raja Bazaar Rawalpindi mein Madina Cash & Carry wala dukandar "
        "aaloo 150 rupay kilo bech raha hai, jabke sarkari rate list ke hisab se ye "
        "sirf 80 rupay kilo hona chahiye. Pyaaz bhi 200 rupay kilo le raha hai. Ye "
        "log zabardasti mehngai kar ke awaam ko loot rahe hain. Please is ke khilaf "
        "action lein."
    )
    res = client.post(
        "/api/complaints/text",
        json={"transcript_text": driver, "location_area": "Raja Bazaar, Rawalpindi"},
    )
    assert res.status_code == 201
    body = res.json()

    complaints = body["complaints"]
    assert len(complaints) == 2

    submission_id = body["submission_id"]
    assert all(c["submission_id"] == submission_id for c in complaints)
    ids = {c["id"] for c in complaints}
    assert len(ids) == 2  # distinct rows

    by_id = {c["item_canonical_id"]: c for c in complaints}
    assert "aloo" in by_id
    assert "pyaaz" in by_id

    potato = by_id["aloo"]
    assert potato["reported_price"] == 150.0
    assert potato["official_price"] == 100.0
    assert potato["percentage_overcharge"] == 50.0
    assert potato["category"] == "PERA - Overpricing"

    onion = by_id["pyaaz"]
    assert onion["reported_price"] == 200.0
    assert onion["official_price"] == 120.0
    assert onion["price_difference_pkr"] == 80.0
    assert onion["percentage_overcharge"] == 66.7
    assert onion["urgency"] == "High"

    assert body["primary"]["item_canonical_id"] == "pyaaz"

    # Shared fields are copied verbatim onto every row.
    assert all(c["transcript_raw"] == driver for c in complaints)
    assert all(c["location_area"] == "Raja Bazaar, Rawalpindi" for c in complaints)

    # PATCH response carries submission_id too.
    patch_res = client.patch(
        f"/api/complaints/{potato['id']}",
        json={"status": "Investigating"},
        headers=ADMIN_HEADERS,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["submission_id"] == submission_id


def test_voice_transcription_failure_returns_503(monkeypatch):
    """Whisper service failures are distinct from genuine silent audio."""
    monkeypatch.setattr(
        "routers.complaints.validate_and_convert_audio",
        lambda *_: (True, 1.0, "Audio valid"),
    )
    monkeypatch.setattr(
        "routers.complaints.ai_pipeline.transcribe_audio_detailed",
        lambda _: {
            "text": "",
            "language": "ur",
            "confidence": 0.0,
            "segments": [],
            "error": "Whisper model not initialized",
        },
    )

    response = client.post(
        "/api/complaints/voice",
        files={"audio": ("recording.webm", b"mock audio", "audio/webm")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Voice transcription is temporarily unavailable. Please try again or "
        "submit your complaint as text."
    )


def test_voice_no_speech_returns_400(monkeypatch):
    """A successful transcription attempt with no speech remains a bad request."""
    monkeypatch.setattr(
        "routers.complaints.validate_and_convert_audio",
        lambda *_: (True, 1.0, "Audio valid"),
    )
    monkeypatch.setattr(
        "routers.complaints.ai_pipeline.transcribe_audio_detailed",
        lambda _: {
            "text": "",
            "language": "ur",
            "confidence": 0.0,
            "segments": [],
        },
    )

    response = client.post(
        "/api/complaints/voice",
        files={"audio": ("recording.webm", b"mock audio", "audio/webm")},
    )

    assert response.status_code == 400
    assert "No audible speech detected" in response.json()["detail"]


def test_analytics_endpoints():
    """Verify overview, hotspots, repeat offenders, and trends."""
    res_ov = client.get("/api/analytics/overview")
    assert res_ov.status_code == 200
    ov_data = res_ov.json()
    assert "total_complaints" in ov_data
    assert "overpricing_cases" in ov_data
    assert "most_gouged_items" in ov_data

    res_hot = client.get("/api/analytics/hotspots")
    assert res_hot.status_code == 200
    assert isinstance(res_hot.json(), list)

    res_rep = client.get("/api/analytics/repeat-offenders")
    assert res_rep.status_code == 200
    assert isinstance(res_rep.json(), list)

    res_tr = client.get("/api/analytics/trends?days=7")
    assert res_tr.status_code == 200
    tr_data = res_tr.json()
    assert "trends" in tr_data
    assert len(tr_data["trends"]) >= 7


def test_admin_endpoints():
    """Verify health and safe config endpoints."""
    res_health = client.get("/api/admin/health")
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data["database_connected"] is True
    assert health_data["rates_count"] >= 25

    # /config is administrative and therefore requires the API key.
    res_cfg = client.get("/api/admin/config", headers=ADMIN_HEADERS)
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert "051" in cfg_data["district_helpline_ict"]
    assert cfg_data["pera_enforcement_helpline"] == "1717"


def test_admin_config_requires_api_key():
    """Non-sensitive /health stays public, but /config must not."""
    # Health is polled by Docker HEALTHCHECK and the citizen dashboard.
    assert client.get("/api/admin/health").status_code == 200

    # Missing credentials -> 401
    res_missing = client.get("/api/admin/config")
    assert res_missing.status_code == 401

    # Wrong credentials -> 403
    res_wrong = client.get("/api/admin/config", headers={"X-API-Key": "definitely-wrong"})
    assert res_wrong.status_code == 403

    # Correct credentials -> 200
    res_ok = client.get("/api/admin/config", headers=ADMIN_HEADERS)
    assert res_ok.status_code == 200


def test_admin_destructive_routes_are_guarded():
    """Reseed wipes and regenerates data, so it must require the admin key."""
    assert client.post("/api/admin/reseed").status_code == 401
    assert client.get("/api/admin/export").status_code == 401


def test_complaint_patch_requires_api_key():
    """Magistrate resolution updates must not be anonymously writable."""
    create_res = client.post(
        "/api/complaints/text",
        json={"transcript_text": "Auth guard test aloo 250 rupay kilo."},
    )
    assert create_res.status_code == 201
    comp_id = create_res.json()["primary"]["id"]

    # Anonymous mutation attempt is rejected.
    anon = client.patch(f"/api/complaints/{comp_id}", json={"status": "Resolved"})
    assert anon.status_code == 401

    # Authorized mutation succeeds.
    auth = client.patch(
        f"/api/complaints/{comp_id}",
        json={"status": "Resolved", "admin_notes": "Authorized update"},
        headers=ADMIN_HEADERS,
    )
    assert auth.status_code == 200
    assert auth.json()["status"] == "Resolved"
    assert auth.json()["admin_notes"] == "Authorized update"


def test_assigned_authority_persists():
    """Authority reassignment is stored on the complaint record."""
    create_res = client.post(
        "/api/complaints/text",
        json={"transcript_text": "Authority reassignment test doodh 300 rupay litre."},
    )
    comp_id = create_res.json()["primary"]["id"]

    res = client.patch(
        f"/api/complaints/{comp_id}",
        json={
            "status": "Investigating",
            "assigned_authority": "Punjab Food Authority (PFA)",
        },
        headers=ADMIN_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["routing_agency"] == "Punjab Food Authority (PFA)"


def test_public_map_points_are_obfuscated():
    """Public heatmap points must be coarse and free of identifying data."""
    res = client.get("/api/analytics/map/points")
    assert res.status_code == 200
    points = res.json()
    assert isinstance(points, list)

    for point in points:
        # Rounded to 3 decimal places (~110m grid) so no shop can be pinpointed.
        assert round(point["lat"], 3) == point["lat"]
        assert round(point["lng"], 3) == point["lng"]
        # Vendor identity and transcripts must never be exposed publicly.
        assert "shop_name" not in point
        assert "transcript_raw" not in point


def test_shop_profile_endpoint():
    """Shop dossier returns citations for a known vendor and 404 otherwise."""
    missing = client.get("/api/admin/shops/No Such Vendor XYZ", headers=ADMIN_HEADERS)
    assert missing.status_code == 404

    # Seed a known shop, then fetch its dossier.
    client.post(
        "/api/complaints/text",
        json={
            "transcript_text": "Aloo 300 rupay kilo at dossier shop.",
            "shop_name": "Dossier Test Store",
            "location_area": "Raja Bazaar",
        },
    )
    found = client.get("/api/admin/shops/Dossier Test Store", headers=ADMIN_HEADERS)
    assert found.status_code == 200
    body = found.json()
    assert body["shop_name"] == "Dossier Test Store"
    assert body["total_citations"] >= 1
    assert "recommended_action" in body


def test_csv_export_with_valid_key():
    """Server-side CSV export streams a downloadable file."""
    res = client.get("/api/admin/export", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]
    assert "Created At" in res.text


def test_complaint_list_query_validation():
    """Malformed filters fail fast with 422 instead of a server error."""
    assert client.get("/api/complaints?date_from=not-a-date").status_code == 422
    assert client.get("/api/complaints?bbox=1,2,3").status_code == 422
    assert client.get("/api/complaints?bbox=10,10,5,5").status_code == 422
    assert client.get("/api/complaints?bbox=99,99,100,100").status_code == 422

    # Well-formed filters succeed.
    assert client.get("/api/complaints?bbox=33.6,73.0,33.7,73.1").status_code == 200
    assert client.get("/api/complaints?date_from=2020-01-01").status_code == 200
    assert client.get("/api/complaints?authority=Food Authority").status_code == 200

